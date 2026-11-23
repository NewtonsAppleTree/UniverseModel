"""Cluster study configuration, complete candidate evidence and immutable replay."""

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import load_config, resolve_dataclass
from contracts.versions.json_codec import canonical_json, parse_json
from evaluation.experiments.runner.cluster import ClusterStudy, read_study, run_study, summarize_records, write_study


ROOT = Path(__file__).resolve().parents[2]  # Repository root for independent CLI execution.
CONFIG = ROOT / "config/experiments/cluster_placement.json"  # Shared fixed-budget comparison.


# Saved observations retain the entire candidate roster, failed attempts and all physical-cost unknowns.
class ClusterExperimentTests(unittest.TestCase):
    # Resolve explicit nested frozen dataclasses through the same public configuration path used by the CLI.
    def setUp(self):
        self.study = load_config(ClusterStudy, CONFIG)

    # All target times are lower_bound metrics; zero latency assumptions and missing energy remain distinguishable.
    def test_known_comparison_and_metric_kinds(self):
        records = run_study(self.study, source_revision="test-source/v1")
        rows = summarize_records(records)
        self.assertEqual([row["status"] for row in rows], ["succeeded", "succeeded"])
        self.assertAlmostEqual(rows[0]["resource_lower_bound_s"], 0.02147483648, delta=1e-17)
        self.assertAlmostEqual(rows[1]["resource_lower_bound_s"], 0.00536870912, delta=1e-17)
        for record in records:
            self.assertEqual(record.spec.mode, "analytical")
            self.assertTrue(all(metric.kind == "lower_bound" for metric in record.metrics if metric.unit == "second"))
            self.assertFalse(any("host" in metric.name for metric in record.metrics))
            energy = next(metric for metric in record.metrics if metric.name == "network_energy")
            self.assertIsNone(energy.value)
            self.assertTrue(energy.unknown_reason)
            self.assertIn("fixture/v1", record.inputs_json)

    # Relational placement failure is recorded after snapshotting, while the successful candidate still completes.
    def test_failed_candidate_preserved(self):
        bad = replace(self.study.candidates[1], placements=tuple(replace(item, endpoint_id="ghost")
                      if item.rank_id == "r0" else item for item in self.study.candidates[1].placements))
        records = run_study(replace(self.study, candidates=(self.study.candidates[0], bad)))
        self.assertEqual([record.status for record in records], ["succeeded", "failed"])
        self.assertIn("unknown endpoint", records[1].diagnostic)
        self.assertIn("ghost", records[1].configuration_json)
        self.assertEqual(records[1].metrics, ())
        self.assertIsNone(records[1].output_json)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "failed-study"
            write_study(records, target)
            self.assertEqual(summarize_records(read_study(target)), summarize_records(records))

    # Runtime route/profile failures never acquire fake lower bounds or success-only evidence.
    def test_local_and_out_of_profile_failures(self):
        local = replace(self.study.traffic.messages[0], dst_rank="r0")
        for study, diagnostic in ((replace(self.study, traffic=replace(self.study.traffic, messages=(local,))), "unsupported_local_path"),
                                  (replace(self.study, graph=replace(self.study.graph, links=tuple(
                                      replace(item, profile_max_payload_bytes=64) for item in self.study.graph.links))), "out_of_domain")):
            records = run_study(study)
            self.assertTrue(all(record.status == "failed" and diagnostic in record.diagnostic for record in records))
            self.assertTrue(all(not record.metrics and record.output_json is None for record in records))

    # Canonical snapshots isolate repeated execution; data/source changes alter identity while host time does not.
    def test_determinism_and_provenance(self):
        before = canonical_json(self.study)
        first, second = run_study(self.study), run_study(self.study)
        self.assertEqual([item.identity_hash for item in first], [item.identity_hash for item in second])
        self.assertEqual([item.output_json for item in first], [item.output_json for item in second])
        self.assertNotEqual(first[0].run_id, second[0].run_id)
        self.assertEqual(canonical_json(self.study), before)
        self.assertNotEqual(first[0].identity_hash, run_study(self.study, source_revision="different/v1")[0].identity_hash)
        traffic = replace(self.study.traffic, messages=tuple(replace(item, content_version="changed/v2") for item in self.study.traffic.messages))
        self.assertNotEqual(first[0].identity_hash, run_study(replace(self.study, traffic=traffic))[0].identity_hash)

    # Replay verifies immutable data and does not invoke analysis; an existing study directory is never overwritten.
    def test_roundtrip_without_execution(self):
        records = run_study(self.study)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "study"
            write_study(records, target)
            with patch("evaluation.experiments.runner.cluster.analyze_traffic", side_effect=AssertionError("must not rerun")):
                self.assertEqual(summarize_records(read_study(target)), summarize_records(records))
            with self.assertRaises(FileExistsError):
                write_study(records, target)

    # Missing candidates and mixed versions/inputs cannot be silently presented as the original fair comparison.
    def test_roster_and_mixed_study_rejection(self):
        records = run_study(self.study)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            summarize_records(records[:1])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            summarize_records((records[0], records[0]))
        other = run_study(self.study, source_revision="other/v1")
        with self.assertRaisesRegex(ValueError, "mixed"):
            summarize_records((records[0], other[1]))

    # A self-consistent JSON snapshot can still contain a duplicate roster; replay must reject this ambiguity.
    def test_snapshot_roster_and_attempt_identity(self):
        records = run_study(self.study)
        modified = []
        for record in records:
            configuration = parse_json(record.configuration_json)
            configuration["candidates"].append(configuration["candidates"][0])
            modified.append(replace(record, configuration_json=canonical_json(configuration)))
        with self.assertRaisesRegex(ValueError, "duplicate.*roster"):
            summarize_records(tuple(modified))
        with self.assertRaisesRegex(ValueError, "duplicate cluster run_id"):
            summarize_records((records[0], replace(records[1], run_id=records[0].run_id)))

    # Unsupported snapshot/index fields cannot silently acquire current-version replay semantics.
    def test_replay_schema_validation(self):
        records = run_study(self.study)
        configuration = parse_json(records[0].configuration_json)
        configuration["schema_version"] = "future/v2"
        with self.assertRaisesRegex(ValueError, "configuration snapshot"):
            summarize_records((replace(records[0], configuration_json=canonical_json(configuration)), records[1]))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "study"
            write_study(records, target)
            index_file = target / "index.json"
            index = parse_json(index_file.read_text(encoding="utf-8"))
            index["ignored"] = True
            index_file.write_text(canonical_json(index), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported cluster study index"):
                read_study(target)

    # The final index and each bundle are required; paths cannot escape the study or omit the failed roster member.
    def test_index_integrity_and_path_validation(self):
        records = run_study(self.study)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "study"
            write_study(records, target)
            index_file = target / "index.json"
            index = parse_json(index_file.read_text(encoding="utf-8"))
            index_file.write_text(canonical_json({**index, "runs": index["runs"][:1]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                read_study(target)
            index["runs"][0]["directory"] = "../elsewhere"
            index_file.write_text(canonical_json(index), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "path/order"):
                read_study(target)

    # Modifying saved result bytes fails the underlying manifest hash before a summary is reconstructed.
    def test_bundle_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "study"
            write_study(run_study(self.study), target)
            run = target / "run-0000" / "run.json"
            run.write_text(run.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                read_study(target)

    # Schema rejects unsupported arrival/dependency semantics and derived hardware overrides rather than ignoring them.
    def test_strict_configuration(self):
        for key, value in (("arrival_s", 1), ("executable", "import os")):
            payload = parse_json(canonical_json(self.study))
            payload["traffic"]["messages"][0][key] = value
            with self.assertRaises(ValueError):
                resolve_dataclass(ClusterStudy, payload)
        payload = parse_json(canonical_json(self.study))
        payload["graph"]["links"][0]["service_capacity_Bps"] = 1
        with self.assertRaisesRegex(ValueError, "derived"):
            resolve_dataclass(ClusterStudy, payload)

    # CLI save/read produces the same comparison; read-time edits and unknown options fail clearly.
    def test_cli_save_read_and_empty_work(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "study"
            command = [sys.executable, "-m", "example.cluster_demo"]
            saved = subprocess.run(command + ["--set", "traffic.messages=[]", "--output", str(target)],
                                   cwd=ROOT, capture_output=True, text=True, check=True)
            restored = subprocess.run(command + ["--read", str(target)], cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertEqual(parse_json(saved.stdout), parse_json(restored.stdout))
            self.assertTrue(all(row["communication_lower_bound_s"] == 0 for row in parse_json(saved.stdout)))
            invalid = subprocess.run(command + ["--read", str(target), "--source-revision", "ignored"],
                                     cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(invalid.returncode, 0)


if __name__ == "__main__":
    unittest.main()
