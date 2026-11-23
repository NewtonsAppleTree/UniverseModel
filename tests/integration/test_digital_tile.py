"""同输入/预算映射、显式本地访问、物理成本未知和记录回读。"""

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from artifacts.storage.local import read_run, write_run
from chipmodel.compute.npu.mac import MacArithmetic
from configuration.resolution.dataclass_config import load_config, resolve_dataclass
from contracts.plan.linear import TileShape
from contracts.results.experiment import RunRecord
from contracts.versions.json_codec import canonical_json, parse_json
from contracts.workload.linear import LinearSpec
from evaluation.experiments.runner.linear import LinearStudy, MappingCandidate, run_study, summarize_records
from evaluation.experiments.runner.training import TrainingStudy, run_training_study
from example.digital_tile_demo import read_comparison, sensitivity_studies, write_comparison


ROOT = Path(__file__).resolve().parents[2]  # 仓库绝对路径。
CONFIG = ROOT / "config/experiments/digital_tile.json"  # 同预算有限对照配置。


# 主对照保持数值与资源一致；额外资源变更仅用于敏感性/消融。
class DigitalTileExperimentTests(unittest.TestCase):
    # 小型binary64/MatVec沿用相同独立数值参考，地址事务模型不绑定INT8。
    def test_float_matvec(self):
        study = load_config(LinearStudy, CONFIG)
        backend = study.hardware.tile_backend
        floating = replace(backend, tile=replace(backend.tile, mac_arithmetic=MacArithmetic(
            operation="float_mul_add", operand_format="float64", accumulator_format="float64", output_format="float64"),
            mac_profile_source="Analytical binary64 mul-add test; no device calibration"))
        study = replace(study, workload=LinearSpec(m=2, n=1, k=2, dtype="float64"),
                        hardware=replace(study.hardware, operand_dtype="float64", tile_backend=floating),
                        candidates=(MappingCandidate(name="matvec", tile=TileShape(m=1, n=1, k=1), strategy="output_stationary"),))
        record = run_study(study)[0]
        self.assertEqual(record.status, "succeeded")
        self.assertTrue(parse_json(record.output_json)["validation"]["passed"])

    # 训练仍使用旧硬件子集，不能接受Tile参数后悄悄忽略新增SRAM/路径成本。
    def test_training_rejects_unimplemented_tile_backend(self):
        training = load_config(TrainingStudy, ROOT / "config/experiments/training_step.json")
        tile_hardware = load_config(LinearStudy, CONFIG).hardware
        records = run_training_study(replace(training, hardware=replace(tile_hardware, operand_dtype="float64")))
        self.assertTrue(all(r.status == "failed" and "Tile address mapping" in r.diagnostic for r in records))

    # 扫描应产生 DMA→计算/存储瓶颈迁移，更多 MAC 不能突破相同 DMA 约束。
    def test_sensitivity_and_complete_roster(self):
        study = load_config(LinearStudy, CONFIG)
        panels = tuple((case, run_study(candidate)) for case, candidate in sensitivity_studies(study))
        rows = {case: summarize_records(records)[0] for case, records in panels}
        self.assertEqual(rows["baseline"]["resource_lower_bound_s"], 348e-9)
        self.assertEqual(rows["mac_lanes_x2"]["resource_lower_bound_s"], 348e-9)
        self.assertEqual(rows["mac_clock_div100"]["resource_lower_bound_s"], 3500e-9)
        self.assertIn("mac", rows["mac_clock_div100"]["bottlenecks"])
        self.assertEqual(rows["dma_clock_div4"]["resource_lower_bound_s"], 1392e-9)
        self.assertEqual(rows["sram_clock_div10"]["resource_lower_bound_s"], 1380e-9)
        self.assertIn("scratch/bank/0", rows["sram_clock_div10"]["bottlenecks"])
        self.assertEqual(rows["one_bank_same_capacity"]["resource_lower_bound_s"], 400e-9)
        self.assertTrue(all(row["external_bytes"] == 314 for row in rows.values()))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "panels"
            write_comparison(path, panels)
            self.assertEqual(read_comparison(path), panels)
            (path / panels[0][1][-1].run_id / "manifest.json").unlink()
            with self.assertRaises((OSError, ValueError)):
                read_comparison(path)

    # 两种 C 驻留策略功能相同，保留外部流量增加、真实 bank 事务和失败样本。
    def test_same_budget_conservation_and_capacity_failure(self):
        study = load_config(LinearStudy, CONFIG)
        records = run_study(study, source_revision="test-tile/v1")
        rows = summarize_records(records)
        self.assertEqual([r["external_bytes"] for r in rows], [314, 954, 370, None])
        self.assertEqual([r["validation_passed"] for r in rows], [True, True, True, None])
        self.assertEqual([r["resource_lower_bound_s"] for r in rows], [348e-9, 588e-9, 460e-9, None])
        self.assertEqual(rows[0]["bank_reads"], [138, 122, 110, 30])
        self.assertEqual(rows[1]["bank_reads"], [158, 142, 130, 50])
        self.assertIn("need 223 bytes, have 64", rows[-1]["diagnostic"])
        payloads = [parse_json(r.output_json) for r in records[:-1]]
        self.assertEqual(len({canonical_json(p["output"]) for p in payloads}), 1)
        self.assertEqual(len({p["input_identity"] for p in payloads}), 1)
        for record, payload in zip(records, payloads):
            work, analysis = payload["tile_work"], payload["tile_analysis"]
            self.assertEqual(work["executed_macs"], 140)
            self.assertEqual(sum(r["payload_bytes"] for r in work["transfers"]),
                             sum(leg["logical_bytes"] for leg in analysis["transfer"]["legs"] if leg["role"] == "source_read"))
            self.assertIsNone(analysis["energy_j"])
            self.assertTrue(analysis["transfer"]["unknown_costs"])
            self.assertEqual(record.spec.implementation_id, "linear-tile-analysis/v1")

    # 1×1×2 手算：本地 A/B读4B，C读8B、写16B；DMA 12B，合计读写各20B。
    def test_small_explicit_access_reference(self):
        study = load_config(LinearStudy, CONFIG)
        study = replace(study, workload=LinearSpec(m=1, n=1, k=2, dtype="int8"),
                        candidates=(MappingCandidate(name="tiny", tile=TileShape(m=1, n=1, k=1), strategy="output_stationary"),))
        payload = parse_json(run_study(study)[0].output_json)
        work, service = payload["tile_work"], payload["tile_analysis"]["scratch_service"]
        self.assertEqual(len(work["local_accesses"]), 7)
        self.assertEqual((service["logical_read_bytes"], service["logical_write_bytes"]), (20, 20))
        self.assertEqual(service["bank_reads"], [6, 2, 2, 0])
        self.assertEqual(service["bank_writes"], [6, 2, 2, 0])
        self.assertEqual([r["source_address_bytes"] for r in work["transfers"]], [0, 2, 1, 3, 2])

    # 外部矩阵行距保留在地址中；scratch arena 则逐行紧凑，不复用外部stride。
    def test_tensor_rows_and_host_limit(self):
        study = load_config(LinearStudy, CONFIG)
        payload = parse_json(run_study(study)[0].output_json)
        transfers = payload["tile_work"]["transfers"][:5]
        self.assertEqual([r["source_address_bytes"] for r in transfers], [0, 7, 35, 39, 43])
        self.assertEqual([r["target_address_bytes"] for r in transfers], [0, 3, 6, 8, 10])
        limited = replace(study, hardware=replace(study.hardware,
                          tile_backend=replace(study.hardware.tile_backend, max_local_accesses=1)))
        records = run_study(limited)
        self.assertEqual(records[0].status, "failed")
        self.assertIn("max_local_accesses", records[0].diagnostic)

    # 配置与直接调用的同一硬件预算不可分叉；所有实际参数参与来源身份。
    def test_strict_config_and_budget_identity(self):
        study = load_config(LinearStudy, CONFIG)
        self.assertEqual(resolve_dataclass(LinearStudy, parse_json(canonical_json(study))), study)
        with self.assertRaisesRegex(ValueError, "budgets"):
            replace(study.hardware, scratch_capacity_bytes=128)
        config = parse_json(canonical_json(study))
        config["hardware"]["tile_backend"]["access_policy"] = "infer-from-dma"
        with self.assertRaises((ValueError, TypeError)):
            resolve_dataclass(LinearStudy, config)

    # 功能、bank账本与未知项均可从只读产物恢复；配置和来源变化可追溯。
    def test_artifacts_repeated_identity_and_cli(self):
        study = load_config(LinearStudy, CONFIG)
        first, second = run_study(study), run_study(study)
        self.assertEqual([r.identity_hash for r in first], [r.identity_hash for r in second])
        self.assertEqual([r.output_json for r in first], [r.output_json for r in second])
        with TemporaryDirectory() as directory:
            for record in first:
                path = Path(directory) / record.run_id
                write_run(record, path)
                self.assertEqual(RunRecord.from_dict(read_run(path)), record)
            output = Path(directory) / "cli"
            command = [sys.executable, "-m", "example.linear_demo"]
            saved = subprocess.run(command + ["--config", str(CONFIG), "--output", str(output)],
                                   cwd=ROOT, capture_output=True, text=True, check=True)
            read = subprocess.run(command + ["--read", str(output)], cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertEqual(sorted(parse_json(saved.stdout), key=lambda r: r["candidate"]),
                             sorted(parse_json(read.stdout), key=lambda r: r["candidate"]))


if __name__ == "__main__":
    unittest.main()
