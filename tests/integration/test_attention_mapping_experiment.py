"""Same-task resource comparisons, expected failures and immutable Attention mapping replay."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import random
from unittest.mock import patch

from compiler.src.interpret.attention import execute_attention_plan
from compiler.src.tiling.attention import build_attention_plan
from contracts.workload.attention import AttentionInputs, AttentionSpec
from workloads.kernels.attention import generate_attention
from workloads.reference.attention import compare_attention, reference_attention
from workloads.reference.classification import classification_metrics
from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json,parse_json
from evaluation.experiments.runner.attention import AttentionMappingStudy,read_study,run_study,summarize_records,write_study


ROOT = Path(__file__).resolve().parents[2]  # Local configs; no target device dependencies.


# All candidate work uses one input/budget, with unknown scalar and physical costs retained.
class AttentionStudyTests(unittest.TestCase):
    # Share immutable records from the reviewed five-candidate fixture.
    @classmethod
    def setUpClass(cls):
        cls.study = load_config(AttentionMappingStudy,ROOT/'config/experiments/attention_mapping.json')
        cls.records = run_study(cls.study,source_revision='mapping-test')

    # Expected capacity failure and numerical success are both necessary to accept the default comparison.
    def test_results_and_partial_hardware_coverage(self):
        rows = {r['case']:r for r in summarize_records(self.records)}
        self.assertEqual((len(rows),sum(r.status=='succeeded' for r in self.records)),(5,4))
        self.assertTrue(all(r['expectation_met'] for r in rows.values()))
        for record in self.records:
            if record.status=='succeeded':
                result = parse_json(record.output_json)
                self.assertEqual(result['mac']['executed_macs'],180)
                self.assertEqual(result['mac']['arithmetic']['operation'],'float_mul_add')
                self.assertIsNone(next(m for m in record.metrics if m.name=='target_execution_time').value)
        self.assertLess(rows['fused_q2']['result']['serial_dma_s'],rows['fused_q1']['result']['serial_dma_s'])
        self.assertEqual(rows['spill_q1']['result']['output'],rows['expanded_q1']['result']['output'])

    # A mismatched hardware format cannot service this binary64 interpreter or be reinterpreted as a faster MAC.
    def test_format_and_input_failure_records(self):
        changed = replace(self.study.hardware.mac,arithmetic=replace(self.study.hardware.mac.arithmetic,operation='float_fma'))
        records = run_study(replace(self.study,hardware=replace(self.study.hardware,mac=changed)))
        self.assertTrue(all(r.status=='failed' for r in records))
        self.assertTrue(any('unsupported' in r.diagnostic for r in records))
        records = run_study(replace(self.study,max_elements=1))
        self.assertTrue(all(parse_json(r.inputs_json)['data'] is None for r in records))
        self.assertTrue(all(not r['expectation_met'] for r in summarize_records(records) if r['case']!='capacity_failed'))

    # Source/input/budget mixing, duplicate cases and missing roster entries are rejected on replay.
    def test_roster_guards(self):
        first = self.records[0]
        config = parse_json(first.configuration_json)
        config['study']['hardware']['scratch_capacity_bytes'] += 1
        variants = (self.records[:-1],(*self.records,first),
                    (replace(first,spec=replace(first.spec,source_revision='other')),*self.records[1:]),
                    (replace(first,configuration_json=canonical_json(config)),*self.records[1:]))
        for records in variants:
            with self.assertRaises(ValueError):
                summarize_records(records)

    # A valid input hash cannot hide altered output, numerical verdict, candidate plan or required reference evidence.
    def test_saved_observation_guards(self):
        first = self.records[0]
        for field in ('output','reference_output','validation','plan','missing_reference','memory','traffic','transfer'):
            payload = parse_json(first.output_json)
            if field in ('output','reference_output'):
                payload[field][0] += 1.
            elif field=='validation':
                payload['validation']['mismatched_indices'] = [0]
            elif field=='plan':
                payload['plan']['query_tile'] += 1
            elif field=='memory':
                payload['memory']['scratch_bytes'] += 8
            elif field=='traffic':
                payload['traffic']['qk_macs'] += 1
            elif field=='transfer':
                payload['traffic']['transfers'][0]['offset_bytes'] = 1000000
            else:
                del payload['reference_output']
            with self.subTest(field=field),self.assertRaises(ValueError):
                summarize_records((replace(first,output_json=canonical_json(payload)),*self.records[1:]))
        metrics = tuple(replace(m,value=m.value+1) if m.name=='external_payload' else m for m in first.metrics)
        with self.assertRaisesRegex(ValueError,'metrics'):
            summarize_records((replace(first,metrics=metrics),*self.records[1:]))

    # Legacy records lack oracle observations and receive structural validation; generations cannot be mixed.
    def test_legacy_mapping_records(self):
        legacy = []
        for record in self.records:
            payload = parse_json(record.output_json) if record.status=='succeeded' else None
            if payload is not None:
                del payload['reference_output']
            legacy.append(replace(record,spec=replace(record.spec,implementation_id='attention-mapping/v1'),
                                  output_json=canonical_json(payload) if payload is not None else None))
        self.assertTrue(all(row['expectation_met'] for row in summarize_records(tuple(legacy))))
        with self.assertRaises(ValueError):
            summarize_records((legacy[0],*self.records[1:]))

    # No compiler, generator, hardware query or numerical reference executes while rebuilding a saved table.
    def test_roundtrip_and_integrity(self):
        with TemporaryDirectory() as root:
            path = Path(root)/'mapping'
            write_study(self.records,path)
            with patch('evaluation.experiments.runner.attention.evaluate_attention',side_effect=AssertionError('executed')), \
                 patch('evaluation.experiments.runner.attention.generate_attention',side_effect=AssertionError('generated')), \
                 patch('evaluation.experiments.runner.attention.reference_attention',side_effect=AssertionError('reference')), \
                 patch('evaluation.experiments.runner.attention.build_attention_plan',side_effect=AssertionError('mapping')):
                self.assertEqual(summarize_records(read_study(path)),summarize_records(self.records))
            index = parse_json((path/'index.json').read_text(encoding='utf-8'))
            index['runs'][0]['directory'] = '../outside'
            (path/'index.json').write_text(canonical_json(index),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'path'):
                read_study(path)


# Cross-module numerical validation compares the compiler against the independent workloads oracle.
class AttentionNumericalTests(unittest.TestCase):
    # Common shape and generous host fixture capacities isolate arithmetic and layout behavior.
    def setUp(self):
        self.spec = AttentionSpec(batch_size=1,query_heads=4,kv_heads=2,query_length=3,kv_length=4,key_dim=2,value_dim=3,scale=.5,causal=True,query_start=1)
        self.capacity = {'scratch_capacity_bytes': 100000, 'backing_capacity_bytes': 100000}

    # Every policy uses the same mathematical task; random shapes compare with an independent high precision oracle.
    def test_randomized_functional_equivalence(self):
        rng = random.Random(492)
        for i in range(18):
            sk = rng.randrange(1,6)
            sq = rng.randrange(1,sk+1)
            p = replace(self.spec,batch_size=rng.randrange(1,3),query_length=sq,kv_length=sk,
                        query_start=sk-sq if i%2 else 0,key_dim=rng.randrange(1,4),value_dim=rng.randrange(1,4),causal=bool(i%2))
            data = generate_attention(p,i)
            ref = reference_attention(p,data)
            outputs = []
            for policy,layout in (('fused','shared'),('spill','shared'),('fused','expanded'),('spill','expanded')):
                plan = build_attention_plan(p,query_tile=2,score_policy=policy,kv_layout=layout)
                actual = execute_attention_plan(p,data,plan,**self.capacity)
                self.assertTrue(compare_attention(p,data,actual,ref).passed)
                outputs.append(actual)
            self.assertTrue(all(x==outputs[0] for x in outputs))

    # The hand causal means expose wrong grouping and future-key leakage directly.
    def test_causal_uniform_means(self):
        p = replace(self.spec,query_length=2,kv_length=3,query_start=1,key_dim=1,value_dim=1)
        data = AttentionInputs(q=(0.,)*8,k=(0.,)*6,v=(2.,4.,102.,10.,20.,60.))
        for layout in ('shared','expanded'):
            plan = build_attention_plan(p,query_tile=2,score_policy='spill',kv_layout=layout)
            self.assertEqual(execute_attention_plan(p,data,plan,**self.capacity),(3.,36.,3.,36.,15.,30.,15.,30.))

    # Functional overflow remains a failed candidate; it cannot be disguised by a successful exact reference.
    def test_numerical_failure_and_comparison(self):
        p = replace(self.spec,query_heads=1,kv_heads=1,query_length=1,kv_length=1,key_dim=1,value_dim=1,query_start=0)
        data = AttentionInputs(q=(1e308,),k=(2.,),v=(1.,))
        with self.assertRaisesRegex(ValueError,'nonfinite'):
            execute_attention_plan(p,data,build_attention_plan(p,query_tile=1),**self.capacity)
        ref = reference_attention(p,data)
        self.assertFalse(compare_attention(p,data,(2.,),ref).passed)
        with self.assertRaisesRegex(ValueError,'identity'):
            compare_attention(p,replace(data,v=(2.,)),(1.,),ref)

    # Nine uniform one-class weights accumulate one ulp above one; a valid mapped output still supports classification.
    def test_uniform_classification_roundoff(self):
        spec = AttentionSpec(batch_size=1,query_heads=1,kv_heads=1,query_length=1,kv_length=9,key_dim=1,value_dim=2,scale=1.)
        data = AttentionInputs(q=(0.,),k=(0.,)*9,v=(1.,0.)*9)
        output = execute_attention_plan(spec,data,build_attention_plan(spec,query_tile=1),**self.capacity)
        self.assertGreater(output[0],1.)
        self.assertTrue(compare_attention(spec,data,output,reference_attention(spec,data)).passed)
        metrics = classification_metrics(output,(0,),2)
        self.assertEqual((metrics.correct,metrics.mean_log_loss),(1,0.))


if __name__=='__main__':
    unittest.main()
