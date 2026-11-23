"""CIM研究主张、精度失败、来源一致性与完整候选保存/回读。"""

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import load_config, resolve_dataclass
from contracts.versions.json_codec import canonical_json, parse_json
from evaluation.experiments.runner.cim import (CimCandidate, CimStudy, apply_candidate, evaluate_cim_experiment,
                                               read_study, run_study, summarize_records, write_study)
from example.cim_demo import comparison_exit_status


ROOT = Path(__file__).resolve().parents[2]  # 仓库根目录。
CONFIG = ROOT / "config/experiments/cim_matvec.json"  # 固定电气/时序假设的有限研究配置。


# 记录功能质量与执行状态，资源和精度消融不混入同预算主比较。
class CimExperimentTests(unittest.TestCase):
    # 基线及数字求差得到相同点积；转换/数字工作量与资源界体现差分位置代价。
    def test_fixed_input_comparison_and_counts(self):
        records = run_study(load_config(CimStudy, CONFIG), source_revision="test-cim/v1")
        rows = {r["candidate"]: r for r in summarize_records(records)}
        self.assertEqual(len(rows), 7)
        a, d = rows["analog_difference"], rows["digital_difference"]
        self.assertEqual(a["output"], [-12, 14, 10])
        self.assertEqual(a["output"], d["output"])
        self.assertTrue(a["validation_passed"] and d["validation_passed"])
        self.assertEqual((a["counts"]["adc_conversions"], d["counts"]["adc_conversions"]), (18, 36))
        self.assertEqual((a["counts"]["digital_operations"], d["counts"]["digital_operations"]), (36, 72))
        self.assertEqual((a["resource_lower_bound_s"], d["resource_lower_bound_s"]), (36e-9, 72e-9))
        self.assertEqual((a["serial_policy_time_s"], d["serial_policy_time_s"]), (108e-9, 168e-9))
        self.assertEqual(len({r.inputs_json for r in records}), 1)
        self.assertEqual(comparison_exit_status(tuple(rows.values())), 0)

    # 增加ADC不改变数字资源界，ADC降频会转移瓶颈，量化误差单独报告。
    def test_resource_and_quality_ablation(self):
        rows = {r["candidate"]: r for r in summarize_records(run_study(load_config(CimStudy, CONFIG)))}
        self.assertEqual(rows["adc_lanes_x2"]["resource_lower_bound_s"], 36e-9)
        self.assertEqual(rows["adc_clock_div4"]["resource_lower_bound_s"], 44e-9)
        self.assertEqual(rows["adc_clock_div4"]["bottlenecks"], ["cim/adc"])
        coarse = rows["adc_2bit"]
        self.assertEqual(coarse["status"], "succeeded")
        self.assertFalse(coarse["validation_passed"])
        self.assertEqual((coarse["max_abs_error"], coarse["clipped_samples"]), (62, 0))
        for name in ("hold_too_small", "hold_expires"):
            self.assertEqual(rows[name]["status"], "failed")
            self.assertIsNone(rows[name]["counts"])
            self.assertIsNone(rows[name]["resource_lower_bound_s"])

    # 未知能耗/编程显式None，host_elapsed_s不是目标性能；profile与初态进入输出。
    def test_unknown_costs_modes_and_sources(self):
        records = run_study(load_config(CimStudy, CONFIG), source_revision="cim-source-test")
        record = records[0]
        metrics = {m.name: m for m in record.metrics}
        for name in ("read_energy", "programming_energy", "programming_time"):
            self.assertIsNone(metrics[name].value)
            self.assertTrue(metrics[name].unknown_reason)
        self.assertEqual(metrics["resource_lower_bound"].kind, "lower_bound")
        self.assertEqual(metrics["serial_policy_time"].kind, "estimated")
        self.assertEqual(record.spec.mode, "analytical")
        self.assertNotIn("host_elapsed_s", metrics)
        payload = parse_json(record.output_json)
        self.assertEqual(payload["validation"]["exact_output"], [-12, 14, 10])
        self.assertIn("no device calibration", payload["effective_tile"]["profile_source"])
        self.assertEqual(len(payload["analysis"]["numeric"]["programmed_arrays"]), 4)

    # 输出格式的独立参考包含有符号饱和/模运算，不借硬件移位函数验证自身。
    def test_independent_overflow_reference(self):
        study = load_config(CimStudy, CONFIG)
        for policy, expected in (("saturate", [-8, 7, 7]), ("wrap", [4, -2, -6])):
            tile = replace(study.tile, numeric=replace(study.tile.numeric, output_bits=4, overflow=policy))
            payload, _ = evaluate_cim_experiment(tile, study.inputs)
            self.assertTrue(payload["validation"]["passed"])
            self.assertEqual(list(payload["validation"]["reference_output"]), expected)

    # 严格解析生产类型和语义：主mapping不得偷换ADC资源预算。
    def test_configuration_and_comparison_contracts(self):
        study = load_config(CimStudy, CONFIG)
        self.assertEqual(resolve_dataclass(CimStudy, parse_json(canonical_json(study))), study)
        for args in (dict(name="bad", category="mapping", subtract_before_adc=False, adc_lane_count=4),
                     dict(name="bad", category="baseline", adc_lane_count=4),
                     dict(name="bad", category="precision_ablation", adc_frequency_hz=1e9),
                     dict(name="bad", category="resource_ablation", adc_lane_count=True)):
            with self.assertRaises((TypeError, ValueError)):
                CimCandidate(**args)
        with self.assertRaises(ValueError):
            replace(study, candidates=(study.candidates[0], study.candidates[0]))
        with self.assertRaises(TypeError):
            apply_candidate(None, study.candidates[0])
        raw = parse_json(canonical_json(study))
        raw["tile"]["numeric"]["conductance_step_s"] = "1/1024"
        with self.assertRaises((TypeError, ValueError)):
            resolve_dataclass(CimStudy, raw)

    # 重复尝试有独立run_id，内容身份/数值不变；不同输入或source不可混入同一比较。
    def test_identity_and_mixed_study_rejection(self):
        study = load_config(CimStudy, CONFIG)
        a, b = run_study(study), run_study(study)
        self.assertEqual([r.identity_hash for r in a], [r.identity_hash for r in b])
        self.assertEqual([r.output_json for r in a], [r.output_json for r in b])
        self.assertTrue(all(x.run_id != y.run_id for x, y in zip(a, b)))
        other = run_study(study, source_revision="changed")
        for records in (a[:-1], (*a, a[0]), (other[0], *a[1:])):
            with self.assertRaises(ValueError):
                summarize_records(records)

    # 回读只依赖已提交记录；删除失败bundle、重复索引或非法路径不能静默通过。
    def test_complete_artifacts_and_read_without_model(self):
        records = run_study(load_config(CimStudy, CONFIG))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "study"
            write_study(records, path)
            with patch("evaluation.experiments.runner.cim.analyze_cim", side_effect=AssertionError("must not run")):
                self.assertEqual(summarize_records(read_study(path)), summarize_records(records))
            index = parse_json((path / "index.json").read_text(encoding="utf-8"))
            truncated = {**index, "runs": index["runs"][:-1]}
            (path / "index.json").write_text(canonical_json(truncated), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                read_study(path)
            index["runs"][0]["directory"] = "../outside"
            (path / "index.json").write_text(canonical_json(index), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "path"):
                read_study(path)

    # CLI保存/读取同一质量、失败与来源结果，退出状态要求主比较通过。
    def test_cli_roundtrip_and_expected_failures(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cim"
            command = [sys.executable, "-m", "example.cim_demo"]
            saved = subprocess.run(command + ["--source-revision", "cli-test", "--output", str(path)],
                                   cwd=ROOT, text=True, capture_output=True, check=True)
            restored = subprocess.run(command + ["--read", str(path)], cwd=ROOT, text=True, capture_output=True, check=True)
            self.assertEqual(parse_json(saved.stdout), parse_json(restored.stdout))
            rows = parse_json(saved.stdout)
            self.assertEqual(sum(r["status"] == "failed" for r in rows), 2)
            self.assertEqual(sum(r["validation_passed"] is False for r in rows), 1)
        self.assertEqual(comparison_exit_status(({"category": "baseline", "status": "succeeded", "validation_passed": False},)), 1)


if __name__ == "__main__":
    unittest.main()
