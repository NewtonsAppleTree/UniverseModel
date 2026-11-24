"""Complete S2 study records, immutable bundle boundaries and adversarial observation replay."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json, parse_json
from evaluation.experiments.runner.system_memory import MemoryStudy, read_study, run_study, summarize_records, write_study


ROOT = Path(__file__).resolve().parents[2]  # Local synthetic fixture; no equipment, external dependency or task dataset.


# Static correctness/reproducibility evidence is distinct from target execution and model/task-quality validation.
class MemoryStudyTests(unittest.TestCase):
    # Immutable 15-case declarations are executed once; all negative controls remain in the roster.
    @classmethod
    def setUpClass(cls):
        cls.study = load_config(MemoryStudy,ROOT/'config/experiments/system_memory.json')
        cls.records = run_study(cls.study,source_revision='memory-test')

    # Six successful controls and nine failures remain visible; costs stay unknown even for local accesses.
    def test_complete_roster_and_unknown_costs(self):
        rows = summarize_records(self.records)
        self.assertEqual(len(rows),15)
        self.assertEqual(sum(r['status']=='succeeded' for r in rows),6)
        self.assertTrue(all(r['expectation_met'] for r in rows))
        by_name = {r['case']:r for r in rows}
        self.assertEqual(by_name['alias']['result']['placement']['backings'][0]['peak_reserved_bytes'],320)
        self.assertEqual(by_name['replicated_copy']['result']['placement']['backings'][0]['peak_reserved_bytes'],512)
        self.assertEqual(by_name['remote']['result']['access']['locality'],'remote')
        self.assertIsNone(by_name['placement_only']['result']['access'])
        for record in self.records:
            if record.status=='succeeded':
                self.assertTrue(all(m.value is None and m.unknown_reason for m in record.metrics if m.name.startswith('target_')))
                self.assertEqual('path_hops' in {m.name for m in record.metrics},record.spec.experiment_id!='placement_only')
            else:
                self.assertIsNone(record.output_json)
                self.assertTrue(record.diagnostic)

    # Readback reanalyzes declarations but cannot execute the producer or search for a replacement route.
    def test_roundtrip_without_producer_or_search(self):
        with TemporaryDirectory() as root:
            destination = Path(root)/'memory'
            write_study(self.records,destination)
            with patch('evaluation.experiments.runner.system_memory._evaluate',side_effect=AssertionError('executed')), \
                 patch('evaluation.experiments.runner.system_memory.analyze_access',side_effect=AssertionError('producer')), \
                 patch('systemmodel.memory.access.find_path',side_effect=AssertionError('searched')):
                self.assertEqual(summarize_records(read_study(destination)),summarize_records(self.records))
            with self.assertRaises(FileExistsError):
                write_study(self.records,destination)
            index = parse_json((destination/'index.json').read_text(encoding='utf-8'))
            index['runs'][0]['directory']='../outside'
            (destination/'index.json').write_text(canonical_json(index),encoding='utf-8')
            with self.assertRaises(ValueError):
                read_study(destination)

    # Omitting a candidate or mixing demand/source/assumptions cannot preserve a complete study identity.
    def test_roster_and_input_integrity(self):
        first = self.records[0]
        inputs = parse_json(first.inputs_json)
        inputs['plan']['allocations'][0]['offset_bytes']+=64
        cases = (self.records[:-1],(*self.records,first),
                 (replace(first,spec=replace(first.spec,source_revision='changed')),*self.records[1:]),
                 (replace(first,spec=replace(first.spec,assumptions=('changed',))),*self.records[1:]),
                 (replace(first,inputs_json=canonical_json(inputs)),*self.records[1:]))
        for records in cases:
            with self.assertRaises(ValueError):
                summarize_records(records)

    # Rehashed observations still must match declared occupancy, live copies, resolved offset, locality and route.
    def test_observation_tampering(self):
        position = next(i for i,r in enumerate(self.records) if r.spec.experiment_id=='alias')
        first = self.records[position]
        paths = ((('placement','memory_identity'),'0'*64),(('placement','plan_identity'),'0'*64),
                 (('placement','backings',0,'peak_reserved_bytes'),512),(('placement','backings',0,'peak_phase'),2),
                 (('placement','backings',0,'allocation_ids_at_peak'),[]),
                 (('access','span','physical_offset_bytes'),64),(('access','locality'),'remote'),
                 (('access','initiator_numa_id'),'numa1'),(('access','path','constraint_visits'),['invented']),
                 (('access','path','link_ids'),['cpu0_fabric','fabric_mc1']),(('access','path','target_domain_id'),'mc1.address'))
        for path,value in paths:
            payload = parse_json(first.output_json)
            target = payload
            for key in path[:-1]:
                target = target[key]
            target[path[-1]]=value
            changed = list(self.records)
            changed[position]=replace(first,output_json=canonical_json(payload))
            with self.subTest(path=path),self.assertRaises(ValueError):
                summarize_records(tuple(changed))
        for payload in (None,{'placement':None,'access':None}):
            changed = list(self.records)
            changed[position]=replace(first,output_json=canonical_json(payload))
            with self.assertRaises(ValueError):
                summarize_records(tuple(changed))

    # Counters, units and unknown-cost reasons cannot be altered independently of the recorded static evidence.
    def test_metric_tampering(self):
        position = next(i for i,r in enumerate(self.records) if r.spec.experiment_id=='local')
        first = self.records[position]
        for name,change in (('allocation_count',{'value':3}),('target_execution_time',{'value':0,'unknown_reason':None}),
                            ('path_hops',{'unit':'byte'}),('target_energy',{'unknown_reason':'invented evidence'})):
            changed = list(self.records)
            changed[position]=replace(first,metrics=tuple(replace(m,**change) if m.name==name else m for m in first.metrics))
            with self.subTest(metric=name),self.assertRaises(ValueError):
                summarize_records(tuple(changed))

    # Unexpected runtime failures remain failed attempts with expectation_met=False; readback does not rerun them.
    def test_unexpected_failure_retention(self):
        with patch('evaluation.experiments.runner.system_memory._evaluate',side_effect=ValueError('injected failure')):
            records = run_study(self.study,source_revision='injected')
        rows = summarize_records(records)
        self.assertTrue(all(r.status=='failed' for r in records))
        self.assertEqual(sum(not r['expectation_met'] for r in rows),6)

    # Configuration cannot invent derived fields or silently rebind plans when physical parameters change.
    def test_strict_configuration_and_stale_binding(self):
        path = ROOT/'config/experiments/system_memory.json'
        for override in ({'memory.identity_hash':'invented'},{'cases.0.plan.source_ref':'override'},{'memory.backings':[]}):
            with self.assertRaises((ValueError,TypeError)):
                load_config(MemoryStudy,path,overrides=override)
        changed = replace(self.study,memory=replace(self.study.memory,source_ref='changed-hardware-source'))
        records = run_study(changed,source_revision='stale-test')
        self.assertTrue(all(r.status=='failed' and 'stale' in r.diagnostic for r in records))


if __name__=='__main__':
    unittest.main()
