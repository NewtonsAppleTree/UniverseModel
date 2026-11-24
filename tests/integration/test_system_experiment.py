"""Node study configuration, complete failed attempts and source-bound static evidence replay."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json, parse_json
from evaluation.experiments.runner.system import NodeStudy, read_study, run_study, summarize_records, write_study


ROOT = Path(__file__).resolve().parents[2]  # Explicit local fixture; no target machine or external reference needed.


# A successful static route must remain distinct from successful data movement or known performance.
class NodeStudyTests(unittest.TestCase):
    # All tests consume the same immutable seven-case study and actual execution records.
    @classmethod
    def setUpClass(cls):
        cls.study = load_config(NodeStudy,ROOT/'config/experiments/system_connectivity.json')
        cls.records = run_study(cls.study,source_revision='system-test')

    # Four failure types remain separate, and successful routes do not invent zero target costs.
    def test_complete_roster_and_unknown_costs(self):
        rows = summarize_records(self.records)
        self.assertEqual(len(rows),7)
        self.assertTrue(all(row['expectation_met'] for row in rows))
        self.assertEqual({row['case'] for row in rows if row['status']=='failed'},
                         {'peer_reverse_denied','read_denied','hop_limit_failed','wrong_explicit_path'})
        for record in self.records:
            if record.status=='succeeded':
                self.assertEqual(next(m.value for m in record.metrics if m.name=='path_hops'),2)
                self.assertTrue(all(m.value is None and m.unknown_reason for m in record.metrics if m.name.startswith('target_')))
            else:
                self.assertIsNone(record.output_json)
                self.assertTrue(record.diagnostic)

    # Readback verifies declared paths but never invokes the producer or performs a new route search.
    def test_bundle_roundtrip_without_execution(self):
        with TemporaryDirectory() as root:
            destination = Path(root)/'node'
            write_study(self.records,destination)
            with patch('evaluation.experiments.runner.system.find_path',side_effect=AssertionError('searched')), \
                 patch('evaluation.experiments.runner.system._evaluate',side_effect=AssertionError('executed')):
                self.assertEqual(summarize_records(read_study(destination)),summarize_records(self.records))
            with self.assertRaises(FileExistsError):
                write_study(self.records,destination)
            index = parse_json((destination/'index.json').read_text(encoding='utf-8'))
            index['runs'][0]['directory']='../outside'
            (destination/'index.json').write_text(canonical_json(index),encoding='utf-8')
            with self.assertRaises(ValueError):
                read_study(destination)

    # Missing candidates, mixed source or modified inputs cannot reuse a complete study identity.
    def test_roster_source_and_request_guards(self):
        first = self.records[0]
        inputs = parse_json(first.inputs_json)
        inputs['request']['max_hops']+=1
        cases = (self.records[:-1],(*self.records,first),
                 (replace(first,spec=replace(first.spec,source_revision='other')),*self.records[1:]),
                 (replace(first,inputs_json=canonical_json(inputs)),*self.records[1:]))
        for records in cases:
            with self.assertRaises(ValueError):
                summarize_records(records)

    # Saved path fields and resource visits must follow the actual route; success with a null payload is rejected.
    def test_saved_path_integrity(self):
        position = next(i for i,r in enumerate(self.records) if r.status=='succeeded')
        first = self.records[position]
        for field in ('node_identity','constraint_visits','source_domain_id','link_ids','null'):
            payload = parse_json(first.output_json)
            if field=='node_identity':
                payload[field]='0'*64
            elif field=='constraint_visits':
                payload['path'][field]=[]
            elif field=='source_domain_id':
                payload['path'][field]='gpu1.address'
            elif field=='link_ids':
                payload['path'][field]=['host_to_rc']
            else:
                payload=None
            changed = list(self.records)
            changed[position]=replace(first,output_json=canonical_json(payload))
            with self.subTest(field=field),self.assertRaises(ValueError):
                summarize_records(tuple(changed))
        changed = list(self.records)
        changed[position]=replace(first,metrics=tuple(replace(m,value=3) if m.name=='path_hops' else m for m in first.metrics))
        with self.assertRaises(ValueError):
            summarize_records(tuple(changed))

    # A runtime path failure remains visible even when a fixture expected success; the complete roster is retained.
    def test_unexpected_failures_are_not_silenced(self):
        with patch('evaluation.experiments.runner.system.find_path',side_effect=ValueError('injected unavailable path')):
            records=run_study(self.study,source_revision='failure-test')
        rows=summarize_records(records)
        self.assertEqual(len(rows),7)
        self.assertTrue(all(r.status=='failed' for r in records))
        self.assertEqual(sum(not r['expectation_met'] for r in rows),3)

    # Config input cannot execute imports/formulas, override derived fields, or replace explicit permissions by protocol names.
    def test_strict_configuration(self):
        path=ROOT/'config/experiments/system_connectivity.json'
        for overrides in ({'node.device_ids':['invented']},{'node.topology.resources':[]},{'cases.0.request.max_hops':4}):
            with self.assertRaises((TypeError,ValueError)):
                load_config(NodeStudy,path,overrides=overrides)


if __name__=='__main__':
    unittest.main()
