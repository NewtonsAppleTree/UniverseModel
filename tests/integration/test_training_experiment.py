"""Full training accounting, immutable records and optional framework cross-validation."""

from dataclasses import replace
import importlib.util
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from artifacts.storage.local import read_run, write_run
from compiler.src.interpret.training import execute_training
from configuration.resolution.dataclass_config import load_config, resolve_dataclass
from contracts.plan.linear import TileShape
from contracts.results.experiment import RunRecord
from contracts.versions.json_codec import canonical_json, parse_json
from contracts.workload.training import TrainingInputs, TrainingSpec, TrainingState
from evaluation.experiments.runner.training import TrainingExperiment, TrainingStudy, evaluate_training, run_training_study, summarize_training
from workloads.graphs.training import generate_training
from workloads.reference.training import compare_training, reference_training


ROOT = Path(__file__).resolve().parents[2]  # Repository fixture root.
CONFIG = ROOT / "config/experiments/training_step.json"  # Shared rectangular two-layer experiment.


# Verify one complete training experiment without requiring a framework in the default environment.
class TrainingIntegrationTests(unittest.TestCase):
    # Candidate comparison resets old state; whole-step dataflow costs include auxiliary operations and failed points.
    def test_default_study_and_accounting(self):
        records = run_training_study(load_config(TrainingStudy, CONFIG), source_revision="test-training/v1")
        rows = summarize_training(records)
        self.assertEqual([row["validation_passed"] for row in rows], [True, True, True, None])
        self.assertEqual([row.get("gemm_payload") for row in rows], [1392, 1680, 1840, None])
        self.assertEqual([row.get("gemm_scratch_peak") for row in rows], [96, 96, 64, None])
        self.assertTrue(all(row["gemm_macs"] == 120 and row["auxiliary_logical_payload"] == 1448 and row["backing_peak"] == 568 for row in rows[:3]))
        self.assertEqual(len({record.inputs_json for record in records}), 1)
        payloads = [parse_json(record.output_json) for record in records[:3]]
        self.assertEqual(len({canonical_json(payload["result"]) for payload in payloads}), 1)
        self.assertTrue(all(payload["result"]["gradients"]["state_version"] == 0 and payload["result"]["next_state"]["version"] == 1 for payload in payloads))
        self.assertIn("need 208 bytes, have 128", records[-1].diagnostic)
        self.assertIsNone(records[-1].output_json)

    # Unmodeled auxiliary service prevents any complete-step latency/energy or MFU claim.
    def test_time_and_energy_coverage(self):
        record = run_training_study(load_config(TrainingStudy, CONFIG))[0]
        metrics = {metric.name: metric for metric in record.metrics}
        self.assertAlmostEqual(metrics["gemm_resource_lower_bound"].value, 532e-9, delta=1e-19)
        self.assertEqual(metrics["gemm_resource_lower_bound"].kind, "lower_bound")
        for name in ("step_time", "step_energy"):
            self.assertIsNone(metrics[name].value)
            self.assertTrue(metrics[name].unknown_reason)
        self.assertNotIn("host_elapsed_s", metrics)
        self.assertNotIn("MFU", metrics)

    # Every tensor observation agrees with the independent exact oracle for non-square, tail and multilayer cases.
    def test_shape_policy_and_activation_matrix(self):
        for widths in ((1, 1), (3, 2), (2, 3, 1), (3, 2, 4, 2)):
            for activation in ("identity", "relu"):
                spec = TrainingSpec(batch_size=3, widths=widths, hidden_activation=activation)
                state, data = generate_training(spec, 21)
                reference = reference_training(spec, state, data, 0.03125)
                for strategy in ("output_stationary", "reload_partials"):
                    with self.subTest(widths=widths, activation=activation, strategy=strategy):
                        result, _ = execute_training(spec, state, data, 0.03125, TileShape(m=2, n=2, k=2), strategy,
                                                      scratch_capacity_bytes=128, backing_capacity_bytes=8192)
                        self.assertTrue(all(value.passed for value in compare_training(result, reference).values()))

    # Quality checks include gradients and updates, and explicitly fail on numerical cancellation despite run completion.
    def test_numerical_failure_and_all_observations(self):
        study = load_config(TrainingStudy, CONFIG)
        spec = TrainingSpec(batch_size=1, widths=(3, 1))
        params = TrainingExperiment(workload=spec, hardware=study.hardware, candidate=study.candidates[0],
                                    backing_capacity_bytes=4096, learning_rate=0.0, atol=0.0, rtol=0.0)
        state = TrainingState(version=0, weights=((1.0, 1.0, 1.0),))
        data = TrainingInputs(x=(1e16, 1.0, -1e16), target=(0.0,))
        payload, _ = evaluate_training(params, (state, data))
        self.assertFalse(payload["validation_passed"])
        self.assertFalse(payload["validation"]["loss"].passed)
        self.assertFalse(payload["validation"]["dx"].passed)
        exact = reference_training(spec, state, data, 0.0)
        altered = replace(exact, next_state=replace(exact.next_state, weights=((2.0, 1.0, 1.0),)))
        self.assertFalse(compare_training(altered, exact)["updated_w0"].passed)

    # Configuration is strict, attempts are repeatable, and infeasible backing/format cases retain diagnostics.
    def test_configuration_reproducibility_and_failures(self):
        study = load_config(TrainingStudy, CONFIG)
        self.assertEqual(resolve_dataclass(TrainingStudy, parse_json(canonical_json(study))), study)
        first, second = run_training_study(study), run_training_study(study)
        self.assertEqual([record.identity_hash for record in first], [record.identity_hash for record in second])
        self.assertEqual([record.output_json for record in first], [record.output_json for record in second])
        self.assertNotEqual(first[0].run_id, second[0].run_id)
        for changed in (replace(study, backing_capacity_bytes=567), replace(study, hardware=replace(study.hardware, operand_dtype="int8"))):
            self.assertTrue(all(record.status == "failed" for record in run_training_study(changed)))
        with self.assertRaises(ValueError):
            replace(study, candidates=(study.candidates[0], study.candidates[0]))

    # Bundles retain full old state, new state, reference and failures without requiring a reference backend at replay.
    def test_artifacts_and_cli_replay(self):
        records = run_training_study(load_config(TrainingStudy, CONFIG))
        with TemporaryDirectory() as directory:
            for record in records:
                path = Path(directory) / record.run_id
                write_run(record, path)
                self.assertEqual(RunRecord.from_dict(read_run(path)), record)
            command = [sys.executable, "-m", "example.training_demo", "--read", directory]
            loaded = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertEqual(sorted(parse_json(loaded.stdout), key=lambda row: row["candidate"]),
                             sorted(summarize_training(records), key=lambda row: row["candidate"]))


# Optional external evidence runs in a pinned framework environment; default standard-library tests remain independent.
@unittest.skipUnless(importlib.util.find_spec("torch") is not None, "optional PyTorch environment not installed")
class PyTorchTrainingTests(unittest.TestCase):
    # Framework autograd and SGD independently validate prediction, loss, every dW/dX and next weights across layouts.
    def test_autograd_sgd_crosscheck(self):
        from evaluation.calibration.pytorch_training import pytorch_environment, pytorch_training
        environment = pytorch_environment()
        self.assertEqual((environment["device"], environment["dtype"]), ("cpu", "float64"))
        for batch, widths, activation in ((1, (2, 1), "identity"), (2, (3, 4, 2), "relu"), (3, (2, 3, 1), "identity"), (2, (3, 2, 4, 2), "relu")):
            spec = TrainingSpec(batch_size=batch, widths=widths, hidden_activation=activation)
            state, data = generate_training(spec, 13)
            torch_result = pytorch_training(spec, state, data, 0.03125)
            for strategy in ("output_stationary", "reload_partials"):
                with self.subTest(batch=batch, widths=widths, strategy=strategy):
                    result, _ = execute_training(spec, state, data, 0.03125, TileShape(m=2, n=2, k=2), strategy,
                                                  scratch_capacity_bytes=128, backing_capacity_bytes=8192)
                    self.assertTrue(all(value.passed for value in compare_training(result, torch_result).values()))

    # External implementation version participates in recorded provenance, and the ordinary artifacts remain readable.
    def test_external_record_provenance(self):
        study = load_config(TrainingStudy, CONFIG)
        records = run_training_study(study, reference_backend="pytorch")
        self.assertTrue(all(row["validation_passed"] for row in summarize_training(records[:3])))
        environment = parse_json(records[0].configuration_json)["reference_environment"]
        self.assertIn("torch_version", environment)
        self.assertEqual(environment["reference_scope"], "functional-only")
        self.assertEqual(RunRecord.from_dict(records[0].to_dict()), records[0])


if __name__ == "__main__":
    unittest.main()
