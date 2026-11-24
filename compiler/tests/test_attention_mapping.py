"""Independent Attention mapping checks: row ownership, physical payloads, numerical reference and failures."""

from dataclasses import replace
import unittest

from compiler.src.interpret.attention import execute_attention_plan
from compiler.src.memplan.attention import count_attention_traffic, plan_attention_memory
from compiler.src.tiling.attention import build_attention_plan, validate_attention_plan
from contracts.workload.attention import AttentionInputs, AttentionSpec


# Coverage and data movement are checked independently of the builder's own validation.
class AttentionMappingTests(unittest.TestCase):
    # Small causal GQA task gives hand-countable full-key loads and real query tails.
    def setUp(self):
        self.spec = AttentionSpec(batch_size=1,query_heads=4,kv_heads=2,query_length=3,kv_length=4,key_dim=2,value_dim=3,scale=.5,causal=True,query_start=1)
        self.capacity = {'scratch_capacity_bytes': 100000, 'backing_capacity_bytes': 100000}

    # Fusion removes four intermediate payload transfers; larger query blocks reduce repeated KV loads.
    def test_hand_counts_and_capacity(self):
        expected = {('fused',1,'shared'): (2400,248,800), ('spill',1,'shared'): (3936,248,1184),
                    ('fused',2,'shared'): (1760,336,800), ('fused',1,'expanded'): (3680,248,1440)}
        for (policy,tile,layout),(traffic_bytes,scratch,backing) in expected.items():
            plan = build_attention_plan(self.spec, query_tile=tile, score_policy=policy, kv_layout=layout)
            traffic = count_attention_traffic(self.spec, plan)
            memory = plan_attention_memory(self.spec, plan, **self.capacity)
            self.assertEqual((traffic.external_bytes,memory.scratch_bytes,memory.backing_bytes),(traffic_bytes,scratch,backing))
            self.assertEqual((traffic.qk_macs,traffic.av_macs,traffic.exp_evaluations,traffic.max_comparisons),(72,108,36,24))
            self.assertEqual(traffic.layout_copy_elements,80 if layout=='expanded' else 0)
            sizes = dict(memory.backing_tensors)
            for t in traffic.transfers:
                self.assertGreater(t.payload_bytes,0)
                self.assertLessEqual(t.offset_bytes+t.payload_bytes,sizes[t.tensor])
            for name in ('scratch_capacity_bytes','backing_capacity_bytes'):
                limits = dict(self.capacity)
                limits[name] = (scratch if name.startswith('scratch') else backing)-1
                with self.assertRaisesRegex(ValueError,'capacity'):
                    plan_attention_memory(self.spec,plan,**limits)

    # Explicitly enumerate output elements; every row/head is written exactly once, including non-divisible tails.
    def test_output_regions_and_layout(self):
        p = replace(self.spec,batch_size=2)
        for layout in ('shared','expanded'):
            plan = build_attention_plan(p,query_tile=2,kv_layout=layout)
            writes = [t for t in count_attention_traffic(p,plan).transfers if t.tensor=='O']
            elements = [j for t in writes for j in range(t.offset_bytes//8,(t.offset_bytes+t.payload_bytes)//8)]
            self.assertEqual(elements,list(range(2*4*3*3)))
            self.assertEqual([b.rows for b in plan.blocks[:2]],[2,1])



    # Reject forged ownership, omitted/repeated rows, stale task hashes and host allocation/work limits.
    def test_plan_and_budget_guards(self):
        p = self.spec
        plan = build_attention_plan(p,query_tile=2)
        for bad in (replace(plan,blocks=plan.blocks[:-1]),replace(plan,blocks=(plan.blocks[0],*plan.blocks)),
                    replace(plan,blocks=(replace(plan.blocks[0],head=1),*plan.blocks[1:])),replace(plan,workload_hash='0'*64)):
            with self.assertRaises(ValueError):
                validate_attention_plan(p,bad)
        with self.assertRaisesRegex(ValueError,'max_blocks'):
            build_attention_plan(p,query_tile=1,max_blocks=1)
        with self.assertRaisesRegex(ValueError,'max_transfers'):
            count_attention_traffic(p,plan,max_transfers=1)
        data = AttentionInputs(q=(0.0,)*(p.batch_size*p.query_heads*p.query_length*p.key_dim),
                               k=(0.0,)*(p.batch_size*p.kv_heads*p.kv_length*p.key_dim),
                               v=(0.0,)*(p.batch_size*p.kv_heads*p.kv_length*p.value_dim))
        for options in ({'max_macs':1},{'max_elements':1}):
            with self.assertRaisesRegex(ValueError,'max_macs/max_elements'):
                execute_attention_plan(p,data,plan,**self.capacity,**options)



if __name__ == '__main__':
    unittest.main()
