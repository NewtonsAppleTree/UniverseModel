"""CH8实验协议、完整产物、专业DRAM接入与可重复局部组合。"""

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from chipmodel.composition.die.topology import DomainPlacement
from chipmodel.composition.graph import ResourceNode
from chipmodel.composition.package.assembly import analyze_assembly, project_scopes
from chipmodel.composition.transfer import MemoryResource, PathLink
from configuration.resolution.dataclass_config import load_config, resolve_dataclass
from contracts.versions.json_codec import canonical_json, parse_json
from evaluation.experiments.runner.assembly import AssemblyStudy, read_study, run_study, summarize_records, write_study
from evaluation.experiments.runner.memory import MemoryStudy
from example.assembly_demo import comparison_exit_status


ROOT = Path(__file__).resolve().parents[2]  # 仓库根目录。
CONFIG = ROOT / "config/experiments/chip_assembly.json"  # CH8同工作/资源/顺序比较。


# 输出来源、比较公平性与失效证据属于研究协议，不靠仅运行成功证明。
class AssemblyExperimentTests(unittest.TestCase):
    # 手算共享SRAM、计算位置和D2D；失败名单及未知执行/能量必须保留。
    def test_expected_cases(self):
        records = run_study(load_config(AssemblyStudy, CONFIG), source_revision="ch8-test")
        rows = {r["case"]: r for r in summarize_records(records)}
        self.assertEqual((len(rows), sum(r.status == "failed" for r in records)), (16, 4))
        expected = {"shared_baseline": 16, "shared_parallel": 16, "memory_read_ports_x2": 8,
                    "memory_clock_half": 32, "compute_baseline": 32, "compute_parallel": 16,
                    "ordering_baseline": 16, "ordering_serial": 32, "d2d_baseline": 500,
                    "d2d_lanes_x2": 250, "d2d_latency_x10": 500}
        for name, ns in expected.items():
            self.assertAlmostEqual(rows[name]["result"]["analysis"]["lower_bound_s"] * 1e9, ns)
        self.assertEqual(comparison_exit_status(tuple(rows.values())), 0)
        for record in records:
            if record.status == "succeeded":
                for name in ("execution_time", "energy"):
                    self.assertIsNone(next(m for m in record.metrics if m.name == name).value)

    # 位置只能改tile，资源只能改单个数值，顺序不能偷改真实工作；配置字段严格。
    def test_comparison_protocol(self):
        study = load_config(AssemblyStudy, CONFIG)
        self.assertEqual(resolve_dataclass(AssemblyStudy, parse_json(canonical_json(study))), study)
        by_name = {c.name: c for c in study.cases}
        base, moved = by_name["shared_baseline"], by_name["shared_parallel"]
        bad = (replace(moved, jobs=(moved.jobs[0], replace(moved.jobs[1], dependencies=("a",)))),
               replace(moved, jobs=(moved.jobs[0],)), replace(moved, assembly=replace(moved.assembly, profile_source="other")),
               replace(moved, jobs=base.jobs))
        for case in bad:
            with self.assertRaises(ValueError):
                replace(study, cases=(base, case))
        base, candidate = by_name["bandwidth_baseline"], by_name["memory_read_ports_x2"]
        memory = candidate.assembly.resources.memories[0]
        two_changes = replace(candidate.assembly, resources=replace(candidate.assembly.resources,
            memories=(replace(memory, sram=replace(memory.sram, write_ports_per_bank=2)),)))
        with self.assertRaisesRegex(ValueError, "one numeric"):
            replace(study, cases=(base, replace(candidate, assembly=two_changes)))
        raw = parse_json(canonical_json(study))
        raw["cases"][0]["assembly"]["formula"] = "arbitrary"
        with self.assertRaises(ValueError):
            resolve_dataclass(AssemblyStudy, raw)

    # 跨版本/输入混用或少保留一项失败都不能形成完整比较。
    def test_roster_identity_and_inputs(self):
        study = load_config(AssemblyStudy, CONFIG)
        a, b = run_study(study, source_revision="a"), run_study(study, source_revision="b")
        changed = replace(a[0], inputs_json=canonical_json(study.cases[0].jobs[:1]))
        for records in (a[:-1], (*a, a[0]), (b[0], *a[1:]), (changed, *a[1:])):
            with self.assertRaises(ValueError):
                summarize_records(records)

    # 两次输出和实验身份相同；回读不调用模型，索引越界和遗漏失败记录明确拒绝。
    def test_artifacts_without_execution(self):
        study = load_config(AssemblyStudy, CONFIG)
        first, second = run_study(study), run_study(study)
        self.assertEqual([r.identity_hash for r in first], [r.identity_hash for r in second])
        self.assertEqual([r.output_json for r in first], [r.output_json for r in second])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "assembly"
            write_study(first, path)
            with patch("evaluation.experiments.runner.assembly.analyze_assembly", side_effect=AssertionError("no model")):
                self.assertEqual(read_study(path), tuple(sorted(first, key=lambda r: r.spec.experiment_id)))
            index = parse_json((path / "index.json").read_text(encoding="utf-8"))
            (path / "index.json").write_text(canonical_json({**index, "runs": index["runs"][:-1]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                read_study(path)
            index["runs"][0]["directory"] = "../outside"
            (path / "index.json").write_text(canonical_json(index), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "path"):
                read_study(path)

    # CLI实际运行并保存全部案例，read仅显示已保存的分析和失败。
    def test_cli_roundtrip(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "assembly"
            command = [sys.executable, "-m", "example.assembly_demo"]
            saved = subprocess.run(command + ["--source-revision", "cli-test", "--output", str(path)], cwd=ROOT,
                                   capture_output=True, text=True, check=True)
            read = subprocess.run(command + ["--read", str(path)], cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertEqual(parse_json(saved.stdout), parse_json(read.stdout))

    # CH7的外部DRAM通过显式边界进入Die，未对齐2B读传32B，不复制容量或把row条件当真实执行。
    def test_dram_external_boundary(self):
        study = load_config(AssemblyStudy, CONFIG)
        case = next(c for c in study.cases if c.name == "d2d_baseline")
        p = case.assembly
        dram = load_config(MemoryStudy, ROOT / "config/experiments/memory_access.json").cases[0].profile
        external = MemoryResource(resource_id="external", domain_id="external.domain", capacity_bytes=dram.organization.capacity_bytes, dram_read=dram)
        nodes = (*p.resources.nodes, ResourceNode(instance_id="external", parent_id="package", model_id="dram"),
                 ResourceNode(instance_id="input_link", parent_id="package", model_id="serial"))
        link = PathLink(resource_id="input_link", source_domain="external.domain", target_domain="mem1", params=p.resources.links[0].params)
        resources = replace(p.resources, nodes=nodes, memories=(*p.resources.memories, external), links=(*p.resources.links, link))
        p = replace(p, resources=resources, domains=(*p.domains, DomainPlacement(domain_id="external.domain", die_id=None)))
        work = case.jobs[0]
        request = replace(work.work.transfers[0], source_id="external", source_address_bytes=15, payload_bytes=2,
                          channel_id="dma1", path=("input_link",), source_row_state="closed")
        work = replace(work, work=replace(work.work, transfers=(request,)))
        r = analyze_assembly(p, (work,))
        bus = next(c for c in r.contributions if c.resource_id == "external/channel/0/read_bus")
        self.assertEqual(bus.amount, 32)
        self.assertEqual(sum(size for _, size in r.memory_capacities), 1536)
        self.assertEqual(next(t for t in r.boundary_traffic if t.link_id == "input_link").payload_bytes, 2)
        self.assertEqual(project_scopes(r, ("package",))[0].memory_capacity_bytes, 1536)
        self.assertTrue(any("row states" in reason for reason in r.unknown_costs))


if __name__ == "__main__":
    unittest.main()
