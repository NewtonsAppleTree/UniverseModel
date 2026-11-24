"""Saved S4 evidence conserves finite capacity, transient copies and method-specific transport semantics."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json, parse_json
from evaluation.experiments.runner.system_tiering import TierStudy, read_study, run_study, summarize_records, write_study


ROOT = Path(__file__).resolve().parents[2]  # Synthetic repository fixture, not a physical CXL measurement.


# Static records prove only declared feasibility and work; neither coherence completion nor target runtime is inferred.
class TierStudyTests(unittest.TestCase):
    # Keep all candidate attempts, including invalid protocol, capacity and migration declarations.
    @classmethod
    def setUpClass(cls):
        cls.study = load_config(TierStudy,ROOT/'config/experiments/system_tiering.json')
        cls.records = run_study(cls.study,source_revision='tiering-test')

    # Fixed hardware/demand comparisons retain failures and distinguish native unknown timing from a DMA partial bound.
    def test_complete_roster_and_metrics(self):
        rows = summarize_records(self.records)
        self.assertEqual(len(rows),15)
        self.assertEqual(sum(r['status']=='succeeded' for r in rows),7)
        self.assertTrue(all(r['expectation_met'] for r in rows))
        metrics = {r.spec.experiment_id:{m.name:m for m in r.metrics} for r in self.records if r.status=='succeeded'}
        self.assertEqual(metrics['expanded_residency']['initial_reserved_bytes'].value,1024)
        self.assertEqual(metrics['partial_read_1B']['cxl_data_bytes'].value,64)
        for name in ('promote','replicate','demote'):
            self.assertEqual(metrics[name]['additional_reserved_bytes'].value,256)
            self.assertIsNone(metrics[name]['known_service_lower_bound'].value)
            self.assertTrue(metrics[name]['known_service_lower_bound'].unknown_reason)
        self.assertAlmostEqual(metrics['dma_to_accelerator']['known_service_lower_bound'].value,256e-9)
        for result in metrics.values():
            self.assertTrue(all(result[name].value is None and result[name].unknown_reason for name in ('target_execution_time','target_energy')))

    # Roundtrip revalidates saved paths and observations without a producer callback or replacement route search.
    def test_roundtrip_without_execution(self):
        with TemporaryDirectory() as root:
            destination = Path(root)/'tiering'
            write_study(self.records,destination)
            with patch('evaluation.experiments.runner.system_tiering._evaluate',side_effect=AssertionError('executed')), \
                 patch('evaluation.experiments.runner.system_tiering.analyze_cxl_access',side_effect=AssertionError('producer')), \
                 patch('evaluation.experiments.runner.system_tiering.analyze_cxl_migration',side_effect=AssertionError('producer')), \
                 patch('evaluation.experiments.runner.system_tiering.analyze_dma_migration',side_effect=AssertionError('producer')), \
                 patch('systemmodel.memory.access.find_path',side_effect=AssertionError('searched')), \
                 patch('systemmodel.io.dma.analysis.find_path',side_effect=AssertionError('searched')):
                self.assertEqual(summarize_records(read_study(destination)),summarize_records(self.records))
            with self.assertRaises(FileExistsError):
                write_study(self.records,destination)
            index = parse_json((destination/'index.json').read_text(encoding='utf-8'))
            index['runs'][0]['directory']='../outside'
            (destination/'index.json').write_text(canonical_json(index),encoding='utf-8')
            with self.assertRaises(ValueError):
                read_study(destination)

    # Missing attempts, source mixing or changed phase inputs invalidate a complete comparison.
    def test_roster_source_and_input_guards(self):
        first = self.records[0]
        inputs = parse_json(first.inputs_json)
        inputs['case']['phase']=0
        cases = (self.records[:-1],(*self.records,first),
                 (replace(first,spec=replace(first.spec,source_revision='changed')),*self.records[1:]),
                 (replace(first,inputs_json=canonical_json(inputs)),*self.records[1:]))
        for records in cases:
            with self.assertRaises(ValueError):
                summarize_records(records)

    # Rehashed observations still must agree with unique capacities, native lines, overlap storage and saved transport work.
    def test_capacity_access_and_migration_tampering(self):
        changes = (
            ('expanded_residency',('residency','tiers',0,'capacity_bytes'),0),
            ('expanded_residency',('residency','tiers',0,'reserved_bytes'),1),
            ('native_read',('access','line_count'),1),
            ('native_read',('access','window_id'),'invented'),
            ('native_read',('access','access','path','link_ids'),[]),
            ('partial_read_1B',('access','extra_data_bytes'),0),
            ('promote',('migration','transition','additional_reserved_bytes'),0),
            ('promote',('migration','transition','during','tiers',0,'reserved_bytes'),1),
            ('promote',('migration','transition','after','plan_identity'),'0'*64),
            ('promote',('migration','method'),'dma'),
            ('promote',('migration','local_span','allocation_id'),'invented'),
            ('promote',('migration','known_service_lower_bound_s'),0),
            ('promote',('migration','unknown_costs'),[]),
            ('dma_to_accelerator',('migration','dma','legs',0,'traffic','frame_bytes'),256),
            ('dma_to_accelerator',('migration','dma','bounds','lower_bound_s'),0),
            ('dma_to_accelerator',('migration','dma','legs',0,'path','link_ids'),[]),
        )
        for name,path,value in changes:
            position = next(i for i,r in enumerate(self.records) if r.spec.experiment_id==name)
            first = self.records[position]
            payload = parse_json(first.output_json)
            target = payload
            for key in path[:-1]:
                target = target[key]
            target[path[-1]]=value
            altered = list(self.records)
            altered[position]=replace(first,output_json=canonical_json(payload))
            with self.subTest(name=name,path=path),self.assertRaises(ValueError):
                summarize_records(tuple(altered))
        position = next(i for i,r in enumerate(self.records) if r.spec.experiment_id=='promote')
        for payload in (None,{'residency':None,'access':None,'migration':{}},
                        {'residency':None,'access':None,'migration':{'cxl_access':None}}):
            altered = list(self.records)
            altered[position]=replace(altered[position],output_json=canonical_json(payload))
            with self.assertRaises(ValueError):
                summarize_records(tuple(altered))

    # Unknown native service cannot become zero; a known DMA lower bound cannot become a runtime estimate.
    def test_metric_integrity(self):
        for case,name,change in (
            ('expanded_residency','initial_reserved_bytes',{'value':0}),
            ('promote','known_service_lower_bound',{'value':0,'unknown_reason':None}),
            ('dma_to_accelerator','known_service_lower_bound',{'kind':'estimated'}),
            ('native_read','target_energy',{'value':0,'unknown_reason':None}),
        ):
            position = next(i for i,r in enumerate(self.records) if r.spec.experiment_id==case)
            first = self.records[position]
            altered = list(self.records)
            altered[position]=replace(first,metrics=tuple(replace(m,**change) if m.name==name else m for m in first.metrics))
            with self.subTest(case=case,name=name),self.assertRaises(ValueError):
                summarize_records(tuple(altered))

    # Producer failures remain prior failed observations; configuration cannot override derived identities or introduce fields.
    def test_failure_retention_and_configuration(self):
        with patch('evaluation.experiments.runner.system_tiering._evaluate',side_effect=ValueError('injected unavailable service')):
            records = run_study(self.study,source_revision='failure-test')
        rows = summarize_records(records)
        self.assertEqual(sum(not r['expectation_met'] for r in rows),7)
        self.assertTrue(all(r.status=='failed' and r.diagnostic for r in records))
        for overrides in ({'system.identity_hash':'invented'},{'cxl.profile.decoder_granule_bytes':3},{'cases.0.phase':2}):
            with self.assertRaises((ValueError,TypeError)):
                load_config(TierStudy,ROOT/'config/experiments/system_tiering.json',overrides=overrides)


if __name__=='__main__':
    unittest.main()
