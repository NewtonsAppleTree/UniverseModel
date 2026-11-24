"""Attention semantics against hand examples, independent float arithmetic and explicit KV expansion."""

from dataclasses import replace
from decimal import Decimal, Inexact, ROUND_DOWN, localcontext
from math import exp, fsum, isclose
import random
import unittest

from contracts.workload.attention import AttentionInputs, AttentionSpec, attention_identity, validate_attention
from workloads.kernels.attention import describe_attention, generate_attention
from workloads.reference.attention import reference_attention, reference_softmax


# Small GQA fixture distinguishes query/key/value dimensions and causal offsets.
def spec(**changes):
    return replace(AttentionSpec(batch_size=1, query_heads=2, kv_heads=1, query_length=2,
                                 kv_length=3, key_dim=2, value_dim=3, scale=0.5, causal=True, query_start=1), **changes)


# Independent direct float64 implementation with an explicit full-row mask; it does not call production helpers.
def float_reference(p, inputs):
    outputs, probabilities = [], []
    for b in range(p.batch_size):
        for h in range(p.query_heads):
            group = h // (p.query_heads // p.kv_heads)
            for i in range(p.query_length):
                scores = []
                for j in range(p.kv_length):
                    if p.causal and j > p.query_start + i:
                        scores.append(float('-inf'))
                    else:
                        q = inputs.q[((b * p.query_heads + h) * p.query_length + i) * p.key_dim:][:p.key_dim]
                        k = inputs.k[((b * p.kv_heads + group) * p.kv_length + j) * p.key_dim:][:p.key_dim]
                        scores.append(fsum(a * c for a, c in zip(q, k)) * p.scale)
                e = [exp(s - max(scores)) for s in scores]
                weights = [v / fsum(e) for v in e]
                probabilities.extend(weights)
                for d in range(p.value_dim):
                    outputs.append(fsum(weights[j] * inputs.v[((b * p.kv_heads + group) * p.kv_length + j) * p.value_dim + d]
                                        for j in range(p.kv_length)))
    return tuple(outputs), tuple(probabilities)


# Verify inputs, grouping, masks, accounting and independent numerical behavior without target hardware.
class AttentionTests(unittest.TestCase):
    # Sq=2, Skv=3 with query_start=1 has 2+3 keys per head; unique KV bytes use Hkv=1.
    def test_hand_counts(self):
        w = describe_attention(spec())
        self.assertEqual((w.dense_qk_macs, w.dense_av_macs, w.visible_pairs, w.visible_pair_macs), (24, 36, 10, 50))
        self.assertEqual((w.softmax_rows, w.reference_exp_evaluations, w.reference_sum_additions), (4, 10, 6))
        self.assertEqual((w.reference_scale_multiplications, w.reference_max_comparisons,
                          w.reference_subtractions, w.reference_divisions), (10, 6, 10, 10))
        self.assertEqual((w.q_bytes, w.kv_bytes, w.output_bytes, w.materialized_score_bytes), (64, 120, 96, 96))
        full = describe_attention(spec(causal=False, query_start=0))
        self.assertEqual((full.visible_pairs, full.visible_pair_macs), (12, 60))

    # Uniform logits expose the grouping and causal alignment directly through distinct value means.
    def test_uniform_grouping_and_causal_offset(self):
        p = spec(query_heads=4, kv_heads=2, key_dim=1, value_dim=1, scale=1)
        data = AttentionInputs(q=(0.0,) * 8, k=(0.0,) * 6, v=(2.0, 4.0, 102.0, 10.0, 20.0, 60.0))
        result = reference_attention(p, data)
        self.assertEqual(result.output, (3.0, 36.0, 3.0, 36.0, 15.0, 30.0, 15.0, 30.0))
        self.assertEqual(result.probabilities[:3], (0.5, 0.5, 0.0))

    # Random rectangular shapes span MHA/GQA/MQA, multiple batches, and distinct D/Dv.
    def test_independent_float_reference(self):
        rng = random.Random(2311)
        for _ in range(60):
            hkv, q = rng.choice((1, 2)), rng.randrange(1, 4)
            kv, causal = q + rng.randrange(4), rng.choice((True, False))
            p = spec(batch_size=rng.choice((1, 2)), query_heads=hkv * rng.choice((1, 2, 3)), kv_heads=hkv,
                     query_length=q, kv_length=kv, causal=causal, query_start=kv - q if causal else 0,
                     key_dim=rng.randrange(1, 4), value_dim=rng.randrange(1, 4))
            data = generate_attention(p, rng.randrange(1000))
            actual = reference_attention(p, data)
            output, probabilities = float_reference(p, data)
            self.assertTrue(all(isclose(a, b, rel_tol=1e-12, abs_tol=1e-15) for a, b in zip(actual.output, output)))
            self.assertTrue(all(isclose(a, b, rel_tol=1e-12, abs_tol=1e-15) for a, b in zip(actual.probabilities, probabilities)))

    # Explicitly replicate K/V heads in an independent layout; GQA outputs must match MHA with shared values.
    def test_gqa_equals_explicit_replication(self):
        p = spec(batch_size=2, query_heads=6, kv_heads=2)
        data = generate_attention(p, 11)
        expanded = {}
        for name, dim in (('k', p.key_dim), ('v', p.value_dim)):
            values = getattr(data, name)
            expanded[name] = tuple(value for b in range(p.batch_size) for h in range(p.query_heads)
                                   for value in values[(b * p.kv_heads + h // 3) * p.kv_length * dim:][:p.kv_length * dim])
        mha = replace(p, kv_heads=p.query_heads)
        self.assertEqual(reference_attention(p, data).output, reference_attention(mha, AttentionInputs(q=data.q, **expanded)).output)
        self.assertEqual(describe_attention(mha).kv_bytes, 3 * describe_attention(p).kv_bytes)

    # Huge common logits plus a one-unit residual survive exact dot-product and shift before float conversion.
    def test_extreme_common_offset(self):
        p = spec(query_heads=1, query_length=1, kv_length=2, key_dim=2, value_dim=1,
                 scale=1, causal=False, query_start=0)
        data = AttentionInputs(q=(1e308, 1.0), k=(2.0, 0.0, 2.0, 1.0), v=(0.0, 1.0))
        self.assertAlmostEqual(reference_attention(p, data).output[0], 1 / (1 + exp(-1)), delta=1e-15)
        self.assertEqual(reference_softmax((1e308, 1e308)), (0.5, 0.5))

    # Probability output may round to zero, while a large V still gives a representable weighted contribution.
    def test_probability_underflow_does_not_erase_weighted_output(self):
        p = spec(query_heads=1, query_length=1, kv_length=2, key_dim=1, value_dim=1,
                 scale=1, causal=False, query_start=0)
        result = reference_attention(p, AttentionInputs(q=(1.0,), k=(0.0, -1000.0), v=(0.0, 1e308)))
        with localcontext() as context:
            context.prec = 100
            tiny = Decimal(-1000).exp()
            expected = float(tiny * Decimal.from_float(1e308) / (1 + tiny))
        self.assertEqual(result.probabilities, (1.0, 0.0))
        self.assertGreater(result.output[0], 0)
        self.assertAlmostEqual(result.output[0] / expected, 1, delta=1e-14)

    # Host Decimal settings cannot change reference output or leak out of the function.
    def test_decimal_context_isolation(self):
        data = generate_attention(spec(), 1)
        expected = reference_attention(spec(), data)
        with localcontext() as context:
            context.prec = 3
            context.rounding = ROUND_DOWN
            context.traps[Inexact] = True
            self.assertEqual(reference_attention(spec(), data), expected)
            self.assertEqual(context.prec, 3)

    # Semantic identities bind scale/mask/values; mutable lists are owned and deterministic seeds are bounded.
    def test_identity_generation_and_ownership(self):
        p = spec()
        data = generate_attention(p, 5)
        self.assertEqual((data.q[:3], data.k[:3], data.v[:3]),
                         ((0.0, -0.4375, 0.0625), (-0.125, -0.5, 0.0625), (-0.125, 0.4375, -0.25)))
        self.assertEqual(generate_attention(p, 5), data)
        self.assertNotEqual(generate_attention(p, 6), data)
        self.assertNotEqual(attention_identity(p, data), attention_identity(replace(p, scale=1), data))
        q = list(data.q)
        owned = replace(data, q=q)
        q[0] = 10.0
        self.assertEqual(owned, data)
        self.assertEqual(reference_attention(p, data).input_identity, attention_identity(p, data))

    # Reject ill-defined grouping, empty rows, nonfinite data and unsupported input containers before evaluation.
    def test_contract_rejections(self):
        for changes in ({'query_heads': 3, 'kv_heads': 2}, {'scale': True}, {'scale': float('inf')},
                        {'query_length': 0}, {'query_start': 2}, {'causal': False}, {'batch_size': True}, {'dtype': 'float32'}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                spec(**changes)
        data = generate_attention(spec(), 0)
        for value in ({0.5: 'value'}, iter((0.5,)), (1,), (float('nan'),)):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                replace(data, q=value)
        with self.assertRaises(ValueError):
            validate_attention(spec(), replace(data, q=()))
        with self.assertRaises(ValueError):
            reference_softmax(())

    # Analytical integer counts need no tensor allocation; reference and generation budgets fail before computation.
    def test_large_counts_and_host_limits(self):
        huge = spec(key_dim=10**100)
        self.assertEqual(describe_attention(huge).dense_qk_macs, 12 * 10**100)
        with self.assertRaisesRegex(ValueError, 'max_elements'):
            generate_attention(huge, 0)
        data = generate_attention(spec(), 0)
        for kwargs in ({'max_score_pairs': 11}, {'max_macs': 49}, {'precision_digits': 20}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                reference_attention(spec(), data, **kwargs)
        for seed in (True, -1, 1 << 64):
            with self.assertRaises(ValueError):
                generate_attention(spec(), seed)


if __name__ == '__main__':
    unittest.main()
