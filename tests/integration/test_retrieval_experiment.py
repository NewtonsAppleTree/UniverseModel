"""Held-out task quality, paired numeric ablations, external baselines and data-free replay."""

from dataclasses import replace
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json,parse_json
from evaluation.experiments.runner.retrieval import read_study,run_study,summarize_records,write_study
from workloads.profiles.retrieval import RetrievalProfile


ROOT = Path(__file__).resolve().parents[2]  # Real dataset fixture remains local and content-addressed.


# Task metrics and numerical correctness have separate assertions and negative controls.
class RetrievalStudyTests(unittest.TestCase):
    # Materialize the complete immutable study once for integrity and paired-result tests.
    @classmethod
    def setUpClass(cls):
        cls.profile = load_config(RetrievalProfile,ROOT/'config/experiments/retrieval_quality.json')
        cls.records = run_study(cls.profile,data_root=ROOT/'config/workloads',source_revision='quality-test')

    # Three fixed real-data splits preserve 90/30/30 ownership and show both acceptable variants and rejected controls.
    def test_complete_quality_evidence(self):
        rows = {r['case']:r for r in summarize_records(self.records)}
        self.assertEqual(len(rows),12)
        self.assertTrue(all(r['status']=='succeeded' and r['expectation_met'] for r in rows.values()))
        for seed,correct in ((0,28),(1,29),(2,27)):
            base = rows[f'seed{seed}:baseline']['result']
            self.assertEqual((base['metrics']['samples'],base['metrics']['correct']),(30,correct))
            coarse = rows[f'seed{seed}:keys_coarse_control']['result']
            self.assertFalse(coarse['quality_passed'])
            self.assertTrue(coarse['numerical']['passed'])
            self.assertEqual(coarse['metrics']['correct'],10)
            self.assertEqual(rows[f'seed{seed}:keys_round_12']['result']['prediction_changes'],0)
        for record in self.records:
            prepared = parse_json(record.inputs_json)
            split = prepared['state']['split']
            self.assertEqual([len(split[k]) for k in ('train','validation','test')],[90,30,30])
            self.assertEqual(len(prepared['validation_scores']),3)
            self.assertIsNone(next(m for m in record.metrics if m.name=='target_energy').value)

    # A requested unavailable library and missing source become complete failure rosters, never silent quality passes.
    def test_source_and_external_failure_records(self):
        profile = replace(self.profile,seeds=(0,))
        missing = run_study(profile,data_root=ROOT/'not-a-dataset')
        self.assertTrue(all(r.status=='failed' and parse_json(r.inputs_json)['data'] is None for r in missing))
        self.assertFalse(any(r['expectation_met'] for r in summarize_records(missing)))
        with patch('evaluation.experiments.runner.retrieval.numpy_environment',side_effect=ImportError('missing optional numpy')):
            failed = run_study(profile,data_root=ROOT/'config/workloads',numpy_reference=True)
        self.assertTrue(all(r.status=='failed' and 'numpy' in r.diagnostic for r in failed))
        self.assertFalse(any(r['expectation_met'] for r in summarize_records(failed)))

    # Replay needs neither external libraries, model execution nor the source dataset; original observations suffice.
    def test_roundtrip_without_data_or_models(self):
        with TemporaryDirectory() as root:
            path = Path(root)/'quality'
            write_study(self.records,path)
            with patch('evaluation.experiments.runner.retrieval.load_classification',side_effect=AssertionError('loaded data')), \
                 patch('evaluation.experiments.runner.retrieval.prepare_retrieval',side_effect=AssertionError('fit model')), \
                 patch('evaluation.experiments.runner.retrieval.reference_attention',side_effect=AssertionError('ran reference')), \
                 patch('evaluation.experiments.runner.retrieval.numpy_environment',side_effect=AssertionError('loaded numpy')):
                self.assertEqual(summarize_records(read_study(path)),summarize_records(self.records))
            with self.assertRaises(FileExistsError):
                write_study(self.records,path)

    # Saved quality must agree with actual probabilities/truth and exact threshold rules; source changes cannot be mixed.
    def test_metric_identity_and_roster_guards(self):
        first = self.records[0]
        payload = parse_json(first.output_json)
        bad_metric = {**payload,'metrics':{**payload['metrics'],'correct':0}}
        bad_gate = {**payload,'quality_passed':False}
        bad_input = parse_json(first.output_json)
        bad_input['attention_inputs']['q'][0] += 1.
        variants = [self.records[:-1],(*self.records,first),
                    (replace(first,spec=replace(first.spec,source_revision='other')),*self.records[1:])]
        variants += [(replace(first,output_json=canonical_json(p)),*self.records[1:]) for p in (bad_metric,bad_gate,bad_input)]
        for records in variants:
            with self.assertRaises(ValueError):
                summarize_records(records)

    # Replay derives numerical evidence and prediction changes instead of trusting producer flags or counters.
    def test_saved_evidence_guards(self):
        first = self.records[0]
        for field in ('reference_output','numerical','prediction_changes','plan','missing_reference'):
            payload = parse_json(first.output_json)
            if field=='reference_output':
                payload[field][0] += .1
            elif field=='numerical':
                payload[field]['passed'] = 'false'
            elif field=='prediction_changes':
                payload[field] += 1
            elif field=='plan':
                payload[field]['blocks'].pop()
            else:
                del payload['reference_output']
            with self.subTest(field=field),self.assertRaises(ValueError):
                summarize_records((replace(first,output_json=canonical_json(payload)),*self.records[1:]))
        prepared = parse_json(first.inputs_json)
        prepared['validation_scores'][0][1]['accuracy'] = .123
        changed = tuple(replace(r,inputs_json=canonical_json(prepared)) if parse_json(r.configuration_json)['seed']==0 else r for r in self.records)
        with self.assertRaisesRegex(ValueError,'validation metrics'):
            summarize_records(changed)

    # The existing v1 evidence remains readable with structural checks, without claiming a regenerated numerical comparison.
    def test_legacy_retrieval_records(self):
        legacy = []
        for record in self.records:
            payload = parse_json(record.output_json)
            del payload['reference_output']
            legacy.append(replace(record,spec=replace(record.spec,implementation_id='retrieval-quality/v1'),output_json=canonical_json(payload)))
        self.assertTrue(all(row['expectation_met'] for row in summarize_records(tuple(legacy))))

    # The optional external evidence uses both matmul and direct squared-distance formulas, with recorded actual version.
    @unittest.skipUnless(find_spec('numpy') is not None,'optional NumPy is not installed')
    def test_numpy_independent_reference(self):
        profile = replace(self.profile,seeds=(0,))
        records = run_study(profile,data_root=ROOT/'config/workloads',source_revision='numpy-test',numpy_reference=True)
        for row in summarize_records(records):
            self.assertTrue(row['expectation_met'],row['diagnostic'])
            self.assertTrue(row['result']['external']['rbf_validation']['passed'])
        config = parse_json(records[0].configuration_json)
        self.assertTrue(config['external_environment']['numpy_version'])
        for field in ('attention_validation','rbf_output','rbf_metrics'):
            payload = parse_json(records[0].output_json)
            if field=='attention_validation':
                payload['external'][field]['passed'] = 'false'
            elif field=='rbf_output':
                payload['external'][field][0] += .1
            else:
                payload['external'][field]['accuracy'] = 0.
            with self.subTest(field=field),self.assertRaises(ValueError):
                summarize_records((replace(records[0],output_json=canonical_json(payload)),*records[1:]))


if __name__=='__main__':
    unittest.main()
