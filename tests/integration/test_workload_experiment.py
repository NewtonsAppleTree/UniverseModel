"""Attention study completeness, actual input retention and replay without model/data execution."""

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json, parse_json
from evaluation.experiments.runner.workload import read_study, run_study, summarize_records, write_study
from example.workload_demo import comparison_exit_status
from workloads.profiles.attention import AttentionSuite


ROOT = Path(__file__).resolve().parents[2]  # Repository config/data sources; no external service required.


# Reproducible semantic experiments preserve successes, source failures and unknown hardware costs separately.
class AttentionExperimentTests(unittest.TestCase):
    # Share immutable baseline records across integrity tests; changing a snapshot requires explicit replacement.
    @classmethod
    def setUpClass(cls):
        cls.suite = load_config(AttentionSuite, ROOT / 'config/experiments/attention_workloads.json')
        cls.records = run_study(cls.suite, data_root=ROOT / 'config/workloads', source_revision='workloads-test')

    # Hand fixture output and complete status roster give evidence beyond merely running a callback.
    def test_roster_hand_result_and_unknown_costs(self):
        rows = {r['case']: r for r in summarize_records(self.records)}
        self.assertEqual((len(rows), sum(r.status == 'succeeded' for r in self.records)), (10, 7))
        self.assertEqual(comparison_exit_status(tuple(rows.values())), 0)
        self.assertEqual(rows['dataset_uniform']['result']['reference']['output'], [1., 2., 3., 3., 4., 5.] * 2)
        self.assertEqual([rows[f'prefill_{kind}']['result']['work']['kv_bytes'] for kind in ('mha', 'gqa', 'mqa')], [640, 320, 160])
        for record in self.records:
            if record.status == 'succeeded':
                for name in ('target_execution_time', 'target_energy'):
                    metric = next(m for m in record.metrics if m.name == name)
                    self.assertIsNone(metric.value)
                    self.assertTrue(metric.unknown_reason)
                self.assertNotIn('passed', parse_json(record.output_json))

    # Failed source preparation has no invented data; a reference-budget failure retains its prepared tensors.
    def test_failures_retain_inputs_and_provenance(self):
        records = {r.spec.experiment_id: r for r in self.records}
        for name in ('host_limit_failed', 'dataset_hash_failed'):
            r = records[name]
            snapshot = parse_json(r.inputs_json)
            self.assertIsNone(snapshot['data'])
            self.assertTrue(snapshot['error'])
            self.assertIsNone(r.output_json)
            self.assertFalse(r.metrics)
        r = records['reference_limit_failed']
        self.assertIsNotNone(parse_json(r.inputs_json)['data'])
        self.assertIsNone(parse_json(r.inputs_json)['error'])
        self.assertIn('max_score_pairs', r.diagnostic)
        saved = parse_json(records['dataset_uniform'].configuration_json)
        dataset = next(c['dataset'] for c in saved['suite']['cases'] if c['name'] == 'dataset_uniform')
        self.assertTrue(all(dataset[k] for k in ('source', 'sha256', 'usage_terms', 'limitations')))

    # Regeneration matches identities/outputs; read-only replay works with all compute and input loaders disabled.
    def test_reproducibility_and_no_execution_replay(self):
        repeated = run_study(self.suite, data_root=ROOT / 'config/workloads', source_revision='workloads-test')
        self.assertEqual(summarize_records(self.records), summarize_records(repeated))
        with TemporaryDirectory() as root:
            path = Path(root) / 'study'
            write_study(self.records, path)
            with patch('evaluation.experiments.runner.workload.reference_attention', side_effect=AssertionError('reference invoked')), \
                 patch('workloads.profiles.attention.generate_attention', side_effect=AssertionError('generation invoked')), \
                 patch('workloads.profiles.attention.load_attention_dataset', side_effect=AssertionError('dataset invoked')):
                self.assertEqual(summarize_records(read_study(path)), summarize_records(self.records))
            with self.assertRaises(FileExistsError):
                write_study(self.records, path)

    # Omissions, duplicate attempts, mixed source/suite and modified inputs cannot become a complete study.
    def test_identity_and_completeness_guards(self):
        a = self.records
        config = parse_json(a[0].configuration_json)
        config['suite']['source_note'] = 'foreign source'
        data = parse_json(a[0].inputs_json)
        data['data']['q'][0] += 1.0
        changes = (replace(a[0], spec=replace(a[0].spec, source_revision='foreign')),
                   replace(a[0], configuration_json=canonical_json(config)),
                   replace(a[0], inputs_json=canonical_json(data)), replace(a[0], run_id=a[1].run_id))
        for records in (a[:-1], (*a, a[0]), *((bad, *a[1:]) for bad in changes)):
            with self.assertRaises(ValueError):
                summarize_records(records)

    # Producer payloads still require real reference observations with the expected shape and numeric domain.
    def test_output_schema_and_domain_guards(self):
        first = self.records[0]
        base = parse_json(first.output_json)
        for payload in (None, {}, {**base, 'reference': {}},
                        {**base, 'reference': {**base['reference'], 'output': [0.0]}},
                        {**base, 'reference': {**base['reference'], 'probabilities': [-1.0] * len(base['reference']['probabilities'])}}):
            changed = replace(first, output_json=canonical_json(payload))
            with self.assertRaises(ValueError):
                summarize_records((changed, *self.records[1:]))

    # Index guards prevent arbitrary paths and missing cases; bundle hash rejects modified output bytes.
    def test_bundle_integrity(self):
        with TemporaryDirectory() as root:
            path = Path(root) / 'study'
            write_study(self.records, path)
            index_path = path / 'index.json'
            original = index_path.read_text(encoding='utf-8')
            index = parse_json(original)
            index['runs'] = index['runs'][:-1]
            index_path.write_text(canonical_json(index), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                read_study(path)
            index = parse_json(original)
            index['runs'][0]['directory'] = '../outside'
            index_path.write_text(canonical_json(index), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'path'):
                read_study(path)
            index_path.write_text(original, encoding='utf-8')
            run = path / 'run-0000/run.json'
            run.write_bytes(run.read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                read_study(path)

    # CLI emits identical saved/read observations and unexpected fixture outcomes fail the process status.
    def test_cli_and_status(self):
        with TemporaryDirectory() as root:
            path = Path(root) / 'study'
            command = [sys.executable, '-m', 'example.workload_demo']
            saved = subprocess.run(command + ['--output', str(path)], cwd=ROOT, capture_output=True, text=True, check=True)
            read = subprocess.run(command + ['--read', str(path), '--data-root', str(path / 'missing')],
                                  cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertEqual(parse_json(saved.stdout), parse_json(read.stdout))
            bad = replace(self.suite, cases=(replace(self.suite.cases[0], expected_status='failed'),))
            config = Path(root) / 'bad.json'
            config.write_text(canonical_json(bad), encoding='utf-8')
            result = subprocess.run(command + ['--config', str(config)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(comparison_exit_status(()), 1)
        self.assertEqual(comparison_exit_status(({'expectation_met': False},)), 1)


if __name__ == '__main__':
    unittest.main()
