"""Independent AI numerics, exact node demand and declared policy/sensitivity evidence."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json, parse_json
from contracts.workload.linear import LinearSpec
from contracts.workload.training import TrainingSpec
from contracts.workload.attention import AttentionSpec
from evaluation.experiments.runner.system_ai import AiTask, AiCase, AiStudy, run_study, summarize_records, read_study, write_study


ROOT=Path(__file__).resolve().parents[2]  # Default bounded synthetic tasks and fixed node budget.


# Numeric correctness and necessary hardware service are separate evidence, checked independently on replay.
class SystemAiTests(unittest.TestCase):
    # Run the complete three-task policy/sensitivity matrix plus all capacity failures once.
    @classmethod
    def setUpClass(cls):
        cls.study=load_config(AiStudy,ROOT/'config/experiments/system_ai.json')
        cls.records=run_study(cls.study,source_revision='ai-test')
        cls.rows={r['case']:r for r in summarize_records(cls.records)}

    # Every numerical result passes its independent reference; three oversized policies fail capacity under the same budget.
    def test_roster_and_numerical_validation(self):
        self.assertEqual((len(self.rows),sum(r['status']=='succeeded' for r in self.rows.values())),(18,15))
        self.assertTrue(all(r['expectation_met'] for r in self.rows.values()))
        for row in self.rows.values():
            if row['result'] is not None:
                self.assertTrue(all(v['passed'] for v in row['result']['task']['validation'].values()))
        training=self.rows['training_direct']['result']['task']
        self.assertTrue({'loss','prediction','dx','dw0','dw1','updated_w0','updated_w1'}<=set(training['validation']))

    # 4x8 and 8x4 float64 operands occupy 512 B; direct copies once, staging twice, and already-resident input needs no preparation.
    def test_linear_hand_demand(self):
        direct=self.rows['linear_direct']['result']; staged=self.rows['linear_staged']['result']; resident=self.rows['linear_resident']['result']
        self.assertEqual((direct['task']['input_bytes'],direct['task']['backing_peak_bytes'],direct['task']['macs']),(512,640,128))
        self.assertEqual((resident['copied_bytes'],direct['copied_bytes'],staged['copied_bytes']),(0,512,1024))
        self.assertAlmostEqual(direct['known_service_lower_bound_s'],512e-9)
        self.assertAlmostEqual(staged['known_service_lower_bound_s'],1024e-9)
        self.assertAlmostEqual(resident['known_service_lower_bound_s'],128e-9)

    # Keeping 288 B packed training inputs requires separate 1096 B of all intermediate/update tensors; dead input slots are unavailable.
    def test_training_workspace_is_conservative(self):
        result=self.rows['training_resident']['result']
        task=result['task']
        self.assertEqual((task['input_bytes'],task['compiler_backing_peak_bytes'],task['backing_peak_bytes']),(288,680,1384))
        sizes={o['object_id']:o['size_bytes'] for o in result['placement']['objects']}
        self.assertEqual(sizes['task.workspace'],1096)
        self.assertGreater(task['backing_peak_bytes'],task['compiler_backing_peak_bytes'])

    # Tail shapes, INT8/INT64 results, one/deeper-layer training and causal batched GQA must preserve actual packed byte demand.
    def test_replaceable_tasks_and_datatypes(self):
        tasks=(AiTask(task_id='int8_tail',seed=11,linear=LinearSpec(m=3,n=5,k=2,dtype='int8')),
               AiTask(task_id='float_tail',seed=12,linear=LinearSpec(m=1,n=3,k=5,dtype='float64')),
               AiTask(task_id='one_layer',seed=13,training=TrainingSpec(batch_size=1,widths=(3,2))),
               AiTask(task_id='three_layers',seed=14,training=TrainingSpec(batch_size=3,widths=(2,3,2,1),hidden_activation='identity')),
               AiTask(task_id='causal_gqa',seed=15,attention=AttentionSpec(batch_size=2,query_heads=4,kv_heads=2,
                       query_length=1,kv_length=3,key_dim=2,value_dim=3,scale=0.5,causal=True,query_start=2)),
               AiTask(task_id='unequal_heads',seed=16,attention=AttentionSpec(batch_size=1,query_heads=3,kv_heads=1,
                       query_length=2,kv_length=2,key_dim=3,value_dim=1,scale=0.5)))
        sizes={'int8_tail':16,'float_tail':160,'one_layer':88,'three_layers':184,'causal_gqa':608,'unequal_heads':208}
        cases=tuple(AiCase(name=t.task_id+'_'+policy,task_id=t.task_id,strategy=policy)
                    for t in tasks for policy in ('resident','direct','staged'))
        study=replace(self.study,tasks=tasks,cases=cases)
        records=run_study(study,source_revision='replaceable-ai-test')
        rows=summarize_records(records)
        self.assertEqual(len(rows),18)
        for row in rows:
            with self.subTest(case=row['case']):
                self.assertEqual(row['status'],'succeeded',row['diagnostic'])
                result=row['result']; size=sizes[row['task_id']]
                self.assertEqual(result['task']['input_bytes'],size)
                self.assertEqual(result['copied_bytes'],size*{'resident':0,'direct':1,'staged':2}[row['strategy']])
                self.assertTrue(all(v['passed'] for v in result['task']['validation'].values()))
        with TemporaryDirectory() as root:
            destination=Path(root)/'varied'; write_study(records,destination)
            self.assertEqual(rows,summarize_records(read_study(destination)))

    # Each task's policies preserve actual inputs/state, numeric outputs and unchanged hardware; intervention cases are explicitly different.
    def test_fair_comparison_and_content_link(self):
        for task in ('linear','training','attention'):
            rows=[self.rows[task+'_'+policy]['result'] for policy in ('resident','direct','staged')]
            self.assertEqual(len({r['task']['input_identity'] for r in rows}),1)
            self.assertEqual(len({r['hardware_identity'] for r in rows}),1)
            self.assertTrue(all(r['task']['actual']==rows[0]['task']['actual'] for r in rows))
            for result in rows:
                obj=next(o for o in result['placement']['objects'] if o['object_id']=='task.inputs')
                self.assertEqual((obj['size_bytes'],obj['source_ref']),(result['task']['input_bytes'],result['task']['input_identity']))

    # Halving the shared root ceiling doubles its necessary time; startup inflation moves small-copy service toward DMA control.
    def test_sensitivity_and_bottleneck(self):
        for task in ('linear','training','attention'):
            base=self.rows[task+'_direct']['result']; half=self.rows[task+'_half_bandwidth']['result']; high=self.rows[task+'_high_startup']['result']
            self.assertAlmostEqual(half['transfer_lower_bound_s'],2*base['transfer_lower_bound_s'])
            self.assertGreater(high['transfer_lower_bound_s'],base['transfer_lower_bound_s'])
            self.assertIn('root_bus',half['bottleneck_resource_ids'])
            self.assertIn('gpu0.dma',high['bottleneck_resource_ids'])
            self.assertNotEqual(base['hardware_identity'],half['hardware_identity'])

    # Saved numerics are checked by independent references; no mapped interpreter or new DMA route search is invoked.
    def test_roundtrip_without_execution(self):
        with TemporaryDirectory() as root:
            destination=Path(root)/'study'
            write_study(self.records,destination)
            with patch('evaluation.experiments.runner.system_ai._evaluate',side_effect=AssertionError('producer')), \
                 patch('evaluation.experiments.runner.system_ai.execute_plan',side_effect=AssertionError('linear execute')), \
                 patch('evaluation.experiments.runner.system_ai.execute_training',side_effect=AssertionError('training execute')), \
                 patch('evaluation.experiments.runner.system_ai.execute_attention_plan',side_effect=AssertionError('attention execute')), \
                 patch('systemmodel.io.dma.analysis.find_path',side_effect=AssertionError('search')):
                self.assertEqual(summarize_records(self.records),summarize_records(read_study(destination)))
            with self.assertRaises(FileExistsError): write_study(self.records,destination)

    # Rehashed outputs cannot falsify the numerics, memory/demand binding, physical route, count or bottleneck explanation.
    def test_observation_tampering(self):
        position=next(i for i,r in enumerate(self.records) if r.spec.experiment_id=='linear_staged')
        first=self.records[position]
        changes=((('task','actual',0),999),(('task','input_bytes'),1),(('task','input_identity'),'wrong'),
                 (('copied_bytes',),512),(('known_service_lower_bound_s',),0),
                 (('placement','objects',0,'size_bytes'),1),(('transfer','legs',0,'path','link_ids'),[]),
                 (('bottleneck_resource_ids',),[]),(('unknown_costs',),[]))
        for path,value in changes:
            payload=parse_json(first.output_json); target=payload
            for key in path[:-1]: target=target[key]
            target[path[-1]]=value
            records=list(self.records); records[position]=replace(first,output_json=canonical_json(payload))
            with self.subTest(path=path),self.assertRaises(ValueError): summarize_records(tuple(records))

    # Input/source/roster changes and relabeling unknown energy invalidate an otherwise rehashed comparison.
    def test_identity_and_unknown_cost_guards(self):
        first=self.records[0]
        for records in (self.records[:-1],(*self.records,first),
                        (replace(first,inputs_json='{}'),*self.records[1:]),
                        (replace(first,spec=replace(first.spec,source_revision='changed')),*self.records[1:]),
                        (replace(first,metrics=tuple(replace(m,value=0,unknown_reason=None) if m.name=='target_energy' else m for m in first.metrics)),*self.records[1:])):
            with self.assertRaises(ValueError): summarize_records(records)

    # All failed tasks remain in the comparison; producer success is never used as a surrogate for numeric validation.
    def test_failure_retention(self):
        with patch('evaluation.experiments.runner.system_ai._evaluate',side_effect=ValueError('injected')):
            rows=summarize_records(run_study(self.study))
        self.assertEqual(sum(not r['expectation_met'] for r in rows),15)
        self.assertTrue(all(r['status']=='failed' and r['diagnostic'] for r in rows))


if __name__=='__main__':
    unittest.main()
