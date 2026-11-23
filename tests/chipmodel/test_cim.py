"""CH5 独立整数/有理参考、电压链、有限保持与跨阶段资源约束。"""

from dataclasses import replace
from fractions import Fraction
from math import nextafter
import random
import unittest

from chipmodel.common import ClockDomain, PipelineParams
from chipmodel.composition.bounds import ActionEstimate, estimate_time_bounds
from chipmodel.composition.graph import ResourceNode
from chipmodel.composition.tile.cim import CimStage, CimTile, analyze_cim
from chipmodel.compute.cim.arrays.conductance import ConductanceArrayParams
from chipmodel.compute.cim.encoding.bit_serial import BitSerialParams
from chipmodel.compute.cim.matvec import CimInput, CimNumericParams, encode_conductances, evaluate_cim
from chipmodel.compute.cim.periphery.adc import AdcParams
from chipmodel.compute.cim.periphery.dac import SampleHoldLimits, VoltageDac


# 二进制可精确表示的电气夹具：每权重digit产生1/4 V，ADC的零点位于bin中心。
def fixture():
    p = CimNumericParams(encoding=BitSerialParams(input_bits=3, magnitude_bits=3, cell_bits=2,
                         differential=True, subtract_before_adc=True),
                         array=ConductanceArrayParams(rows=2, columns=3, conductance_min_s=1/4096,
                                                      conductance_max_s=1/256, max_abs_input_v=0.25),
                         conductance_step_s=1/1024, dac=VoltageDac(resolution_bits=1, output_min_v=0, output_max_v=0.25),
                         tia_gain_ohm=1024, tia_offset_v=0,
                         adc=AdcParams(resolution_bits=6, lane_count=2, conversion_cycles=3,
                                       initiation_interval_cycles=1, input_min_v=-2.03125, input_max_v=1.96875), output_bits=16)
    inputs = CimInput(work_id="fixture", input_codes=(3, 5), weights=((1, -2, 5), (-3, 4, -1)))
    arrays = tuple(f"array/{i}" for i in range(4))
    nodes = (ResourceNode(instance_id="tile", parent_id=None, model_id=None),
             *(ResourceNode(instance_id=key, parent_id="tile", model_id="detail") for key in (*arrays, "dac", "tia", "adc", "hold", "digital")))
    clock = ClockDomain(domain_id="clock", frequency_hz=1e9)
    unit = PipelineParams(lane_count=1, latency_cycles=1, initiation_interval_cycles=1)
    tile = CimTile(numeric=p, nodes=nodes, array_resource_ids=arrays, array_pipeline=replace(unit, latency_cycles=2),
                    array_clock=clock, dac=CimStage(resource_id="dac", clock=clock, pipeline=replace(unit, lane_count=2, latency_cycles=2)),
                    tia=CimStage(resource_id="tia", clock=clock, pipeline=unit), adc_resource_id="adc", adc_clock=clock,
                    mux_settle_cycles=1, adc_inflight_per_lane=3, hold_resource_id="hold",
                    hold=SampleHoldLimits(slot_count=6, valid_duration_s=20e-9),
                    digital=CimStage(resource_id="digital", clock=clock, pipeline=unit), code_buffer_slots=6,
                    accumulator_slots=3, profile_source="independent binary fixture/v1; not calibrated")
    return tile, inputs


# 功能验证不从硬件动作量公式推导期望输出。
class CimNumericTests(unittest.TestCase):
    # 不同矩形/单列形状独立配置容量与量程，确保台架不绑定默认2×3矩阵。
    def test_rectangular_shapes_and_column_tails(self):
        base, _ = fixture()
        for rows, columns in ((1, 1), (1, 5), (3, 1), (3, 4), (4, 5)):
            data = CimInput(work_id="rectangle", input_codes=tuple(i + 1 for i in range(rows)),
                             weights=tuple(tuple((-1)**(i + j) * (j + 1) for j in range(columns)) for i in range(rows)))
            expected = tuple(sum(data.input_codes[i] * data.weights[i][j] for i in range(rows)) for j in range(columns))
            for before in (True, False):
                numeric = replace(base.numeric, array=replace(base.numeric.array, rows=rows, columns=columns),
                                  encoding=replace(base.numeric.encoding, subtract_before_adc=before),
                                  adc=replace(base.numeric.adc, resolution_bits=10, input_min_v=-8.0078125, input_max_v=7.9921875))
                tile = replace(base, numeric=numeric, dac=replace(base.dac, pipeline=replace(base.dac.pipeline, lane_count=rows)),
                               hold=replace(base.hold, slot_count=2 * columns), code_buffer_slots=2 * columns, accumulator_slots=columns)
                analysis = analyze_cim(tile, data)
                self.assertEqual(analysis.numeric.output, expected)
                self.assertEqual(analysis.counts.adc_conversions, columns * 6 * (1 if before else 2))

    # 手算点积为(-12,14,10)，两種差分位置都执行完整电压链。
    def test_exact_signed_output_and_voltage_chain(self):
        tile, data = fixture()
        for before in (True, False):
            p = replace(tile.numeric, encoding=replace(tile.numeric.encoding, subtract_before_adc=before))
            result = evaluate_cim(p, data)
            self.assertEqual(result.output, (-12, 14, 10))
            self.assertEqual(result.clipped_samples, 0)
            self.assertEqual(result.phases[0].partials, (-2, -2, 0))
            self.assertEqual(result.phases[0].row_voltages_v, (0.25, 0.25))
            if before:
                first = result.phases[0].readouts[0]
                self.assertEqual(Fraction(first.current_a), Fraction(-1, 2048))
                self.assertEqual((first.voltage_v, first.adc_sample.code), (-0.5, 24))
            self.assertEqual(result.programmed_arrays[0].conductances_s[0][0], 5/4096)
            self.assertEqual(result.programmed_arrays[1].conductances_s[1][0], 13/4096)

    # 80组全位宽随机小矩阵用Python整数点积，覆盖负权重、零和不同bit phase。
    def test_random_integer_reference(self):
        tile, data = fixture()
        rng = random.Random(517)
        for _ in range(80):
            x = tuple(rng.randrange(8) for _ in range(2))
            weights = tuple(tuple(rng.randrange(-7, 8) for _ in range(3)) for _ in range(2))
            expected = tuple(x[0] * weights[0][j] + x[1] * weights[1][j] for j in range(3))
            for before in (True, False):
                p = replace(tile.numeric, encoding=replace(tile.numeric.encoding, subtract_before_adc=before))
                self.assertEqual(evaluate_cim(p, replace(data, input_codes=x, weights=weights)).output, expected)

    # 3-bit幅度存入2-bit cell：最高slice只用一位；物理48bit包含未使用编码位。
    def test_tail_weight_slice_and_action_conservation(self):
        tile, data = fixture()
        result = analyze_cim(tile, data)
        c = result.counts
        self.assertEqual((c.logical_macs, c.physical_arrays, c.physical_weight_bits, c.phases), (6, 4, 48, 6))
        self.assertEqual((c.dac_updates, c.array_reads, c.cell_evaluations, c.adc_conversions), (12, 12, 72, 18))
        self.assertEqual((c.digital_reconstructions, c.digital_subtractions, c.shift_adds, c.digital_operations), (18, 0, 18, 36))
        self.assertEqual(result.numeric.programmed_arrays[2].conductances_s[0][2], 5/4096)
        self.assertEqual(tuple(phase.shift for phase in result.numeric.phases), (0, 2, 1, 3, 2, 4))
        after = analyze_cim(replace(tile, numeric=replace(tile.numeric, encoding=replace(tile.numeric.encoding, subtract_before_adc=False))), data)
        self.assertEqual((after.counts.cell_evaluations, after.counts.adc_conversions, after.counts.digital_operations), (72, 36, 72))

    # 无差分时移除Gmin已知基线；有差分时Gmin自然取消，负TIA增益也可恢复符号。
    def test_unsigned_baseline_and_negative_tia(self):
        tile, data = fixture()
        p = replace(tile.numeric, encoding=replace(tile.numeric.encoding, differential=False, subtract_before_adc=False))
        unsigned = replace(data, weights=((1, 2, 5), (3, 4, 1)))
        self.assertEqual(evaluate_cim(p, unsigned).output, (18, 26, 20))
        negative = replace(tile.numeric, tia_gain_ohm=-1024, tia_offset_v=0.125)
        self.assertEqual(evaluate_cim(negative, data).output, (-12, 14, 10))

    # 零输入仍执行声明的相位/转换，不能靠跳过工作制造成本下降。
    def test_zero_data_preserves_dense_work(self):
        tile, data = fixture()
        ordinary = evaluate_cim(tile.numeric, data)
        zero = evaluate_cim(tile.numeric, replace(data, input_codes=(0, 0)))
        self.assertEqual(zero.output, (0, 0, 0))
        self.assertEqual(zero.work, ordinary.work)
        self.assertEqual(sum(len(p.readouts) for p in zero.phases), 18)

    # 输出格式仅在最终执行error/saturate/wrap，量化功能与格式溢出分开。
    def test_output_overflow_policies(self):
        tile, data = fixture()
        with self.assertRaisesRegex(ValueError, "signed output width"):
            evaluate_cim(replace(tile.numeric, output_bits=4), data)
        saturated = evaluate_cim(replace(tile.numeric, output_bits=4, overflow="saturate"), data)
        wrapped = evaluate_cim(replace(tile.numeric, output_bits=4, overflow="wrap"), data)
        self.assertEqual(saturated.output, (-8, 7, 7))
        self.assertEqual(wrapped.output, (4, -2, -6))
        self.assertEqual(saturated.output_overflowed, (True, True, True))

    # 限幅和低精度是可观察的质量损失，不能标成精确计算通过。
    def test_clipping_and_coarse_quantization(self):
        tile, data = fixture()
        clipped = evaluate_cim(replace(tile.numeric, adc=replace(tile.numeric.adc, input_min_v=-0.125, input_max_v=0.125)), data)
        self.assertGreater(clipped.clipped_samples, 0)
        self.assertNotEqual(clipped.output, (-12, 14, 10))
        coarse = evaluate_cim(replace(tile.numeric, adc=replace(tile.numeric.adc, resolution_bits=2)), data)
        self.assertEqual(coarse.output, (50, 58, 54))
        self.assertEqual(coarse.clipped_samples, 0)

    # 来源/初态冻结，不同数据或编码的内容身份改变，重复调用没有遗留状态。
    def test_immutable_data_and_identity(self):
        tile, data = fixture()
        codes, weights = [3, 5], [[1, -2, 5], [-3, 4, -1]]
        frozen = CimInput(work_id="fixture", input_codes=codes, weights=weights)
        codes.clear()
        weights[0][0] = 7
        self.assertEqual(frozen, data)
        a, b = evaluate_cim(tile.numeric, data), evaluate_cim(tile.numeric, data)
        self.assertEqual(a, b)
        changed = evaluate_cim(tile.numeric, replace(data, input_codes=(1, 0)))
        self.assertNotEqual(a.input_identity, changed.input_identity)
        self.assertEqual(a.weight_identity, changed.weight_identity)

    # 输入/形状/电气域与宿主上限在执行前明确校验。
    def test_invalid_numeric_inputs(self):
        tile, data = fixture()
        for changes in (dict(input_codes=(8, 0)), dict(input_codes=(-1, 0)), dict(input_codes=(1,)),
                        dict(weights=((8, 0, 0), (0, 0, 0)))):
            with self.assertRaises(ValueError):
                evaluate_cim(tile.numeric, replace(data, **changes))
        for changes in (dict(input_codes="12"), dict(weights="bad"), dict(weights=(None,)), dict(input_codes=(True, 0))):
            with self.assertRaises((ValueError, TypeError)):
                replace(data, **changes)
        with self.assertRaisesRegex(ValueError, "host"):
            evaluate_cim(tile.numeric, data, max_cell_evaluations=71)
        for changes in (dict(tia_gain_ohm=0), dict(conductance_step_s=1), dict(output_bits=65),
                        dict(dac=VoltageDac(resolution_bits=2, output_min_v=0, output_max_v=0.25))):
            with self.assertRaises(ValueError):
                replace(tile.numeric, **changes)
        with self.assertRaises(ValueError):
            encode_conductances(tile.numeric, ((1, 2),))


# 时序oracle来自手算窗口和严格容量边界，不把宿主执行时长当作硬件时间。
class CimCompositionTests(unittest.TestCase):
    # 每phase为DAC2+array2+TIA3+MUX/ADC5+digital6=18ns；共6phase=108ns。
    def test_serial_policy_and_sample_times(self):
        tile, data = fixture()
        a = analyze_cim(tile, data)
        self.assertEqual(a.serial_policy_time_s, 108e-9)
        self.assertEqual(a.resource_lower_bound_s, 36e-9)
        self.assertEqual(a.bottlenecks, ("digital",))
        first = a.samples[:3]
        self.assertEqual([s.captured_s for s in first], [5e-9, 6e-9, 7e-9])
        self.assertEqual([s.adc_start_s for s in first], [8e-9, 8e-9, 9e-9])
        self.assertEqual([s.adc_complete_s for s in first], [11e-9, 11e-9, 12e-9])
        self.assertEqual([s.hold_age_s for s in first], [3e-9, 2e-9, 2e-9])
        self.assertEqual((a.peak_hold_samples, a.peak_code_slots, a.required_adc_inflight_per_lane), (3, 3, 2))
        self.assertEqual({s.sample_id for s in a.samples}, {r.sample_id for p in a.numeric.phases for r in p.readouts})

    # ADC增多不突破数字处理资源界；减慢ADC则转为ADC瓶颈且保持年龄增大。
    def test_adc_sensitivity_and_digital_bottleneck(self):
        tile, data = fixture()
        more = analyze_cim(replace(tile, numeric=replace(tile.numeric, adc=replace(tile.numeric.adc, lane_count=4))), data)
        slow = analyze_cim(replace(tile, adc_clock=replace(tile.adc_clock, frequency_hz=250e6)), data)
        self.assertEqual((more.resource_lower_bound_s, more.serial_policy_time_s), (36e-9, 102e-9))
        self.assertEqual((slow.resource_lower_bound_s, slow.serial_policy_time_s), (44e-9, 198e-9))
        self.assertEqual(slow.bottlenecks, ("adc",))
        self.assertEqual(max(s.hold_age_s for s in slow.samples), 8e-9)

    # 保持容量、ADC内部在途与数字寄存器是四个独立约束。
    def test_independent_capacities(self):
        tile, data = fixture()
        for changes in (dict(hold=replace(tile.hold, slot_count=2)), dict(adc_inflight_per_lane=1),
                        dict(code_buffer_slots=2), dict(accumulator_slots=2)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                analyze_cim(replace(tile, **changes), data)

    # 1Hz夹具使3秒边界可精确表示；等于期限可用，紧邻更小值失效。
    def test_hold_deadline_and_mux(self):
        tile, data = fixture()
        clock = ClockDomain(domain_id="exact", frequency_hz=1)
        tile = replace(tile, array_clock=clock, adc_clock=clock, dac=replace(tile.dac, clock=clock),
                       tia=replace(tile.tia, clock=clock), digital=replace(tile.digital, clock=clock),
                       hold=replace(tile.hold, valid_duration_s=3))
        self.assertEqual(max(s.hold_age_s for s in analyze_cim(tile, data).samples), 3)
        with self.assertRaisesRegex(ValueError, "age"):
            analyze_cim(replace(tile, hold=replace(tile.hold, valid_duration_s=nextafter(3, 0))), data)
        with self.assertRaisesRegex(ValueError, "age"):
            analyze_cim(replace(tile, mux_settle_cycles=4), data)

    # L<II时跨phase仍需等到同一资源可再发起，不能在上一批完成后立即重用。
    def test_cross_phase_initiation_interval(self):
        tile, data = fixture()
        tile = replace(tile, dac=replace(tile.dac, pipeline=replace(tile.dac.pipeline, initiation_interval_cycles=50)))
        a = analyze_cim(tile, data)
        starts = [w.first_issue_s for w in a.windows if w.resource_id == "dac"]
        self.assertEqual(starts, [0, 50e-9, 100e-9, 150e-9, 200e-9, 250e-9])
        self.assertEqual(a.serial_policy_time_s, 268e-9)
        self.assertEqual(a.resource_lower_bound_s, 252e-9)

    # 档位与包含关系不能增加硬件副本或同时收取摘要成本。
    def test_resource_ownership_and_shape_rejections(self):
        tile, _ = fixture()
        with self.assertRaises(ValueError):
            replace(tile, array_resource_ids=tile.array_resource_ids[:-1])
        with self.assertRaises(ValueError):
            replace(tile, adc_resource_id=tile.dac.resource_id)
        with self.assertRaises(ValueError):
            replace(tile, nodes=tuple(replace(n, parent_id=None) if n.instance_id == "adc" else n for n in tile.nodes))
        with self.assertRaises(ValueError):
            replace(tile, nodes=tuple(replace(n, parent_id="dac") if n.instance_id == "adc" else n for n in tile.nodes))
        with self.assertRaisesRegex(ValueError, "DAC lane"):
            replace(tile, dac=replace(tile.dac, pipeline=replace(tile.dac.pipeline, lane_count=1)))

    # 本地actions可接外部数据准备的完成依赖，资源ID/预算保持原样且不重复相加摘要。
    def test_composable_dependency_and_unknown_costs(self):
        tile, data = fixture()
        a = analyze_cim(tile, data)
        load = ActionEstimate(action_id="explicit-input-ready", latency_s=7e-9, dependencies=(), demands=())
        actions = (replace(a.actions[0], dependencies=(load.action_id,)), *a.actions[1:], load)
        bounds = estimate_time_bounds(actions, a.budgets)
        self.assertAlmostEqual(bounds.critical_path_s, 115e-9, delta=1e-20)
        self.assertIsNone(a.energy_j)
        self.assertIsNone(a.programming_time_s)
        self.assertIsNone(a.programming_energy_j)
        self.assertTrue(a.unknown_reasons)


if __name__ == "__main__":
    unittest.main()
