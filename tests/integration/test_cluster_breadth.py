"""Expanded topology/demand observations and static outage provenance through the existing runner."""

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import load_config, resolve_dataclass
from contracts.versions.json_codec import canonical_json, parse_json
from clustermodel.topology.scenarios import NetworkOutage
from evaluation.experiments.runner.cluster import ClusterStudy, read_study, run_study, summarize_records, write_study


ROOT = Path(__file__).resolve().parents[2]  # Shared repository root for CLI checks.
CONFIG = ROOT / "config/experiments/cluster_leaf_spine.json"  # Six-node synthetic demand-matrix fixture.


# The horizontal features reuse run records, including explicit unknowns and candidate failures.
class ClusterBreadthIntegrationTests(unittest.TestCase):
    # Resolve every input through strict producer dataclasses and keep source/version metadata explicit.
    def setUp(self):
        self.study = load_config(ClusterStudy, CONFIG)

    # Wider topology and workload descriptions are stored alongside the existing analytical ledger.
    def test_saved_overview_and_reference(self):
        records = run_study(self.study, source_revision="breadth-test/v1")
        record = records[0]
        self.assertEqual(record.status, "succeeded", record.diagnostic)
        row = summarize_records(records, include_overview=True)[0]
        self.assertEqual(row["network_overview"]["directed_link_count"], 24)
        self.assertEqual(row["traffic_description"]["logical_payload_bytes"], 31457280)
        self.assertEqual(row["traffic_description"]["message_count"], 30)
        self.assertEqual(len(row["traffic_description"]["node_matrix"]), 30)
        self.assertEqual(row["link_frame_bytes"], 113246208)
        self.assertIsNone(row["outage_view"])
        self.assertTrue(all(metric.kind == "lower_bound" for metric in record.metrics if metric.unit == "second"))

    # A surviving spine changes routes but not installed budget; input snapshots retain both original graph and outage.
    def test_outage_snapshots_and_alternative_route(self):
        study = replace(self.study, outage=NetworkOutage(source_ref="maintenance/test-v1", disabled_switch_ids=("s0",)))
        record = run_study(study)[0]
        self.assertEqual(record.status, "succeeded", record.diagnostic)
        configuration = parse_json(record.configuration_json)
        result = parse_json(record.output_json)
        self.assertEqual(len(configuration["graph"]["links"]), 24)
        self.assertEqual(configuration["outage"]["source_ref"], "maintenance/test-v1")
        self.assertEqual(result["network_overview"]["directed_link_count"], 18)
        self.assertEqual(len(result["outage_view"]["removed_link_ids"]), 6)
        route = next(item["route"]["link_ids"] for item in result["messages"] if item["message_id"] == "m0-2")
        self.assertEqual(route, ["e0->l0", "l0->s1", "s1->l1", "l1->e2"])
        self.assertAlmostEqual(result["resource_time_lower_bound_s"], 0.00067108864, delta=1e-18)
        self.assertNotEqual(record.identity_hash, run_study(self.study)[0].identity_hash)

    # An unavailable fabric leaves the original demand intact and round-trips a failed record with no fake target metrics.
    def test_unreachable_failure_roundtrip(self):
        study = replace(self.study, outage=NetworkOutage(source_ref="test/v1", disabled_switch_ids=("s0", "s1")))
        records = run_study(study)
        self.assertEqual(records[0].status, "failed")
        self.assertIn("unreachable", records[0].diagnostic)
        self.assertEqual(len(parse_json(records[0].inputs_json)["messages"]), 30)
        self.assertIsNone(records[0].output_json)
        self.assertEqual(records[0].metrics, ())
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "failed"
            write_study(records, target)
            self.assertEqual(summarize_records(read_study(target), include_overview=True),
                             summarize_records(records, include_overview=True))

    # Unknown selectors are recorded as failures; temporal fault fields cannot enter the static outage schema.
    def test_outage_validation_and_schema(self):
        study = replace(self.study, outage=NetworkOutage(source_ref="test/v1", disabled_switch_ids=("unknown",)))
        record = run_study(study)[0]
        self.assertEqual(record.status, "failed")
        self.assertIn("unknown identities", record.diagnostic)
        payload = parse_json(canonical_json(self.study))
        payload["outage"] = {"source_ref": "test/v1", "disabled_switch_ids": ["s0"]}
        resolved = resolve_dataclass(ClusterStudy, payload)
        self.assertEqual(resolved.outage.disabled_switch_ids, ("s0",))
        payload["outage"]["repair_time_s"] = 5
        with self.assertRaises((ValueError, TypeError)):
            resolve_dataclass(ClusterStudy, payload)

    # Reading earlier payloads exposes absent overviews without rerunning a newer model or changing saved conclusions.
    def test_older_payload_without_overview(self):
        record = run_study(self.study)[0]
        payload = parse_json(record.output_json)
        for name in ("network_overview", "traffic_description", "outage_view"):
            payload.pop(name)
        old = replace(record, output_json=canonical_json(payload))
        with patch("evaluation.experiments.runner.cluster.analyze_traffic", side_effect=AssertionError("must not rerun")):
            row = summarize_records((old,), include_overview=True)[0]
        self.assertIsNone(row["network_overview"])
        self.assertIsNone(row["traffic_description"])
        self.assertEqual(row["link_frame_bytes"], 113246208)

    # Overview is a display option compatible with replay, and identical saved views require no current input file.
    def test_cli_overview_save_read(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "study"
            command = [sys.executable, "-m", "example.cluster_demo"]
            saved = subprocess.run(command + ["--config", str(CONFIG), "--overview", "--output", str(target)],
                                   cwd=ROOT, capture_output=True, text=True, check=True)
            restored = subprocess.run(command + ["--read", str(target), "--overview"],
                                      cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertEqual(parse_json(saved.stdout), parse_json(restored.stdout))
            self.assertEqual(parse_json(restored.stdout)[0]["network_overview"]["switch_count"], 5)


if __name__ == "__main__":
    unittest.main()
