"""Logical KV state ownership, head-major append and prefill/decode equivalence."""

from dataclasses import replace
import unittest

from contracts.workload.attention import AttentionSpec, KvCacheSpec, KvCacheState
from workloads.graphs.kv_cache import append_kv, attention_from_cache
from workloads.kernels.attention import generate_attention
from workloads.reference.attention import reference_attention


# Extract contiguous token ranges independently within every batch/head group for equivalence fixtures.
def tokens(values, groups, length, dim, start, end):
    return tuple(values[(group * length + i) * dim + j]
                 for group in range(groups) for i in range(start, end) for j in range(dim))


# No physical page allocation or hardware timing is implied by these state tests.
class KvCacheTests(unittest.TestCase):
    # Four B/head groups must each append their token; concatenating entire old/new arrays would be wrong.
    def test_grouped_append_and_capacity(self):
        p = KvCacheSpec(batch_size=2, kv_heads=2, key_dim=2, value_dim=1, max_tokens=3)
        empty = KvCacheState(spec=p)
        first = append_kv(empty, tokens=1, k=tuple(map(float, range(8))), v=(1.0, 2.0, 3.0, 4.0), expected_identity=empty.identity_hash)
        second = append_kv(first, tokens=1, k=tuple(map(float, range(8, 16))), v=(5.0, 6.0, 7.0, 8.0), expected_identity=first.identity_hash)
        self.assertEqual(second.k, (0., 1., 8., 9., 2., 3., 10., 11., 4., 5., 12., 13., 6., 7., 14., 15.))
        self.assertEqual(second.v, (1., 5., 2., 6., 3., 7., 4., 8.))
        self.assertEqual((empty.tokens, first.tokens, second.tokens, second.version), (0, 1, 2, 2))
        self.assertEqual((p.capacity_bytes, second.resident_bytes), (288, 192))
        self.assertEqual(first.v, (1., 2., 3., 4.))

    # Full causal prefill equals both token-wise decode and chunked append, across batches and shared heads.
    def test_prefill_equals_chunked_decode(self):
        p = AttentionSpec(batch_size=2, query_heads=4, kv_heads=2, query_length=5,
                          kv_length=5, key_dim=2, value_dim=3, scale=0.5, causal=True)
        data = generate_attention(p, 19)
        whole = reference_attention(p, data).output
        for chunks in ((1, 1, 1, 1, 1), (1, 2, 2), (5,)):
            state = KvCacheState(spec=KvCacheSpec(batch_size=2, kv_heads=2, key_dim=2, value_dim=3, max_tokens=5))
            start, pieces = 0, [[] for _ in range(8)]
            for size in chunks:
                end = start + size
                state = append_kv(state, tokens=size, k=tokens(data.k, 4, 5, 2, start, end),
                                  v=tokens(data.v, 4, 5, 3, start, end), expected_identity=state.identity_hash)
                part = replace(p, query_length=size, kv_length=end, query_start=start)
                inputs = attention_from_cache(part, state, tokens(data.q, 8, 5, 2, start, end))
                out = reference_attention(part, inputs).output
                for group in range(8):
                    pieces[group].extend(out[group * size * 3:(group + 1) * size * 3])
                start = end
            self.assertEqual(tuple(x for group in pieces for x in group), whole)
            self.assertEqual((state.k, state.v, state.tokens, state.version), (data.k, data.v, 5, len(chunks)))

    # Expected source identity rejects stale/foreign states; all snapshots remain unchanged after rejected writes.
    def test_identity_and_append_rejections(self):
        state = KvCacheState(spec=KvCacheSpec(batch_size=1, kv_heads=1, key_dim=1, value_dim=1, max_tokens=2))
        new = append_kv(state, tokens=1, k=[1.0], v=[2.0], expected_identity=state.identity_hash)
        for kwargs in ({'expected_identity': state.identity_hash}, {'tokens': 2}, {'tokens': 0},
                       {'k': (1.0, 2.0)}, {'max_elements': 3}):
            params = dict(tokens=1, k=(3.0,), v=(4.0,), expected_identity=new.identity_hash)
            params.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                append_kv(new, **params)
        self.assertNotEqual(new.identity_hash, replace(new, k=(5.0,)).identity_hash)
        self.assertEqual((state.tokens, new.k), (0, (1.0,)))

    # Cache-binding enforces logical axis dimensions and resident length, not just a matching element count.
    def test_snapshot_and_binding_guards(self):
        p = KvCacheSpec(batch_size=1, kv_heads=1, key_dim=2, value_dim=1, max_tokens=4)
        for kwargs in ({'version': True}, {'tokens': 5}, {'tokens': 1}, {'k': {1.0: 'value'}}):
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, TypeError)):
                KvCacheState(spec=p, **kwargs)
        state = KvCacheState(spec=p, tokens=1, k=(1.0, 2.0), v=(3.0,))
        task = AttentionSpec(batch_size=1, query_heads=2, kv_heads=1, query_length=1, kv_length=1,
                             key_dim=2, value_dim=1, scale=1, causal=True)
        bound = attention_from_cache(task, state, (1.0, 1.0, 2.0, 2.0))
        self.assertEqual(reference_attention(task, bound).output, (3.0, 3.0))
        with self.assertRaises(ValueError):
            attention_from_cache(replace(task, kv_length=2), state, bound.q)


if __name__ == '__main__':
    unittest.main()
