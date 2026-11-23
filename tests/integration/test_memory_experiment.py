"""CH7对照协议、记录完整性及真实Linear/Tile外存接入。"""

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import load_config, resolve_dataclass
from contracts.versions.json_codec import canonical_json, parse_json
from evaluation.experiments.runner.memory import MemoryStudy, run_study, summarize_records, write_study, read_study
from evaluation.experiments.runner.linear import LinearStudy, run_study as run_linear
from example.memory_demo import comparison_exit_status


ROOT = Path(__file__).resolve().parents[2]  # 仓库根目录。
CONFIG = ROOT / "config/experiments/memory_access.json"  # 三类外存与缓存的完整合成对照。
TILE = ROOT / "config/experiments/digital_tile.json"  # 已有数字Tile任务与资源映射。


# 对照必须保留失败/未知，且资源和工作变化符合声明的实验条件。
class MemoryExperimentTests(unittest.TestCase):
    # 手算行前缀、缓存冲突/布局和NAND页重用；unknown分析成功不能当成完整时间。
    def test_expected_results(self):
        records = run_study(load_config(MemoryStudy, CONFIG), source_revision="ch7-test")
        rows = {r["case"]: r for r in summarize_records(records)}
        self.assertEqual((len(rows), sum(r.status == "failed" for r in records)), (21, 4))
        self.assertEqual([rows[name]["analysis"]["completion_cycles"] for name in ("dram_baseline", "dram_closed", "dram_conflict")], [12, 15, 20])
        self.assertEqual([rows[name]["analysis"]["cache"]["line_misses"] for name in ("cache_baseline", "cache_ways_x2", "cache_distributed_layout")], [4, 2, 2])
        self.assertEqual(rows["cache_dirty"]["analysis"]["cache"]["deferred_dirty_bytes"], 16)
        self.assertEqual(rows["cache_dirty_flush"]["analysis"]["cache"]["writeback_bytes"], 48)
        self.assertAlmostEqual(rows["nand_baseline"]["analysis"]["modeled_time_s"], 21e-6)
        self.assertAlmostEqual(rows["nand_output_x2"]["analysis"]["modeled_time_s"], 17.5e-6)
        self.assertAlmostEqual(rows["nand_different_page"]["analysis"]["modeled_time_s"], 31e-6)
        self.assertIsNone(rows["nand_unknown_output"]["analysis"]["modeled_time_s"])
        self.assertEqual(comparison_exit_status(tuple(rows.values())), 0)
        for record in records:
            if record.status == "succeeded":
                metric = next(m for m in record.metrics if m.name == "execution_time")
                self.assertIsNone(metric.value)
                self.assertTrue(metric.unknown_reason)

    # strict配置与单因素预算；不能借资源标签同时改变工作或多个数值参数。
    def test_config_and_comparison_guards(self):
        study = load_config(MemoryStudy, CONFIG)
        self.assertEqual(resolve_dataclass(MemoryStudy, parse_json(canonical_json(study))), study)
        base, rank = study.cases[:2]
        changed = (replace(rank, work=replace(rank.work, row_state="conflict")),
                   replace(rank, profile=replace(rank.profile, organization=replace(rank.profile.organization, channel_count=2))),
                   replace(rank, profile=base.profile), replace(rank, role="access_comparison"))
        for case in changed:
            with self.assertRaises(ValueError):
                replace(study, cases=(base, case))
        with self.assertRaises(ValueError):
            replace(study, cases=(base, base))
        raw = parse_json(canonical_json(study))
        raw["cases"][0]["work"]["formula"] = "eval"
        with self.assertRaises(ValueError):
            resolve_dataclass(MemoryStudy, raw)

    # 输入、源码身份或名单不一致的记录不得拼为完整对照。
    def test_roster_and_identity_guards(self):
        study = load_config(MemoryStudy, CONFIG)
        a, b = run_study(study, source_revision="one"), run_study(study, source_revision="two")
        bad = replace(a[0], inputs_json=canonical_json(replace(study.cases[0].work, row_state="closed")))
        for records in (a[:-1], (*a, a[0]), (b[0], *a[1:]), (bad, *a[1:])):
            with self.assertRaises(ValueError):
                summarize_records(records)

    # 保存/回读不执行模型，身份和输出可复现；索引遗漏与越界路径要被拒绝。
    def test_artifacts_and_replay(self):
        study = load_config(MemoryStudy, CONFIG)
        first, second = run_study(study), run_study(study)
        self.assertEqual([r.identity_hash for r in first], [r.identity_hash for r in second])
        self.assertEqual([r.output_json for r in first], [r.output_json for r in second])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "memory"
            write_study(first, path)
            with patch("evaluation.experiments.runner.memory._evaluate", side_effect=AssertionError("must not run model")):
                self.assertEqual(read_study(path), tuple(sorted(first, key=lambda r: r.spec.experiment_id)))
            index = parse_json((path / "index.json").read_text(encoding="utf-8"))
            (path / "index.json").write_text(canonical_json({**index, "runs": index["runs"][:-1]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                read_study(path)
            index["runs"][0]["directory"] = "../outside"
            (path / "index.json").write_text(canonical_json(index), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "path"):
                read_study(path)

    # CLI回读输出一致，必须实际执行完整默认案例；退出成功不表示已知全部硬件成本。
    def test_cli_roundtrip(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "memory"
            command = [sys.executable, "-m", "example.memory_demo"]
            saved = subprocess.run(command + ["--source-revision", "cli-test", "--output", str(path)], cwd=ROOT,
                                   capture_output=True, text=True, check=True)
            read = subprocess.run(command + ["--read", str(path)], cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertEqual(parse_json(saved.stdout), parse_json(read.stdout))

    # 相同Linear工作换为DRAM源，数值、MAC和scratch账本不变；读burst只在DRAM总线上累计一次。
    def test_linear_tile_external_dram(self):
        study = load_config(LinearStudy, TILE)
        study = replace(study, candidates=study.candidates[:1])
        backend = study.hardware.tile_backend
        p = load_config(MemoryStudy, CONFIG).cases[0].profile
        memories = tuple(replace(m, capacity_bytes=p.organization.capacity_bytes, sram=None, clock=None,
                                  unknown_reason=None, dram_read=p) if m.resource_id == backend.external_memory_id else m
                         for m in backend.tile.resources.memories)
        tile = replace(backend.tile, resources=replace(backend.tile.resources, memories=memories))
        with self.assertRaisesRegex(ValueError, "external_read_row_state"):
            replace(backend, tile=tile)
        changed = replace(study, hardware=replace(study.hardware, tile_backend=replace(backend, tile=tile, external_read_row_state="closed")))
        old, new = run_linear(study)[0], run_linear(changed)[0]
        self.assertEqual((old.status, new.status), ("succeeded", "succeeded"), new.diagnostic)
        a, b = parse_json(old.output_json), parse_json(new.output_json)
        self.assertEqual(a["output"], b["output"])
        for key in ("scratch_service", "mac_analysis"):
            self.assertEqual(a["tile_analysis"][key], b["tile_analysis"][key])
        transfer = b["tile_analysis"]["transfer"]
        burst_bytes = sum(sum(amount for _, amount in service["channel_transferred_bytes"]) for _, service in transfer["dram_services"])
        bus = next(c for c in b["tile_analysis"]["contributions"] if c["resource_id"] == backend.external_memory_id + "/channel/0/read_bus")
        self.assertEqual(bus["amount"], burst_bytes)
        self.assertTrue(any("write service" in reason for reason in transfer["unknown_costs"]))
        self.assertGreater(burst_bytes, 0)


if __name__ == "__main__":
    unittest.main()
