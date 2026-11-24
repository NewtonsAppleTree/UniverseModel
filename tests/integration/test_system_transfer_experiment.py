"""Immutable S3 records retain complete candidate rosters and reject altered static traffic/bound observations."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json, parse_json
from evaluation.experiments.runner.system_transfer import TransferStudy, read_study, run_study, summarize_records, write_study


ROOT = Path(__file__).resolve().parents[2]  # Repository fixture, not a physical PCIe device or performance measurement.


# Records are verified as static evidence; successful production alone is not task quality or target performance.
class TransferStudyTests(unittest.TestCase):
    # Execute all immutable fixture cases once, including intentionally unavailable paths and invalid staging.
    @classmethod
    def setUpClass(cls):
        cls.study = load_config(TransferStudy,ROOT/'config/experiments/system_transfer.json')
        cls.records = run_study(cls.study,source_revision='transfer-test')

    # All seven positive and seven negative candidates remain visible; target execution and energy remain unknown.
    def test_complete_roster_and_metrics(self):
        rows = summarize_records(self.records)
        self.assertEqual(len(rows),14)
        self.assertEqual(sum(r['status']=='succeeded' for r in rows),7)
        self.assertTrue(all(r['expectation_met'] for r in rows))
        metrics = {r.spec.experiment_id:{m.name:m for m in r.metrics} for r in self.records if r.status=='succeeded'}
        self.assertEqual(metrics['direct']['payload_bytes'].value,metrics['staged']['payload_bytes'].value)
        self.assertEqual((metrics['direct']['copied_bytes'].value,metrics['staged']['copied_bytes'].value),(512,1024))
        self.assertEqual((metrics['direct']['pcie_frame_bytes'].value,metrics['staged']['pcie_frame_bytes'].value),(1120,2240))
        for result in metrics.values():
            self.assertEqual(result['known_service_lower_bound'].kind,'lower_bound')
            self.assertTrue(all(result[name].value is None and result[name].unknown_reason for name in ('target_execution_time','target_energy')))

    # Replay validates saved routes and deterministic ledgers without a new producer call or connectivity search.
    def test_roundtrip_without_execution(self):
        with TemporaryDirectory() as root:
            destination = Path(root)/'transfer'
            write_study(self.records,destination)
            with patch('evaluation.experiments.runner.system_transfer._evaluate',side_effect=AssertionError('executed')), \
                 patch('evaluation.experiments.runner.system_transfer.analyze_transfers',side_effect=AssertionError('producer')), \
                 patch('systemmodel.io.dma.analysis.find_path',side_effect=AssertionError('searched')):
                self.assertEqual(summarize_records(read_study(destination)),summarize_records(self.records))
            with self.assertRaises(FileExistsError):
                write_study(self.records,destination)
            index = parse_json((destination/'index.json').read_text(encoding='utf-8'))
            index['runs'][0]['directory']='../outside'
            (destination/'index.json').write_text(canonical_json(index),encoding='utf-8')
            with self.assertRaises(ValueError):
                read_study(destination)

    # Missing candidates, mixed source identities and altered inputs cannot masquerade as the same complete study.
    def test_roster_and_source_guards(self):
        first = self.records[0]
        inputs = parse_json(first.inputs_json)
        inputs['batch']['phase']=0
        cases = (self.records[:-1],(*self.records,first),
                 (replace(first,spec=replace(first.spec,source_revision='changed')),*self.records[1:]),
                 (replace(first,inputs_json=canonical_json(inputs)),*self.records[1:]))
        for records in cases:
            with self.assertRaises(ValueError):
                summarize_records(records)

    # Even rehashed payloads must conserve frame work, dependencies, staging identity and the actual stored path.
    def test_traffic_and_bound_tampering(self):
        position = next(i for i,r in enumerate(self.records) if r.spec.experiment_id=='staged')
        first = self.records[position]
        changes = ((('system_identity',),'0'*64),(('legs',0,'traffic','frame_bytes'),512),
                   (('legs',0,'dma','completion_cycles'),0),(('bounds','lower_bound_s'),0),
                   (('actions',1,'dependencies'),[]),(('staging_allocation_ids',),[]),
                   (('memory_work',2,'read_bytes'),0),(('legs',0,'path','link_ids'),['gpu0.tx','gpu1.rx']),
                   (('contributions',0,'amount'),0),(('unknown_costs',),[]))
        for path,value in changes:
            payload = parse_json(first.output_json)
            target = payload['analysis']
            for key in path[:-1]:
                target = target[key]
            target[path[-1]]=value
            altered = list(self.records)
            altered[position]=replace(first,output_json=canonical_json(payload))
            with self.subTest(path=path),self.assertRaises(ValueError):
                summarize_records(tuple(altered))
        for payload in (None,{'analysis':None},{'analysis':{'legs':[]}}):
            altered = list(self.records)
            altered[position]=replace(first,output_json=canonical_json(payload))
            with self.assertRaises(ValueError):
                summarize_records(tuple(altered))

    # A partial service bound cannot be relabeled as simulated runtime; unknown physical energy cannot become zero.
    def test_metric_integrity(self):
        first = self.records[0]
        for name,change in (('copied_bytes',{'value':0}),('known_service_lower_bound',{'kind':'estimated'}),
                            ('target_energy',{'value':0,'unknown_reason':None})):
            changed = replace(first,metrics=tuple(replace(m,**change) if m.name==name else m for m in first.metrics))
            with self.assertRaises(ValueError):
                summarize_records((changed,*self.records[1:]))

    # Unexpected failures remain recorded and break expectations; malformed derived-field overrides are rejected.
    def test_failure_retention_and_configuration(self):
        with patch('evaluation.experiments.runner.system_transfer._evaluate',side_effect=ValueError('injected unavailable service')):
            records = run_study(self.study,source_revision='failure-test')
        rows = summarize_records(records)
        self.assertEqual(sum(not r['expectation_met'] for r in rows),7)
        self.assertTrue(all(r.status=='failed' and r.diagnostic for r in records))
        for overrides in ({'system.identity_hash':'invented'},{'system.profile.max_payload_bytes':64},{'cases.0.batch.phase':2}):
            with self.assertRaises((ValueError,TypeError)):
                load_config(TransferStudy,ROOT/'config/experiments/system_transfer.json',overrides=overrides)


if __name__=='__main__':
    unittest.main()
