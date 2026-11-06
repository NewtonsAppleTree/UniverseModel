"""Independent engineering checks; target model tests stay in tests/chipmodel."""

from dataclasses import FrozenInstanceError, dataclass, field, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
import unittest
from unittest.mock import patch

from artifacts.storage.local import read_run, write_run
from configuration.resolution.dataclass_config import apply_overrides, load_config, resolve_dataclass
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from evaluation.experiments.runner.single import run_experiment
from example.universal_demo import AdcCase, DmaCase, evaluate_adc, evaluate_dma
from tools import check_model_rules, check_structure


ROOT = Path(__file__).resolve().parents[2]  # Repository fixtures; absolute path for independent test discovery.


# Exercise defaults, nested tuple/union validation and read-only derived fields with a small independent schema.
@dataclass(frozen=True, slots=True, kw_only=True)
class ToyParams:
    count: int  # Discrete count [item]; bool is not an item count.
    gain: float = 1.0  # Explicit dimensionless scalar [1].
    values: tuple[tuple[int, ...], ...] = ()  # Immutable integer matrix [code].
    optional: int | None = None  # Optional discrete input [item]; None means absent.
    policy: Literal["error", "wrap"] = "error"  # Explicit integer overflow policy.
    derived: int = field(init=False)  # Read-only result D=2*count [item].

    # Producer remains responsible for semantic constraints and formulas.
    def __post_init__(self):
        if self.count < 0:
            raise ValueError("count must be nonnegative")
        object.__setattr__(self, "derived", self.count * 2)


# Reuse a declared version/assumption boundary; revisions are explicit identity inputs.
def spec() -> ExperimentSpec:
    return ExperimentSpec(experiment_id="test", implementation_id="test-adapter/v1", mode="analytical",
                          source_revision="test-source/v1", assumptions=("isolated reference",))


# Verify strict decoding and canonical identity without depending on hardware formulas.
class ConfigurationTests(unittest.TestCase):
    # Frozen nested tuples, finite floats and producer defaults survive strict resolution.
    def test_typed_resolution_and_defaults(self):
        value = resolve_dataclass(ToyParams, {"count": 3, "gain": 2, "values": [[1, 2], [3]], "optional": 4})
        self.assertEqual((value.derived, value.gain, value.values, value.optional), (6, 2.0, ((1, 2), (3,)), 4))
        self.assertIs(type(value.gain), float)
        with self.assertRaises(FrozenInstanceError):
            value.count = 4

    # Unknown/derived fields, ambiguous scalar coercion and invalid enums fail with a field location.
    def test_illegal_fields_types_and_semantics(self):
        for override, message in (({"derived": 8}, "derived"), ({"typo": 2}, "typo"),
                                  ({"count": True}, "configuration.count"), ({"count": "3"}, "configuration.count"),
                                  ({"gain": float("inf")}, "configuration.gain"),
                                  ({"gain": 10**400}, "configuration.gain"),
                                  ({"policy": "saturate"}, "configuration.policy"),
                                  ({"values": [[False]]}, r"configuration.values\[0\]\[0\]"),
                                  ({"optional": "4"}, "configuration.optional"), ({"count": -1}, "nonnegative")):
            with self.subTest(override=override), self.assertRaisesRegex((ValueError, TypeError), message):
                resolve_dataclass(ToyParams, {"count": 3, **override})
        with self.assertRaisesRegex(TypeError, "count"):
            resolve_dataclass(ToyParams, {})

    # Invocation overrides are independent copies; sequences replace rather than concatenate.
    def test_override_order_and_input_isolation(self):
        raw = {"outer": {"n": 1}, "values": [1, 2]}
        revised = apply_overrides(raw, {"outer.n": 3, "values": [4]})
        self.assertEqual(raw, {"outer": {"n": 1}, "values": [1, 2]})
        self.assertEqual(revised, {"outer": {"n": 3}, "values": [4]})
        for path in ("", "outer..n", "values.n"):
            with self.assertRaises(ValueError):
                apply_overrides(raw, {path: 2})

    # UTF-8 JSON file loading yields exactly the same canonical effective parameters as Python.
    def test_json_loading_and_model_constraints(self):
        path = ROOT / "config/experiments/universal_adc.json"
        value = load_config(AdcCase, path, overrides={"configuration.adc.lane_count": 8})
        self.assertEqual(value.configuration.adc.lane_count, 8)
        self.assertIsInstance(value.inputs.voltages_v, tuple)
        for override in ({"configuration.adc.lane_count": 0}, {"configuration.adc.lanes": 8},
                         {"schema_version": "future/v2"}):
            with self.assertRaises((ValueError, TypeError)):
                load_config(AdcCase, path, overrides=override)

    # Canonical identity ignores object key order; strings/numeric types and unsupported JSON stay distinct.
    def test_canonical_json_and_rejections(self):
        self.assertEqual(content_hash({"b": [1, 2], "a": 3}), content_hash({"a": 3, "b": (1, 2)}))
        self.assertNotEqual(content_hash(1), content_hash(1.0))
        for source in ('{"n":1,"n":2}', 'NaN', 'Infinity', '1e999'):
            with self.assertRaises((ValueError, TypeError)):
                parse_json(source)
        for value in ({1: "n"}, object(), float("nan")):
            with self.assertRaises((ValueError, TypeError)):
                canonical_json(value)


# Verify mode, evidence, ownership and failure semantics independently of an event engine.
class ExperimentTests(unittest.TestCase):
    # Five ready ADC samples at P=4,L=II=2 finish in four cycles; code outputs preserve input order.
    def test_independent_adc_case(self):
        case = load_config(AdcCase, ROOT / "config/experiments/universal_adc.json")
        record = run_experiment(spec(), case.configuration, case.inputs, evaluate_adc)
        output = record.to_dict()["output"]
        self.assertEqual(record.status, "succeeded")
        self.assertEqual([sample["code"] for sample in output["samples"]], [0, 256, 512, 768, 1023])
        self.assertEqual(output["batch"]["completion_cycles"], 4)
        self.assertEqual(output["batch"]["completion_time_s"], 4e-9)
        self.assertIsNone(record.metrics[-1].value)

    # A 72-byte DMA at 8 B/cycle with startup=1 finishes in ten target cycles.
    def test_independent_dma_case(self):
        case = load_config(DmaCase, ROOT / "config/experiments/universal_dma.json")
        record = run_experiment(spec(), case.configuration, case.inputs, evaluate_dma)
        self.assertEqual(record.to_dict()["output"]["completion_cycles"], 10)
        self.assertEqual(record.metrics[0].value, 72)

    # Repeated calls have independent attempt IDs but share input identity; elapsed host time is excluded.
    def test_repeated_calls_and_snapshot_ownership(self):
        inputs = [1, 2]

        # Mutate only the injected local input copy; caller data and prior snapshots remain unchanged.
        def execute(configuration, local_inputs):
            local_inputs.append(3)
            return local_inputs, ()

        first = run_experiment(spec(), {"n": 1}, inputs, execute)
        second = run_experiment(spec(), {"n": 1}, inputs, execute)
        self.assertEqual(inputs, [1, 2])
        self.assertEqual(first.identity_hash, second.identity_hash)
        self.assertNotEqual(first.run_id, second.run_id)
        self.assertEqual(first.output_json, "[1,2,3]")
        view = first.to_dict()
        view["inputs"].append(99)
        self.assertEqual(first.to_dict()["inputs"], [1, 2])
        changed = run_experiment(spec(), {"n": 2}, inputs, execute)
        self.assertNotEqual(first.identity_hash, changed.identity_hash)

    # Failed callback produces a terminal diagnostic and no fabricated metrics; later calls still work.
    def test_failure_and_invalid_results(self):
        # Model failure remains visible to the orchestrator.
        def fail(configuration, inputs):
            raise ValueError("capacity exceeded")

        failed = run_experiment(spec(), {}, [], fail)
        self.assertEqual(failed.status, "failed")
        self.assertIn("capacity exceeded", failed.diagnostic)
        self.assertIsNone(failed.output_json)
        self.assertEqual(failed.metrics, ())
        duplicate = Metric(name="n", value=1, unit="one", kind="counter")
        bad = run_experiment(spec(), {}, [], lambda c, i: ({}, (duplicate, duplicate)))
        self.assertEqual(bad.status, "failed")
        self.assertIn("duplicate", bad.diagnostic)
        good = run_experiment(spec(), {}, [], lambda c, i: ({}, ()))
        self.assertEqual(good.status, "succeeded")

    # Unknown and zero are different; target cycles require a clock identity and bool is not a counter.
    def test_metric_and_schema_constraints(self):
        self.assertEqual(Metric(name="zero", value=0, unit="joule", kind="estimated").value, 0)
        for args in ({"value": None}, {"value": True}, {"value": float("nan")},
                     {"unit": "cycle"}, {"unit": "ns"}, {"unit": "typo"},
                     {"unknown_reason": "unknown"}, {"kind": "unsupported"}):
            values = {"name": "n", "value": 1, "unit": "one", "kind": "counter", **args}
            with self.assertRaises((ValueError, TypeError)):
                Metric(**values)
        with self.assertRaisesRegex(ValueError, "schema"):
            ExperimentSpec(experiment_id="test", implementation_id="v1", source_revision="test", mode="analytical",
                           assumptions=(), schema_version="future/v2")

    # A static/analytical result cannot claim a simulated time; event producers must explicitly declare mode.
    def test_evidence_kind_matches_mode(self):
        simulated = Metric(name="time", value=1e-9, unit="second", kind="simulated")
        record = run_experiment(spec(), {}, [], lambda c, i: ({}, (simulated,)))
        self.assertEqual(record.status, "failed")
        event = run_experiment(replace(spec(), mode="event"), {}, [], lambda c, i: ({}, (simulated,)))
        self.assertEqual(event.status, "succeeded")


# Validate persistence by independently reading bytes and introducing corrupt/missing artifacts.
class ArtifactTests(unittest.TestCase):
    # A committed bundle preserves effective inputs/results and cannot overwrite an existing attempt.
    def test_round_trip_and_no_overwrite(self):
        record = run_experiment(spec(), {"n": 1}, [2], lambda c, i: (i, ()))
        with TemporaryDirectory() as folder:
            target = write_run(record, Path(folder) / "run")
            self.assertEqual(read_run(target), record.to_dict())
            with self.assertRaises(FileExistsError):
                write_run(record, target)
            self.assertEqual(read_run(target), record.to_dict())

    # Full schema reconstruction preserves null outputs on success and terminal diagnostics on failure.
    def test_record_schema_and_failed_bundle(self):
        success = run_experiment(spec(), {}, [], lambda c, i: (None, ()))
        self.assertEqual(RunRecord.from_dict(success.to_dict()), success)
        with self.assertRaisesRegex(ValueError, "fields"):
            RunRecord.from_dict({**success.to_dict(), "future_field": 1})
        malformed = success.to_dict()
        malformed["identity_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "identity"):
            RunRecord.from_dict(malformed)
        failed = run_experiment(spec(), {}, [], lambda c, i: (object(), ()))
        with TemporaryDirectory() as folder:
            target = write_run(failed, Path(folder) / "failed")
            self.assertEqual(read_run(target)["status"], "failed")
            self.assertEqual(read_run(target)["diagnostic"], failed.diagnostic)

    # Modified bytes, incomplete commits, unsupported versions and path substitutions fail clearly.
    def test_corruption_incomplete_and_manifest_schema(self):
        record = run_experiment(spec(), {}, [], lambda c, i: ({}, ()))
        with TemporaryDirectory() as folder:
            target = write_run(record, Path(folder) / "run")
            data = (target / "run.json").read_bytes()
            (target / "run.json").write_bytes(data + b" ")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                read_run(target)
            (target / "run.json").write_bytes(data)
            manifest_path = target / "manifest.json"
            manifest = parse_json(manifest_path.read_text(encoding="utf-8"))
            manifest["schema_version"] = "future/v2"
            manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema"):
                read_run(target)
            manifest["schema_version"] = "universal-manifest/v1"
            manifest["artifact"]["path"] = "../run.json"
            manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "local run.json"):
                read_run(target)
            manifest_path.unlink()
            with self.assertRaises(FileNotFoundError):
                read_run(target)


# Negative repository fixtures ensure engineering checks enforce real imports and documentation rules.
class StructureTests(unittest.TestCase):
    # A valid dependency manifest cannot hide an actual forbidden cross-module Python import.
    def test_actual_import_dependency_guard(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "docs/architecture").mkdir(parents=True)
            modules = {"modules": [{"id": "contracts", "path": "contracts", "allowed_dependencies": []},
                                   {"id": "evaluation", "path": "evaluation", "allowed_dependencies": ["contracts"]}]}
            (root / "docs/architecture/modules.json").write_text(canonical_json(modules), encoding="utf-8")
            (root / "contracts").mkdir()
            (root / "evaluation").mkdir()
            (root / "contracts/invalid.py").write_text("import evaluation\n", encoding="utf-8")
            (root / "evaluation/valid.py").write_text("from contracts import results\n", encoding="utf-8")
            errors = []
            with patch.object(check_structure, "ROOT", root), patch.object(check_structure, "ERRORS", errors):
                self.assertEqual(check_structure.check_python_dependencies(), 2)
            self.assertEqual(len(errors), 1)
            self.assertIn("forbidden dependency contracts -> evaluation", errors[0])

    # New implementation modules cannot omit definition/field notes or their own generated UNITS section.
    def test_new_module_rule_scope(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "docs/architecture").mkdir(parents=True)
            (root / "contracts/results").mkdir(parents=True)
            (root / "docs/architecture/modules.json").write_text(
                canonical_json({"modules": [{"id": "contracts", "path": "contracts"}]}), encoding="utf-8")
            source = root / "contracts/results/bad.py"
            source.write_text("class Params:\n    count: int\n", encoding="utf-8")
            with patch.object(check_model_rules, "ROOT", root):
                directories = check_model_rules.model_directories()
                errors, _, _ = check_model_rules.inspect_source(source)
                missing_docs = check_model_rules.check()
            self.assertEqual(directories, [root / "contracts", root / "contracts/results"])
            self.assertTrue(any("lacks a preceding" in error for error in errors))
            self.assertTrue(any("lacks field note" in error for error in errors))
            self.assertEqual(len(missing_docs), 2)


if __name__ == "__main__":
    unittest.main()
