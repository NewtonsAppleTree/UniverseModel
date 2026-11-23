"""Cross-module arithmetic, service accounting, provenance and artifact tests."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import unittest

from artifacts.storage.local import read_run, write_run
from configuration.resolution.dataclass_config import load_config, resolve_dataclass
from contracts.plan.linear import TileShape
from contracts.results.experiment import ExperimentSpec, RunRecord
from contracts.versions.json_codec import canonical_json, parse_json
from contracts.workload.linear import LinearInputs, LinearSpec
from evaluation.experiments.runner.linear import LinearExperiment, LinearStudy, MappingCandidate, evaluate_mapping, run_study, summarize_records
from evaluation.experiments.runner.single import run_experiment
from example.linear_demo import comparison_exit_status


ROOT = Path(__file__).resolve().parents[2]  # Absolute repository root for fixture and CLI access.
CONFIG = ROOT / "config/experiments/linear_mapping.json"  # Versioned hand-auditable example configuration.


# Exercise the complete bounded experiment while preserving independent functional and analytical claims.
class LinearExperimentTests(unittest.TestCase):
    # Shared source data and budget give three valid mappings and one recorded capacity failure.
    def test_default_study_and_failed_candidate(self):
        study = load_config(LinearStudy, CONFIG)
        records = run_study(study, source_revision="test-linear/v1")
        summary = summarize_records(records)
        self.assertEqual([row["status"] for row in summary], ["succeeded"] * 3 + ["failed"])
        self.assertEqual([row["external_bytes"] for row in summary], [314, 954, 370, None])
        self.assertEqual([row["scratch_bytes"] for row in summary], [44, 44, 25, None])
        self.assertEqual([row["validation_passed"] for row in summary], [True, True, True, None])
        self.assertIn("need 223 bytes, have 64", summary[-1]["diagnostic"])
        self.assertEqual(len({record.inputs_json for record in records}), 1)
        outputs = [parse_json(record.output_json) for record in records[:-1]]
        self.assertEqual(len({output["input_identity"] for output in outputs}), 1)
        self.assertEqual(len({canonical_json(output["output"]) for output in outputs}), 1)
        self.assertIsNone(records[-1].output_json)
        self.assertEqual(records[-1].metrics, ())
        self.assertEqual(comparison_exit_status(summary), 0)

    # Independently counted row service is converted with DMA frequency, never MAC or host time.
    def test_clock_domains_lower_bound_and_unknown_energy(self):
        records = run_study(load_config(LinearStudy, CONFIG))
        for record, dma_cycles in zip(records[:3], (174, 294, 230)):
            metrics = {metric.name: metric for metric in record.metrics}
            payload = parse_json(record.output_json)
            self.assertEqual(payload["serial_dma_cycles"], dma_cycles)
            self.assertAlmostEqual(metrics["ideal_compute_service"].value, 35 / 1e9, delta=1e-20)
            self.assertAlmostEqual(metrics["serial_dma_service"].value, dma_cycles / 5e8, delta=1e-19)
            self.assertAlmostEqual(metrics["resource_time_lower_bound"].value, dma_cycles / 5e8, delta=1e-19)
            self.assertEqual(metrics["resource_time_lower_bound"].kind, "lower_bound")
            self.assertIsNone(metrics["total_energy"].value)
            self.assertTrue(metrics["total_energy"].unknown_reason)
            self.assertNotIn("host_elapsed_s", metrics)
            self.assertGreaterEqual(record.host_elapsed_s, 0)
            self.assertEqual(record.spec.mode, "analytical")

    # Lower transfer bandwidth increases the bound; more scratch admits the previously infeasible mapping.
    def test_hardware_sensitivity(self):
        baseline = load_config(LinearStudy, CONFIG)
        slow = replace(baseline, hardware=replace(baseline.hardware, dma=replace(baseline.hardware.dma, bytes_per_cycle=1)))
        ordinary = summarize_records(run_study(baseline))
        reduced = summarize_records(run_study(slow))
        self.assertGreater(reduced[0]["resource_lower_bound_s"], ordinary[0]["resource_lower_bound_s"])
        self.assertEqual(reduced[0]["external_bytes"], ordinary[0]["external_bytes"])
        large = replace(baseline, hardware=replace(baseline.hardware, scratch_capacity_bytes=256))
        full = summarize_records(run_study(large))[-1]
        self.assertTrue(full["validation_passed"])
        self.assertEqual((full["scratch_bytes"], full["external_bytes"]), (223, 223))

    # Explicit hardware format mismatch becomes a failed run instead of borrowing INT8 throughput for floats.
    def test_dtype_capability_and_float_study(self):
        original = load_config(LinearStudy, CONFIG)
        floating = replace(original, workload=replace(original.workload, dtype="float64"))
        self.assertTrue(all(record.status == "failed" for record in run_study(floating)))
        supported = replace(floating, hardware=replace(floating.hardware, operand_dtype="float64", scratch_capacity_bytes=1024))
        self.assertTrue(all(row["validation_passed"] for row in summarize_records(run_study(supported))))

    # Cancellation demonstrates that callback success and analytical counters do not prove numerical quality.
    def test_successful_execution_with_failed_numerical_quality(self):
        base = load_config(LinearStudy, CONFIG)
        params = LinearExperiment(workload=LinearSpec(m=1, n=1, k=3, dtype="float64"),
                                  hardware=replace(base.hardware, operand_dtype="float64"),
                                  candidate=MappingCandidate(name="cancellation", tile=TileShape(m=1, n=1, k=1), strategy="output_stationary"),
                                  atol=0.0, rtol=0.0)
        spec = ExperimentSpec(experiment_id="cancellation", implementation_id="linear-mapping-analysis/v1", mode="analytical",
                              source_revision="test/v1", assumptions=("scalar binary64 without FMA",))
        record = run_experiment(spec, params, LinearInputs(a=(1e16, 1.0, -1e16), b=(1.0, 1.0, 1.0)), evaluate_mapping)
        summary = summarize_records((record,))
        self.assertEqual(record.status, "succeeded")
        self.assertFalse(summary[0]["validation_passed"])
        self.assertEqual(comparison_exit_status(summary), 1)
        good = run_study(base)[0]
        self.assertEqual(comparison_exit_status(summarize_records((good, record))), 1)

    # Typed configurations preserve canonical identity and reject accidental duplicate candidate names.
    def test_configuration_roundtrip_and_overrides(self):
        original = load_config(LinearStudy, CONFIG)
        self.assertEqual(resolve_dataclass(LinearStudy, parse_json(canonical_json(original))), original)
        overridden = load_config(LinearStudy, CONFIG, overrides={"hardware.scratch_capacity_bytes": 44, "seed": 8})
        self.assertEqual((overridden.hardware.scratch_capacity_bytes, overridden.seed), (44, 8))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            replace(original, candidates=(original.candidates[0], original.candidates[0]))
        with self.assertRaises(ValueError):
            replace(original, candidates=())
        for override in ({"workload.n": True}, {"hardware.typo": 1}, {"atol": -1.0}):
            with self.subTest(override=override), self.assertRaises((TypeError, ValueError)):
                load_config(LinearStudy, CONFIG, overrides=override)

    # Repeated studies own fresh attempts with reproducible identity, generator provenance and target outputs.
    def test_repeated_study_identity(self):
        study = load_config(LinearStudy, CONFIG)
        first, second = run_study(study), run_study(study)
        self.assertEqual([record.identity_hash for record in first], [record.identity_hash for record in second])
        self.assertEqual([record.output_json for record in first], [record.output_json for record in second])
        self.assertTrue(all(a.run_id != b.run_id for a, b in zip(first, second)))
        configuration = parse_json(first[0].configuration_json)
        self.assertEqual(configuration["input_generator"], {"version": "sha256-index-v1", "seed": 7})

    # Saved immutable records retain both success and failure and can rebuild the exact same comparison.
    def test_artifact_roundtrip(self):
        records = run_study(load_config(LinearStudy, CONFIG), source_revision="test/v1")
        with TemporaryDirectory() as directory:
            restored = []
            for record in records:
                path = Path(directory) / record.run_id
                write_run(record, path)
                restored.append(RunRecord.from_dict(read_run(path)))
            self.assertEqual(summarize_records(tuple(restored)), summarize_records(records))
            self.assertEqual(restored, list(records))

    # CLI read derives rows from verified bundles even if the non-authoritative summary file is damaged.
    def test_cli_save_read_and_all_infeasible_exit(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "study"
            command = [sys.executable, "-m", "example.linear_demo"]
            saved = subprocess.run(command + ["--output", str(output)], cwd=ROOT, capture_output=True, text=True, check=True)
            expected = parse_json(saved.stdout)
            (output / "summary.json").write_text("not authoritative", encoding="utf-8")
            loaded = subprocess.run(command + ["--read", str(output)], cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertEqual(sorted(parse_json(loaded.stdout), key=lambda row: row["candidate"]),
                             sorted(expected, key=lambda row: row["candidate"]))
            failed = subprocess.run(command + ["--set", "hardware.scratch_capacity_bytes=1"], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(failed.returncode, 1)
            self.assertTrue(all(row["status"] == "failed" for row in parse_json(failed.stdout)))


if __name__ == "__main__":
    unittest.main()
