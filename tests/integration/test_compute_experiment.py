"""CH6完整对照协议、失败回读，以及显式MAC能力与已有Tile账本的组合。"""

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from chipmodel.composition.tile.digital import TileWork, analyze_tile
from chipmodel.compute.npu.mac import MacArithmetic
from configuration.resolution.dataclass_config import load_config, resolve_dataclass
from contracts.versions.json_codec import canonical_json, parse_json
from evaluation.experiments.runner.compute import ComputeStudy, run_study, summarize_records, write_study, read_study
from evaluation.experiments.runner.linear import LinearStudy, run_study as run_linear
from example.compute_demo import comparison_exit_status
from example.digital_tile_demo import sensitivity_studies


ROOT = Path(__file__).resolve().parents[2]  # 仓库根路径。
CONFIG = ROOT / "config/experiments/compute_capacity.json"  # 三家族分别比较的有限案例。
TILE = ROOT / "config/experiments/digital_tile.json"  # 显式INT8/INT64能力和供数对照。


# 工作身份、成功/可行性、参数预算和未知执行时间都属于可检验的研究协议。
class ComputeExperimentTests(unittest.TestCase):
    # 手算25μop、四block和9MAC的结果；错误签名失败，GPU不可行仍为有效分析输出。
    def test_expected_cases_and_unknown_time(self):
        records = run_study(load_config(ComputeStudy, CONFIG), source_revision="ch6-test")
        rows = {r["case"]: r for r in summarize_records(records)}
        self.assertEqual((len(rows), sum(r.status == "failed" for r in records)), (16, 3))
        a, b = rows["cpu_baseline"]["analysis"], rows["cpu_ports_x2"]["analysis"]
        self.assertEqual((a["peak_uops_per_cycle"], b["peak_uops_per_cycle"], a["issue_span_lower_bound_cycles"]), (2, 2, 12))
        self.assertEqual(rows["cpu_retire_x4"]["analysis"]["bottlenecks"], ["issue"])
        for name in ("gpu_baseline", "gpu_registers_x2", "gpu_shared_x2"):
            self.assertEqual(rows[name]["analysis"]["resident_blocks"], 4)
        self.assertFalse(rows["gpu_launch_rejected"]["analysis"]["launch_feasible"])
        self.assertIsNone(rows["gpu_launch_unknown"]["analysis"]["launch_feasible"])
        self.assertEqual(rows["npu_baseline"]["analysis"]["service"]["completion_cycles"], 7)
        self.assertEqual(rows["npu_lanes_x2"]["analysis"]["service"]["completion_cycles"], 5)
        self.assertEqual(comparison_exit_status(tuple(rows.values())), 0)
        for record in records:
            if record.status == "succeeded":
                time = next(m for m in record.metrics if m.name == "execution_time")
                self.assertIsNone(time.value)
                self.assertTrue(time.unknown_reason)

    # 参数树单数值改动，固定另一侧；不能把改工作或换操作语义标成资源消融。
    def test_comparison_budgets_and_strict_config(self):
        study = load_config(ComputeStudy, CONFIG)
        self.assertEqual(resolve_dataclass(ComputeStudy, parse_json(canonical_json(study))), study)
        baseline, candidate = study.cases[:2]
        bad = (replace(candidate, work=replace(candidate.work, executed_uops=26)),
               replace(candidate, model=replace(candidate.model, params=replace(candidate.model.params, retire_uops_per_cycle=4))),
               replace(candidate, model=replace(baseline.model, uop_class="other")),
               replace(candidate, model=baseline.model))
        for case in bad:
            with self.assertRaises(ValueError):
                replace(study, cases=(baseline, case))
        with self.assertRaises(ValueError):
            replace(study, cases=(baseline, baseline))
        with self.assertRaises(TypeError):
            replace(baseline, family="gpu")

    # source、名单或实际工作不同的记录不能拼成貌似完整且同预算的对照。
    def test_incomplete_mixed_and_work_mismatch(self):
        study = load_config(ComputeStudy, CONFIG)
        records = run_study(study, source_revision="one")
        changed = run_study(study, source_revision="two")
        bad_work = replace(records[0], inputs_json=canonical_json(replace(study.cases[0].work, executed_uops=999)))
        for roster in (records[:-1], (*records, records[0]), (changed[0], *records[1:]), (bad_work, *records[1:])):
            with self.assertRaises(ValueError):
                summarize_records(roster)

    # 完整bundle回读只依赖记录；索引不能遗漏失败案例或越过指定实验目录。
    def test_artifacts_without_model(self):
        study = load_config(ComputeStudy, CONFIG)
        first, second = run_study(study), run_study(study)
        self.assertEqual([r.identity_hash for r in first], [r.identity_hash for r in second])
        self.assertEqual([r.output_json for r in first], [r.output_json for r in second])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "study"
            write_study(first, path)
            with patch("evaluation.experiments.runner.compute.analyze_cpu", side_effect=AssertionError("no model")), \
                 patch("evaluation.experiments.runner.compute.derive_occupancy", side_effect=AssertionError("no model")), \
                 patch("evaluation.experiments.runner.compute.MacArray.analyze", side_effect=AssertionError("no model")):
                self.assertEqual(read_study(path), tuple(sorted(first, key=lambda r: r.spec.experiment_id)))
            index = parse_json((path / "index.json").read_text(encoding="utf-8"))
            (path / "index.json").write_text(canonical_json({**index, "runs": index["runs"][:-1]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                read_study(path)
            index["runs"][0]["directory"] = "../outside"
            (path / "index.json").write_text(canonical_json(index), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "path"):
                read_study(path)

    # CLI保留所有边界失败；退出码仅检查常规分析是否完成，不等于器件或质量验证通过。
    def test_cli_roundtrip(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "compute"
            command = [sys.executable, "-m", "example.compute_demo"]
            saved = subprocess.run(command + ["--source-revision", "cli-test", "--output", str(path)], cwd=ROOT,
                                   capture_output=True, text=True, check=True)
            read = subprocess.run(command + ["--read", str(path)], cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertEqual(parse_json(saved.stdout), parse_json(read.stdout))

    # 显式能力复用MAC成本；同一输入、地址和服务参数下账本/下界与历史接口一致。
    def test_tile_capability_does_not_double_count(self):
        study = load_config(LinearStudy, TILE)
        study = replace(study, candidates=study.candidates[:1])
        typed = parse_json(run_linear(study)[0].output_json)
        backend = study.hardware.tile_backend
        legacy = replace(study, hardware=replace(study.hardware, tile_backend=replace(backend,
                         tile=replace(backend.tile, mac_arithmetic=None))))
        old = parse_json(run_linear(legacy)[0].output_json)
        self.assertEqual(typed["output"], old["output"])
        for key in ("lower_bound_s", "contributions", "service_bounds", "scratch_service"):
            self.assertEqual(typed["tile_analysis"][key], old["tile_analysis"][key])
        detail = typed["tile_analysis"]["mac_analysis"]
        self.assertEqual((detail["logical_macs"], detail["executed_macs"], detail["extra_macs"]), (140, 140, 0))
        self.assertEqual(detail["service"], typed["ideal_compute"])
        self.assertIsNone(old["tile_analysis"]["mac_analysis"])

    # MAC翻倍使孤立计算35→18ns，但同输入Tile仍受348ns搬运约束。
    def test_supply_bound_with_explicit_format(self):
        study = load_config(LinearStudy, TILE)
        study = replace(study, candidates=study.candidates[:1])
        panels = sensitivity_studies(study)[:2]
        a, b = [parse_json(run_linear(panel)[0].output_json) for _, panel in panels]
        self.assertTrue(a["validation"]["passed"] and b["validation"]["passed"])
        self.assertEqual(a["output"], b["output"])
        self.assertEqual([p["tile_analysis"]["mac_analysis"]["service"]["completion_cycles"] for p in (a, b)], [35, 18])
        self.assertEqual([p["tile_analysis"]["lower_bound_s"] for p in (a, b)], [348e-9, 348e-9])
        self.assertEqual(a["traffic"], b["traffic"])

    # 错误累加格式明确失败；只提供能力或请求一侧不能回退到无格式估算。
    def test_tile_unsupported_format_and_partial_declaration(self):
        study = load_config(LinearStudy, TILE)
        backend = study.hardware.tile_backend
        wrong = replace(backend.tile, mac_arithmetic=MacArithmetic(operation="integer_mac", operand_format="int8",
                         accumulator_format="int32", output_format="int32"))
        study = replace(study, candidates=study.candidates[:1], hardware=replace(study.hardware, tile_backend=replace(backend, tile=wrong)))
        record = run_linear(study)[0]
        self.assertEqual(record.status, "failed")
        self.assertIn("unsupported", record.diagnostic)
        work = TileWork(work_id="standalone", executed_macs=0, local_accesses=(), transfers=(), reservations=())
        with self.assertRaisesRegex(ValueError, "both"):
            analyze_tile(backend.tile, work)
        typed = replace(work, mac_arithmetic=backend.tile.mac_arithmetic, logical_macs=0)
        with self.assertRaisesRegex(ValueError, "both"):
            analyze_tile(replace(backend.tile, mac_arithmetic=None), typed)
        self.assertEqual(analyze_tile(backend.tile, typed).mac_analysis.executed_macs, 0)


if __name__ == "__main__":
    unittest.main()
