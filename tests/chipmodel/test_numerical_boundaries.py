"""基础收尾：独立Decimal参考、打包枚举和直接/配置输入契约；极值用于数值审计，不作器件参数。"""

from dataclasses import replace
from decimal import Decimal, localcontext
import random
import unittest

from chipmodel.compute.cim.arrays.conductance import ConductanceArray, ConductanceArrayParams, transimpedance
from chipmodel.control.data_movement import TensorLayout
from chipmodel.interconnect.d2d.link import SerialLinkParams, estimate_link
from chipmodel.packaging.thermal.rc import ThermalRc
from configuration.resolution.dataclass_config import resolve_dataclass


# 使用简明8b/10b线路参数，独立枚举逐包开销和最后lane beat。
def link_params(**changes):
    return replace(SerialLinkParams(lane_count=3, lane_rate_bps=1024, coding_data_bits=8,
                   coding_wire_bits=10, max_payload_bytes=7, packet_overhead_bytes=2, fixed_latency_s=0.25), **changes)


# 稳定数值只保证给定数学模型正确，不证明极值对应真实硬件。
class NumericalBoundaryTests(unittest.TestCase):
    # 逐包列出编码bit，再逐beat计数；覆盖零、尾包与多lane，不复用ceil_div。
    def test_serial_packet_enumeration(self):
        for lanes in (1, 3, 8):
            p = link_params(lane_count=lanes)
            for payload in range(40):
                packets = [min(7, payload - start) for start in range(0, payload, 7)]
                encoded = sum((size + 2) * 10 for size in packets)
                wire = len(range(0, encoded, lanes)) * lanes
                result = estimate_link(p, payload)
                self.assertEqual((result.packet_count, result.protocol_bytes, result.wire_bits),
                                 (len(packets), len(packets) * 2, wire))
                self.assertEqual(result.completion_time_s, 0.25 + wire / (lanes * 1024) if payload else 0)

    # bit计数超出binary64仍可有有限商；最终非有限的时间须显式失败。
    def test_serial_large_count_finite_quotient(self):
        p = link_params(lane_count=1, lane_rate_bps=1e308, coding_wire_bits=8,
                        max_payload_bytes=1, packet_overhead_bytes=0, fixed_latency_s=0)
        with localcontext() as context:
            context.prec = 400
            expected = float(Decimal(8 * 10**308) / Decimal.from_float(1e308))
        self.assertEqual(estimate_link(p, 10**308).completion_time_s, expected)
        self.assertEqual(estimate_link(p, 10**308).wire_bits, 8 * 10**308)
        with self.assertRaises(ValueError):
            estimate_link(replace(p, lane_rate_bps=1), 10**308)

    # 长时间冷却必须收敛到300K；高初温不能在减法抵消后变成0K。
    def test_thermal_long_cooling(self):
        rc = ThermalRc(resistance_k_per_w=1, capacitance_j_per_k=1, ambient_temperature_k=300)
        for initial in (300, 1e20, 1e308):
            self.assertEqual(rc.temperature_after(initial_temperature_k=initial, power_w=0, duration_s=1000), 300)
            self.assertEqual(rc.temperature_after(initial_temperature_k=initial, power_w=0, duration_s=0), initial)

    # 独立高精度解析参考跨越冷热方向和长短时间常数，结果始终位于初温/稳态之间。
    def test_thermal_decimal_extremes(self):
        rng = random.Random(2310)
        with localcontext() as context:
            context.prec = 100
            for _ in range(70):
                initial = 10.0 ** rng.uniform(1, 100)
                duration = 10.0 ** rng.uniform(-12, 3)
                power = 10.0 ** rng.uniform(0, 100)
                rc = ThermalRc(resistance_k_per_w=2, capacitance_j_per_k=0.5, ambient_temperature_k=300)
                decay = (-Decimal.from_float(duration)).exp()
                steady = Decimal(300) + 2 * Decimal.from_float(power)
                expected = float(steady * (1 - decay) + Decimal.from_float(initial) * decay)
                actual = rc.temperature_after(initial_temperature_k=initial, power_w=power, duration_s=duration)
                self.assertAlmostEqual(actual / expected, 1, delta=5e-15)
                self.assertLessEqual(actual, max(initial, rc.steady_temperature(power)))
                self.assertGreaterEqual(actual, min(initial, rc.steady_temperature(power)))

    # I=GᵀV有有限结果时，中间大电流的抵消不能溢出；精确零与负电流均保留。
    def test_array_cancellation_and_sign(self):
        p = ConductanceArrayParams(rows=3, columns=1, conductance_min_s=0,
                                   conductance_max_s=1e308, max_abs_input_v=1)
        array = ConductanceArray(params=p, conductances_s=((1e308,),) * 3)
        self.assertEqual(array.evaluate((1, 1, -1)), (1e308,))
        self.assertEqual(array.evaluate((-1, -1, 1)), (-1e308,))
        self.assertEqual(array.evaluate((1, 0, -1)), (0,))
        with self.assertRaises(ValueError):
            array.evaluate((1, 1, 1))

    # 两个半subnormal贡献相加可表示；非零最终结果下溢必须拒绝。
    def test_array_subnormal_sum(self):
        p = ConductanceArrayParams(rows=2, columns=1, conductance_min_s=0,
                                   conductance_max_s=1, max_abs_input_v=1)
        array = ConductanceArray(params=p, conductances_s=((5e-324,), (5e-324,)))
        self.assertEqual(array.evaluate((0.5, 0.5)), (5e-324,))
        for voltage in (0.25, -0.25):
            with self.assertRaisesRegex(ValueError, 'underflows'):
                array.evaluate((voltage, 0))

    # 200位Decimal乘加对照真实binary64输入，并检查偏置抵消前溢出的回归。
    def test_tia_decimal_and_cancellation(self):
        self.assertEqual(transimpedance((1e308,), gain_ohm=2, offset_v=-1e308), (1e308,))
        rng = random.Random(24)
        with localcontext() as context:
            context.prec = 200
            for _ in range(50):
                currents = tuple(rng.uniform(-1, 1) for _ in range(4))
                gain, offset = rng.uniform(-100, 100), rng.uniform(-1, 1)
                expected = tuple(float(Decimal.from_float(i) * Decimal.from_float(gain)
                                       + Decimal.from_float(offset)) for i in currents)
                self.assertEqual(transimpedance(currents, gain_ohm=gain, offset_v=offset), expected)
        with self.assertRaisesRegex(ValueError, 'underflows'):
            transimpedance((-5e-324,), gain_ohm=0.25, offset_v=0)

    # 字典/惰性迭代器不能冒充维度或坐标；列表冻结，广播和非连续地址仍合法。
    def test_layout_strict_sequences_and_freezing(self):
        fields = dict(shape=[2, 3], strides_bytes=[0, 8], element_bytes=4, base_address_bytes=7)
        layout = TensorLayout(**fields)
        resolved = resolve_dataclass(TensorLayout, fields)
        fields['shape'][0] = 20
        self.assertEqual(layout, resolved)
        self.assertEqual((layout.logical_bytes, layout.span_bytes, layout.address([1, 2])), (24, 20, 23))
        for bad in ({2: 'value'}, iter((2,)), '2'):
            with self.assertRaises(TypeError):
                replace(layout, shape=bad)
        for bad in ({0: 'value', 1: 'value'}, iter((0, 1)), '01'):
            with self.assertRaises(TypeError):
                layout.address(bad)
        with self.assertRaises(TypeError):
            replace(layout, strides_bytes={0: 'value', 8: 'value'})

    # 直接CIM原语与CH5台架采用相同的有限序列输入语义，拒绝隐式字典键数据。
    def test_array_sequence_contracts(self):
        p = ConductanceArrayParams(rows=1, columns=1, conductance_min_s=0, conductance_max_s=1, max_abs_input_v=1)
        array = ConductanceArray(params=p, conductances_s=[[0.5]])
        for bad in ({0.5: 'value'}, iter((0.5,))):
            with self.assertRaises(TypeError):
                array.evaluate(bad)
        with self.assertRaises(TypeError):
            ConductanceArray(params=p, conductances_s=({0.5: 'value'},))
        with self.assertRaises(TypeError):
            transimpedance({0.5: 'value'}, gain_ohm=1, offset_v=0)


if __name__ == '__main__':
    unittest.main()
