"""Independent small arithmetic examples and workload boundary checks."""

from dataclasses import replace
import unittest

from contracts.workload.linear import LinearInputs, LinearSpec, input_identity, validate_inputs
from workloads.kernels.linear import describe_work, generate_inputs, matvec_spec
from workloads.reference.linear import compare_output, reference_linear


# Check semantic contracts without using a compiler or hardware model as the reference.
class LinearWorkloadTests(unittest.TestCase):
    # Hand-computed rectangular product and 2-operation-per-MAC accounting.
    def test_rectangular_reference_and_counts(self):
        spec = LinearSpec(m=2, n=2, k=3)
        inputs = LinearInputs(a=(1, 2, 3, 4, 5, 6), b=(7, 8, 9, 10, 11, 12))
        self.assertEqual(reference_linear(spec, inputs), (58, 64, 139, 154))
        work = describe_work(spec)
        self.assertEqual((work.macs, work.conventional_operations), (12, 24))
        self.assertEqual((work.a_bytes, work.b_bytes, work.output_bytes), (6, 6, 32))

    # MatVec keeps signed exact arithmetic and explicit 64-bit result storage.
    def test_matvec_and_int8_extremes(self):
        spec = matvec_spec(2, 3)
        self.assertEqual(reference_linear(spec, LinearInputs(a=(1, 2, 3, 4, 5, 6), b=(-1, 0, 2))), (5, 8))
        extreme = LinearSpec(m=1, n=1, k=2)
        self.assertEqual(reference_linear(extreme, LinearInputs(a=(-128, 127), b=(-128, 127))), (32513,))
        self.assertEqual((extreme.operand_bytes, extreme.result_bytes, extreme.result_dtype), (1, 8, "int64"))

    # Reject malformed extents and unsupported semantics before allocating any buffers.
    def test_invalid_specs(self):
        for dimension in (0, -1, True, 1.0):
            with self.subTest(dimension=dimension), self.assertRaises((TypeError, ValueError)):
                LinearSpec(m=dimension, n=1, k=1)
        for changes in ({"dtype": "float16"}, {"schema_version": "v2"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(LinearSpec(m=1, n=1, k=1), **changes)
        limit = ((1 << 63) - 1) // (128 * 128)
        LinearSpec(m=1, n=1, k=limit)
        with self.assertRaisesRegex(ValueError, "INT64"):
            LinearSpec(m=1, n=1, k=limit + 1)

    # Buffers own immutable snapshots and exclude nested, bool and nonfinite values.
    def test_input_ownership_and_scalar_validation(self):
        original = [1, 2]
        inputs = LinearInputs(a=original, b=[3, 4])
        original[0] = 99
        self.assertEqual(inputs.a, (1, 2))
        for bad in ([True], [[1]], [float("nan")], [float("inf")], "12"):
            with self.subTest(bad=bad), self.assertRaises((TypeError, ValueError)):
                LinearInputs(a=bad, b=(1,))

    # Shape and dtype errors cannot silently coerce int, float or out-of-range INT8 operands.
    def test_shape_and_dtype_validation(self):
        spec = LinearSpec(m=1, n=1, k=1)
        for a in ((), (1, 2), (128,), (-129,), (1.0,)):
            with self.subTest(a=a), self.assertRaises(ValueError):
                validate_inputs(spec, LinearInputs(a=a, b=(1,)))
        with self.assertRaises(TypeError):
            validate_inputs(replace(spec, dtype="float64"), LinearInputs(a=(1,), b=(1,)))

    # Freeze generator version with an independently recorded small golden vector and identity.
    def test_deterministic_generation_and_identity(self):
        spec = LinearSpec(m=2, n=2, k=3)
        inputs = generate_inputs(spec, 7)
        self.assertEqual(inputs.a, (-5, -4, 0, 3, 3, -4))
        self.assertEqual(inputs.b, (-6, -1, 3, 7, 2, 4))
        self.assertEqual(input_identity(spec, inputs), "78bd7ad62fd9386289f0716a839b4b59a0707005112c1a4a059ae471f319b8ab")
        self.assertEqual(inputs, generate_inputs(spec, 7))
        self.assertNotEqual(input_identity(spec, inputs), input_identity(spec, generate_inputs(spec, 8)))
        self.assertNotEqual(spec.identity_hash, replace(spec, dtype="float64").identity_hash)
        floating = generate_inputs(replace(spec, dtype="float64"), 7)
        self.assertEqual(floating.a, tuple(value / 16.0 for value in inputs.a))

    # Generation and reference enumeration reject unsafe host work before materialization.
    def test_host_work_limits(self):
        spec = LinearSpec(m=2, n=2, k=3)
        for seed in (-1, 1 << 64, True, 0.5):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                generate_inputs(spec, seed)
        with self.assertRaisesRegex(ValueError, "max_elements"):
            generate_inputs(spec, 0, max_elements=11)
        with self.assertRaisesRegex(ValueError, "max_macs"):
            reference_linear(spec, generate_inputs(spec, 0), max_macs=11)

    # Exact rational accumulation preserves the residual that native sequential binary64 loses.
    def test_float_reference_cancellation(self):
        spec = LinearSpec(m=1, n=1, k=3, dtype="float64")
        inputs = LinearInputs(a=(1e16, 1.0, -1e16), b=(1.0, 1.0, 1.0))
        self.assertEqual(reference_linear(spec, inputs), (1.0,))
        quality = compare_output(spec, (0.0,), (1.0,), atol=0.0, rtol=0.0)
        self.assertFalse(quality.passed)
        self.assertEqual((quality.mismatched_indices, quality.max_absolute_error), ((0,), 1.0))
        self.assertTrue(compare_output(spec, (0.0,), (1.0,), atol=1.0, rtol=0.0).passed)

    # Integer comparison is exact even with loose tolerances; invalid comparison arithmetic is rejected.
    def test_quality_contract(self):
        spec = LinearSpec(m=1, n=1, k=1)
        self.assertFalse(compare_output(spec, (2,), (1,), atol=1e20, rtol=1e20).passed)
        for actual in ((True,), (1.0,)):
            with self.subTest(actual=actual), self.assertRaises(TypeError):
                compare_output(spec, actual, (1,))
        with self.assertRaises(ValueError):
            compare_output(spec, (), (1,))
        for tolerance in (-1.0, float("nan"), True):
            with self.subTest(tolerance=tolerance), self.assertRaises(ValueError):
                compare_output(spec, (1,), (1,), atol=tolerance)
        floating = replace(spec, dtype="float64")
        for actual, expected in ((float("inf"), 1.0), (1e308, -1e308)):
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                compare_output(floating, (actual,), (expected,))


if __name__ == "__main__":
    unittest.main()
