"""CH9实际配置、来源/回读以及CH8物理适配的集成证据。"""

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from chipmodel.composition.package.assembly import analyze_assembly
from chipmodel.packaging.assembly import assembly_physical_model, assembly_physical_work
from chipmodel.packaging.evidence import ObservationWindow, Placement, analyze_physical
from chipmodel.packaging.geometry.floorplan import Rectangle
from configuration.resolution.dataclass_config import load_config, resolve_dataclass
from contracts.versions.json_codec import canonical_json, parse_json
from costmodel.providers.tabulated.lookup import CostTable
from evaluation.experiments.runner.assembly import AssemblyStudy
from evaluation.experiments.runner.physical import PhysicalStudy, read_study, run_study, summarize_records, write_study

ROOT = Path(__file__).resolve().parents[2]  # 测试读取真实配置，独立子进程验证CLI。
CONFIG = ROOT / "config/experiments/physical_evidence.json"  # 完整20案例列表。


# 实验记录不把未知、几何/热必要条件失败和程序失败混为一类。
class PhysicalExperimentTests(unittest.TestCase):
    # 来源点、观测倍增、缺项、热阈值和三种预期运行失败。
    def test_default_results(self):
        study = load_config(PhysicalStudy, CONFIG)
        self.assertEqual(study.cases[0].table, load_config(CostTable, ROOT / "config/costs/nangate45_typical.json"))
        rows = {r["case"]: r for r in summarize_records(run_study(study, source_revision="test"))}
        self.assertEqual(len(rows), 20)
        self.assertEqual(sum(r["status"] == "failed" for r in rows.values()), 3)
        baseline = rows["stdcell_baseline"]["result"]["physical"]
        self.assertAlmostEqual(baseline["characterized_area_mm2"] * 1e6, 1.33)
        self.assertAlmostEqual(baseline["modeled_energy_j"] * 1e9, 31.746545)
        self.assertAlmostEqual(rows["stdcell_window_x2"]["result"]["physical"]["modeled_energy_j"] / baseline["modeled_energy_j"], 2)
        self.assertFalse(rows["stdcell_area_too_small"]["result"]["physical"]["area_fits_placement"])
        for name in ("stdcell_no_window", "stdcell_toggle_unknown", "stdcell_summary_unknown", "stdcell_pvt_outside", "assembly_assumed_window"):
            self.assertIsNone(rows[name]["result"]["physical"]["modeled_energy_j"])
        self.assertTrue(rows["thermal_baseline"]["result"]["thermal"]["within_limit"])
        self.assertFalse(rows["thermal_resistance_x2"]["result"]["thermal"]["within_limit"])
        self.assertFalse(rows["thermal_power_x2"]["result"]["thermal"]["within_limit"])
        self.assertEqual(rows["synthetic_energy_summary"]["result"]["physical"]["modeled_energy_j"], 3.75)

    # 配置严格解析，比较不能在声称改变时长时偷换成本表/结构/工作。
    def test_comparison_protocol(self):
        study = load_config(PhysicalStudy, CONFIG)
        self.assertEqual(resolve_dataclass(PhysicalStudy, parse_json(canonical_json(study))), study)
        base, candidate = study.cases[:2]
        with self.assertRaisesRegex(ValueError, "outside"):
            replace(study, cases=(base, replace(candidate, table=replace(candidate.table, points=()))))
        with self.assertRaisesRegex(ValueError, "change"):
            replace(study, cases=(base, replace(candidate, work=base.work)))
        thermal = next(c for c in study.cases if c.name == "thermal_baseline")
        changed = replace(thermal, name="two_factors", role="thermal", thermal=replace(thermal.thermal,
            model=replace(thermal.thermal.model, resistance_k_per_w=4, capacitance_j_per_k=10)))
        with self.assertRaisesRegex(ValueError, "one numeric"):
            replace(study, cases=(thermal, changed))
        raw = parse_json(canonical_json(study))
        raw["cases"][0]["model"]["formula"] = "arbitrary expression"
        with self.assertRaises(ValueError):
            resolve_dataclass(PhysicalStudy, raw)

    # 全名单、输入、来源版本与run身份必须对应，失败项不能从比较中删掉。
    def test_roster_and_identity(self):
        study = load_config(PhysicalStudy, CONFIG)
        a, b = run_study(study, source_revision="a"), run_study(study, source_revision="b")
        changed = replace(a[0], inputs_json=canonical_json(replace(study.cases[0].work, observation=None)))
        for records in (a[:-1], (*a, a[0]), (b[0], *a[1:]), (changed, *a[1:])):
            with self.assertRaises(ValueError):
                summarize_records(records)

    # 保存/回读只处理记录，不依赖网络/模型执行；索引篡改、遗漏和覆盖均拒绝。
    def test_artifact_roundtrip(self):
        study = load_config(PhysicalStudy, CONFIG)
        records = run_study(study)
        with TemporaryDirectory() as directory:
            target = Path(directory) / "study"
            write_study(records, target)
            with patch("evaluation.experiments.runner.physical.analyze_physical", side_effect=AssertionError("no execute")):
                self.assertEqual(summarize_records(read_study(target)), summarize_records(records))
            with self.assertRaises(FileExistsError):
                write_study(records, target)
            index = parse_json((target / "index.json").read_text(encoding="utf-8"))
            (target / "index.json").write_text(canonical_json({**index, "runs": index["runs"][:-1]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                read_study(target)
            index["runs"][0]["directory"] = "../outside"
            (target / "index.json").write_text(canonical_json(index), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "path"):
                read_study(target)

    # CLI真实运行完整配置，并回读完全相同的结果和失败状态。
    def test_cli(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "study"
            command = [sys.executable, "-m", "example.physical_demo"]
            saved = subprocess.run(command + ["--source-revision", "cli-test", "--output", str(path)], cwd=ROOT,
                                   capture_output=True, text=True, check=True)
            read = subprocess.run(command + ["--read", str(path)], cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertEqual(parse_json(saved.stdout), parse_json(read.stdout))

    # CH8共享SRAM/MAC工作量不丢失；相同结构不因资源名称不同而得到不同cost key。
    def test_assembly_activity_conservation(self):
        case = next(c for c in load_config(AssemblyStudy, ROOT / "config/experiments/chip_assembly.json").cases if c.name == "shared_parallel")
        analysis = analyze_assembly(case.assembly, case.jobs)
        sample = load_config(PhysicalStudy, CONFIG).cases[0]
        rect = Rectangle(x_mm=0, y_mm=0, width_mm=10, height_mm=10)
        model = assembly_physical_model(analysis, sample.model.structures[0].operating_point, boundary=rect,
            placements=(Placement(resource_id="die", rectangle=rect),), geometry_source=sample.model.geometry_source)
        work = assembly_physical_work(analysis)
        self.assertEqual(sum(a.amount for a in work.activities if a.work_unit == "MAC"), 64)
        self.assertEqual(sum(a.amount for a in work.activities if a.action == "read_word"), 16)
        self.assertEqual(sum(a.amount for a in work.activities if a.work_unit == "word"),
                         sum(c.amount for c in analysis.contributions if c.work_unit == "word"))
        mac_ids = {s.structure_id for s in model.structures if s.resource_id in ("mac0", "mac1")}
        self.assertEqual(len(mac_ids), 1)
        self.assertIsNone(work.observation)
        self.assertIn("SHA256:", work.activity_source)
        result = analyze_physical(model, work, sample.table)
        self.assertIsNone(result.characterized_area_mm2)
        self.assertIsNone(result.modeled_energy_j)
        assumed = replace(work, observation=ObservationWindow(duration_s=1e-6, basis="assumed", source=sample.model.geometry_source))
        self.assertIsNone(analyze_physical(model, assumed, sample.table).modeled_energy_j)

    # 跨Die真正线路bit原样进入动作账本；PHY能量未知不影响原计数。
    def test_d2d_activity_conservation(self):
        study = load_config(AssemblyStudy, ROOT / "config/experiments/chip_assembly.json")
        case = next(c for c in study.cases if c.name == "d2d_baseline")
        analysis = analyze_assembly(case.assembly, case.jobs)
        work = assembly_physical_work(analysis)
        self.assertEqual(sum(a.amount for a in work.activities if a.action == "wire_bit"), 500)
        self.assertEqual(sum(t.wire_bits for t in analysis.boundary_traffic), 500)
        self.assertIsNone(work.observation)

    # 共享RW服务约束仍需保留不同的read/write动作，不能用合并端口需求抹去能量差异。
    def test_shared_rw_activity_semantics(self):
        study = load_config(AssemblyStudy, ROOT / "config/experiments/chip_assembly.json")
        case = next(c for c in study.cases if c.name == "shared_parallel")
        memory = case.assembly.resources.memories[0]
        memory = replace(memory, sram=replace(memory.sram, read_ports_per_bank=0, write_ports_per_bank=0, shared_rw_ports_per_bank=1))
        assembly = replace(case.assembly, resources=replace(case.assembly.resources, memories=(memory,)))
        job = case.jobs[0]
        access = job.work.local_accesses[0]
        job = replace(job, work=replace(job.work, local_accesses=(replace(access, direction="write"), *job.work.local_accesses[1:])))
        analysis = analyze_assembly(assembly, (job, case.jobs[1]))
        work = assembly_physical_work(analysis)
        self.assertEqual(sum(a.amount for a in work.activities if a.action == "read_word"), 15)
        self.assertEqual(sum(a.amount for a in work.activities if a.action == "write_word"), 1)
        self.assertEqual(sum(c.amount for c in analysis.contributions if c.work_unit == "word"), 16)


if __name__ == "__main__":
    unittest.main()
