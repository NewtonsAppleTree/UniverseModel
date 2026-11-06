"""ADC 数值与分析验证：手算码值、独立阈值参考、发起/完成时间表。"""

from bisect import bisect_right
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from math import inf, nan, nextafter
import sys
import unittest

from chipmodel.compute.cim.periphery.adc import AdcParams, IdealAdc, derive_adc


def make_params(**changes) -> AdcParams:
    params = AdcParams(
        resolution_bits=10,
        lane_count=4,
        conversion_cycles=2,
        initiation_interval_cycles=2,
        input_min_v=0.0,
        input_max_v=1.0,
    )
    return replace(params, **changes)


class AdcParameterTests(unittest.TestCase):
    def test_hand_calculated_spec(self):
        derived = derive_adc(make_params(), frequency_hz=1e9)
        self.assertEqual(derived.code_count, 1024)
        self.assertEqual(derived.quantization_step_v, 0.0009765625)
        self.assertEqual(derived.conversion_time_s, 2e-9)
        self.assertEqual(derived.initiation_interval_s, 2e-9)
        self.assertEqual(derived.ideal_conversions_per_s, 2e9)
        self.assertEqual(derived.minimum_inflight_per_lane, 1)

    def test_counts_reject_bool_float_and_nonpositive_values(self):
        for name in ("resolution_bits", "lane_count", "conversion_cycles",
                     "initiation_interval_cycles"):
            for value in (True, 2.0, "2", None):
                with self.subTest(name=name, value=value):
                    with self.assertRaisesRegex(TypeError, name):
                        make_params(**{name: value})
            for value in (0, -1):
                with self.subTest(name=name, value=value):
                    with self.assertRaisesRegex(ValueError, name):
                        make_params(**{name: value})

    def test_resolution_support_domain(self):
        for bits in (1, 53):
            derived = derive_adc(make_params(resolution_bits=bits), frequency_hz=1e9)
            self.assertEqual(derived.code_count, 2**bits)
        for bits in (54, 10**100):
            with self.assertRaisesRegex(ValueError, "resolution_bits"):
                make_params(resolution_bits=bits)

    def test_voltage_input_types_and_ranges(self):
        for name in ("input_min_v", "input_max_v"):
            for value in (True, "1 V", None):
                with self.subTest(name=name, value=value):
                    with self.assertRaisesRegex(TypeError, name):
                        make_params(**{name: value})
            for value in (nan, inf, -inf, 10**400):
                with self.subTest(name=name, value=value):
                    with self.assertRaisesRegex(ValueError, name):
                        make_params(**{name: value})
        for upper in (0.0, -1.0):
            with self.assertRaisesRegex(ValueError, "input_max_v"):
                make_params(input_max_v=upper)

    def test_nonrepresentable_lsb_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "quantization_step_v"):
            make_params(resolution_bits=1, input_max_v=nextafter(0.0, inf))

    def test_frequency_validation(self):
        for frequency in (True, "1 GHz", None):
            with self.assertRaisesRegex(TypeError, "frequency_hz"):
                derive_adc(make_params(), frequency_hz=frequency)
        for frequency in (0, -1, nan, inf, 10**400):
            with self.assertRaisesRegex(ValueError, "frequency_hz"):
                IdealAdc(params=make_params(), frequency_hz=frequency)

    def test_derived_overflow_is_reported(self):
        with self.assertRaisesRegex(ValueError, "conversion_time_s"):
            derive_adc(make_params(), frequency_hz=1e-320)
        with self.assertRaisesRegex(ValueError, "ideal_conversions_per_s"):
            derive_adc(make_params(lane_count=10**400), frequency_hz=1e9)

    def test_representable_results_survive_large_intermediates(self):
        # P*f 会溢出 float，但 P*f/II 仍可表示；先精确求比值再转 float。
        p = make_params(lane_count=10**200, conversion_cycles=10**200,
                        initiation_interval_cycles=10**200)
        d = derive_adc(p, frequency_hz=1e200)
        self.assertEqual(d.ideal_conversions_per_s, 1e200)
        self.assertAlmostEqual(d.conversion_time_s, 1.0)

    def test_wrong_parameter_object_is_rejected(self):
        with self.assertRaisesRegex(TypeError, "AdcParams"):
            derive_adc({}, frequency_hz=1e9)


class AdcQuantizationTests(unittest.TestCase):
    def setUp(self):
        self.adc = IdealAdc(params=make_params(), frequency_hz=1e9)

    def test_known_codes_and_overrange_flags(self):
        samples = self.adc.convert_many((-0.1, 0.0, 0.25, 0.5, 0.999, 1.0, 1.1))
        self.assertEqual([x.code for x in samples], [0, 0, 256, 512, 1022, 1023, 1023])
        self.assertEqual([x.clipped_low for x in samples], [True] + [False] * 6)
        self.assertEqual([x.clipped_high for x in samples], [False] * 6 + [True])

    def test_each_transition_and_adjacent_binary64_inputs(self):
        for code in range(1, 1024):
            threshold = code / 1024
            with self.subTest(code=code):
                self.assertEqual(self.adc.convert(nextafter(threshold, -inf)).code, code - 1)
                self.assertEqual(self.adc.convert(threshold).code, code)
                self.assertEqual(self.adc.convert(nextafter(threshold, inf)).code, code)

    def test_bipolar_range_remains_offset_binary(self):
        adc = IdealAdc(params=make_params(resolution_bits=3, input_min_v=-1.0),
                       frequency_hz=1e9)
        self.assertEqual([x.code for x in adc.convert_many((-1, -0.75, -0.5, 0, 0.5, 1))],
                         [0, 1, 2, 4, 6, 7])
        # 浮点式 (V+1)/0.25 会把这个略小于零的输入误算为 code=4。
        self.assertEqual(adc.convert(nextafter(0.0, -inf)).code, 3)
        self.assertEqual(adc.convert(nextafter(0.0, inf)).code, 4)

    def test_non_dyadic_range_against_independent_threshold_search(self):
        adc = IdealAdc(params=make_params(resolution_bits=4, input_min_v=-0.1,
                                         input_max_v=0.2), frequency_hz=1e9)
        # 独立算法：Decimal 阈值表 + 搜索，而非重复模型的 Fraction floor。
        with localcontext() as ctx:
            ctx.prec = 100
            lower, upper = Decimal.from_float(-0.1), Decimal.from_float(0.2)
            thresholds = [lower + (upper - lower) * k / 16 for k in range(1, 16)]
            inputs = [k / 1000 for k in range(-120, 221)]
            for threshold in thresholds:
                v = float(threshold)
                inputs.extend((nextafter(v, -inf), v, nextafter(v, inf)))
            for voltage in inputs:
                expected = bisect_right(thresholds, Decimal.from_float(voltage))
                with self.subTest(voltage=voltage):
                    self.assertEqual(adc.convert(voltage).code, expected)

    def test_53_bit_code_boundary(self):
        adc = IdealAdc(params=make_params(resolution_bits=53), frequency_hz=1e9)
        self.assertEqual(adc.convert(0.5).code, 2**52)
        self.assertEqual(adc.convert(nextafter(1.0, 0.0)).code, 2**53 - 1)

    def test_large_finite_bipolar_range(self):
        adc = IdealAdc(params=make_params(resolution_bits=1,
                                         input_min_v=-sys.float_info.max,
                                         input_max_v=sys.float_info.max), frequency_hz=1e9)
        self.assertEqual(adc.derived.quantization_step_v, sys.float_info.max)
        self.assertEqual(adc.convert(-1.0).code, 0)
        self.assertEqual(adc.convert(0.0).code, 1)

    def test_invalid_samples_and_empty_batch(self):
        for value in (nan, inf, -inf, 10**400):
            with self.assertRaisesRegex(ValueError, "voltage_v"):
                self.adc.convert(value)
        for value in (True, "0.5", None):
            with self.assertRaisesRegex(TypeError, "voltage_v"):
                self.adc.convert(value)
        self.assertEqual(self.adc.convert_many(iter(())), ())
        with self.assertRaises(ValueError):
            self.adc.convert_many(iter((0.25, nan)))
        self.assertEqual(self.adc.convert(0.25).code, 256)


class AdcTimingAndIsolationTests(unittest.TestCase):
    def test_partial_groups_and_empty_batch(self):
        adc = IdealAdc(params=make_params(), frequency_hz=1e9)
        # 4 lanes 每 2 cycles 发起一批，末批不满时仍只付一次转换延迟。
        for count, groups, cycles in ((0, 0, 0), (1, 1, 2), (4, 1, 2),
                                       (5, 2, 4), (16, 4, 8), (17, 5, 10)):
            with self.subTest(count=count):
                result = adc.estimate_batch(count)
                self.assertEqual((result.sample_count, result.group_count,
                                  result.completion_cycles), (count, groups, cycles))
                self.assertAlmostEqual(result.completion_time_s * 1e9, cycles)

    def test_latency_and_ii_are_independent(self):
        # 三批发起于 0/2/4，完成于 5/7/9；流水线至少容纳每 lane 3 个在途样本。
        pipelined = IdealAdc(params=make_params(conversion_cycles=5), frequency_hz=1e9)
        self.assertEqual(pipelined.estimate_batch(9).completion_cycles, 9)
        self.assertEqual(pipelined.derived.minimum_inflight_per_lane, 3)
        # 有恢复间隔的转换器：发起于 0/5/10，完成于 2/7/12。
        recovering = IdealAdc(params=make_params(initiation_interval_cycles=5),
                              frequency_hz=1e9)
        self.assertEqual(recovering.estimate_batch(9).completion_cycles, 12)
        self.assertEqual(recovering.derived.minimum_inflight_per_lane, 1)

    def test_lane_and_clock_changes_have_separate_effects(self):
        original = IdealAdc(params=make_params(), frequency_hz=1e9)
        wider = replace(original, params=replace(original.params, lane_count=8))
        faster = replace(original, frequency_hz=2e9)
        self.assertEqual(original.estimate_batch(16).completion_cycles, 8)
        self.assertEqual(wider.estimate_batch(16).completion_cycles, 4)
        self.assertEqual(faster.estimate_batch(16).completion_cycles, 8)
        self.assertEqual(faster.estimate_batch(16).completion_time_s, 4e-9)
        self.assertEqual(wider.derived.ideal_conversions_per_s, 4e9)
        self.assertEqual(original.convert_many((0.25, 0.5)), wider.convert_many((0.25, 0.5)))

    def test_freezing_and_reconfiguration(self):
        adc = IdealAdc(params=make_params(), frequency_hz=1e9)
        for obj, name, value in ((adc, "frequency_hz", 2e9), (adc.params, "lane_count", 8),
                                  (adc.derived, "code_count", 4096)):
            with self.assertRaises(FrozenInstanceError):
                setattr(obj, name, value)
        changed = replace(adc, params=replace(adc.params, resolution_bits=8))
        self.assertEqual(changed.convert(0.5).code, 128)
        self.assertEqual(adc.convert(0.5).code, 512)
        with self.assertRaises(ValueError):
            replace(adc.params, lane_count=0)

    def test_observation_and_calls_do_not_accumulate_state(self):
        adc = IdealAdc(params=make_params(), frequency_hz=1e9)
        before = adc.estimate_batch(16)
        adc.convert_many([0.25] * 16)
        repr(adc)
        self.assertEqual(adc.estimate_batch(16), before)

    def test_invalid_batch_counts_and_nonrepresentable_time(self):
        adc = IdealAdc(params=make_params(), frequency_hz=1e9)
        for value in (True, 1.0, "1", None):
            with self.assertRaisesRegex(TypeError, "sample_count"):
                adc.estimate_batch(value)
        with self.assertRaisesRegex(ValueError, "sample_count"):
            adc.estimate_batch(-1)
        with self.assertRaisesRegex(ValueError, "completion_time_s"):
            adc.estimate_batch(10**400)


if __name__ == "__main__":
    unittest.main()
