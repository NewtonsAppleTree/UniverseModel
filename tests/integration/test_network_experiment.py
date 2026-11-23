"""C1 configuration, evidence identity, failures and artifact round trips."""

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from artifacts.storage.local import read_run, write_run
from configuration.resolution.dataclass_config import load_config, resolve_dataclass
from contracts.results.experiment import RunRecord
from contracts.versions.json_codec import canonical_json, parse_json
from example.network_demo import NetworkCase, NetworkInputs, run_case, summarize


ROOT = Path(__file__).resolve().parents[2]  # Repository root; model inputs are independent of process cwd.
CONFIG = ROOT / "config/experiments/network_link.json"  # Explicit C1 demonstration parameters.


# The existing engineering boundary preserves scope/unknowns and does not turn host time into target time.
class NetworkIntegrationTests(unittest.TestCase):
    # Nested configuration returns real frozen model values with the exact independently checked 42 us result.
    def test_configuration_and_known_example(self):
        case = load_config(NetworkCase, CONFIG)
        result = run_case(case, source_revision="test-source/v1")
        self.assertEqual(result.status, "succeeded", result.diagnostic)
        metrics = {metric.name: metric for metric in result.metrics}
        self.assertAlmostEqual(metrics["isolated_link_time"].value, 42e-6, delta=1e-18)
        self.assertEqual(metrics["link_frame_bytes"].value, 1_000_000)
        self.assertIsNone(metrics["network_energy"].value)
        self.assertTrue(metrics["network_energy"].unknown_reason)
        self.assertTrue(all(metric.kind != "simulated" for metric in result.metrics))

    # Failed profile queries retain the original input/configuration and no fabricated successful metrics.
    def test_out_of_domain_failure_record(self):
        case = load_config(NetworkCase, CONFIG)
        graph = replace(case.configuration.graph, links=tuple(replace(item, profile_max_payload_bytes=64)
                                                            for item in case.configuration.graph.links))
        case = replace(case, configuration=replace(case.configuration, graph=graph))
        result = run_case(case)
        self.assertEqual(result.status, "failed")
        self.assertIn("out_of_domain", result.diagnostic)
        self.assertIsNone(result.output_json)
        self.assertEqual(result.metrics, ())
        self.assertIn("1000000", result.inputs_json)

    # Effective payload preserves unknown wire counters through serialization, rather than using zero.
    def test_effective_profile_unknown_record(self):
        case = load_config(NetworkCase, CONFIG)
        values = parse_json(canonical_json(case))
        for item in values["configuration"]["graph"]["links"]:
            for name in ("line_rate_bps", "coding_efficiency", "max_payload_bytes", "header_bytes",
                         "trailer_bytes", "alignment_bytes"):
                item[name] = None
            item["rate_basis"] = "effective_payload"
            item["payload_bandwidth_Bps"] = 20e9
            item["capacity_kind"] = "effective_service"
        result = run_case(resolve_dataclass(NetworkCase, values))
        self.assertEqual(result.status, "succeeded", result.diagnostic)
        wire = next(metric for metric in result.metrics if metric.name == "link_frame_bytes")
        self.assertIsNone(wire.value)
        self.assertTrue(wire.unknown_reason)

    # Repeat calls are isolated; input/source changes affect experiment identity while host elapsed time does not.
    def test_identity_and_isolation(self):
        case = load_config(NetworkCase, CONFIG)
        before = canonical_json(case)
        first, second = run_case(case), run_case(case)
        self.assertNotEqual(first.run_id, second.run_id)
        self.assertEqual(first.identity_hash, second.identity_hash)
        self.assertEqual(first.output_json, second.output_json)
        self.assertEqual(canonical_json(case), before)
        self.assertNotEqual(first.identity_hash, run_case(replace(case, inputs=NetworkInputs(payload_bytes=1))).identity_hash)
        self.assertNotEqual(first.identity_hash, run_case(case, source_revision="another-source").identity_hash)

    # Saved evidence reconstructs the same summary; an existing directory cannot be overwritten.
    def test_artifact_roundtrip(self):
        result = run_case(load_config(NetworkCase, CONFIG), source_revision="test-source/v1")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "run"
            write_run(result, target)
            restored = RunRecord.from_dict(read_run(target))
            self.assertEqual(summarize(restored), summarize(result))
            with self.assertRaises(FileExistsError):
                write_run(result, target)

    # CLI save/read handles an explicit empty query and never silently ignores conflicting read-time overrides.
    def test_cli_save_read_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "run"
            command = [sys.executable, "-m", "example.network_demo"]
            saved = subprocess.run(command + ["--payload-bytes", "0", "--output", str(target)],
                                   cwd=ROOT, capture_output=True, text=True, check=True)
            restored = subprocess.run(command + ["--read", str(target)], cwd=ROOT,
                                      capture_output=True, text=True, check=True)
            self.assertEqual(parse_json(saved.stdout), parse_json(restored.stdout))
            invalid = subprocess.run(command + ["--read", str(target), "--payload-bytes", "1"],
                                     cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(invalid.returncode, 0)

    # Producer-derived properties and unsupported future switch fields cannot be injected through JSON.
    def test_strict_schema_fields(self):
        case = load_config(NetworkCase, CONFIG)
        values = parse_json(canonical_json(case))
        values["configuration"]["graph"]["links"][0]["service_capacity_Bps"] = 1
        with self.assertRaisesRegex(ValueError, "derived"):
            resolve_dataclass(NetworkCase, values)


if __name__ == "__main__":
    unittest.main()
