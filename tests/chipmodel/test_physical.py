"""几何唯一计量、动作/背景积分、CH8适配和独立热响应参考。"""

from dataclasses import replace
from decimal import Decimal, localcontext
from math import log
import random
import unittest

from chipmodel.composition.graph import ResourceNode
from chipmodel.packaging.evidence import (CostActivity, ObservationWindow, PhysicalModel, PhysicalWork,
    Placement, ResourceStructure, analyze_physical)
from chipmodel.packaging.geometry.floorplan import Rectangle
from chipmodel.packaging.thermal.rc import ThermalRc
from chipmodel.packaging.thermal.trace import PowerSegment, ThermalTrace, analyze_thermal_trace
from costmodel.interfaces.costs import CostKey, CostPoint, CostSource, OperatingPoint
from costmodel.providers.tabulated.lookup import CostTable


# 可独立构造的合成夹具，仅证明公式和所有权，不作为真实器件profile。
def fixture():
    source = CostSource(source_id="test-assumption", kind="assumption", reference="synthetic hand calculation", revision="v1",
        artifact_sha256=None, extraction="Explicit test parameters", limitations=("No device calibration",))
    op = OperatingPoint(process="synthetic", voltage_v=1, temperature_k=300)
    rect = Rectangle(x_mm=0, y_mm=0, width_mm=2, height_mm=2)
    nodes = (ResourceNode(instance_id="die", parent_id=None, model_id=None),
             ResourceNode(instance_id="a", parent_id="die", model_id="synthetic"),
             ResourceNode(instance_id="b", parent_id="die", model_id="synthetic"))
    model = PhysicalModel(scope_id="die", nodes=nodes, physical_ids=("a", "b"),
        structures=tuple(ResourceStructure(resource_id=key, structure_id=key, operating_point=op) for key in ("die", "a", "b")),
        static_selection=("a", "b"), boundary=rect, placements=(Placement(resource_id="die", rectangle=rect),), geometry_source=source)
    points = []
    for resource, area, leakage, energy in (("a", 1.0, 0.125, 0.25), ("b", 2.0, 0.25, 0.5), ("die", 3.0, 0.375, 0.75)):
        key = CostKey(structure_id=resource, operating_point=op, metric="area")
        points.extend((CostPoint(key=key, value=area, source=source, coverage="synthetic instance"),
                       CostPoint(key=replace(key, metric="leakage"), value=leakage, source=source, coverage="background only"),
                       CostPoint(key=replace(key, metric="dynamic", action="compute", work_unit="MAC"), value=energy,
                                 source=source, coverage="dynamic action only; excludes background")))
    work = PhysicalWork(activities=(CostActivity(activity_id="first", resource_id="a", action="compute", work_unit="MAC", amount=4),
                                   CostActivity(activity_id="second", resource_id="a", action="compute", work_unit="MAC", amount=2),
                                   CostActivity(activity_id="third", resource_id="b", action="compute", work_unit="MAC", amount=3)),
        activity_source="synthetic hand count", observation=ObservationWindow(duration_s=2, basis="assumed", source=source))
    return model, work, CostTable(table_id="test-only", points=tuple(points))


# 覆盖独立物理分析和几何反例，不依赖完整实验执行器。
class PhysicalTests(unittest.TestCase):
    # 静态资源只计一次，多个真实动作累计；E=6*0.25+3*0.5+(0.125+0.25)*2。
    def test_unique_costs_and_energy(self):
        model, work, table = fixture()
        r = analyze_physical(model, work, table)
        self.assertEqual((r.characterized_area_mm2, r.footprint_mm2), (3, 4))
        self.assertEqual((r.dynamic_energy_j, r.leakage_energy_j, r.modeled_energy_j), (3, 0.75, 3.75))
        self.assertTrue(r.area_fits_placement)
        self.assertEqual(len(r.lines), 7)

    # 同一成本指标选择摘要或叶子得到相同值；不把几何footprint再加到表面积。
    def test_summary_selection(self):
        model, work, table = fixture()
        a = analyze_physical(model, work, table)
        b = analyze_physical(replace(model, static_selection=("die",)), work, table)
        self.assertEqual((a.characterized_area_mm2, a.modeled_energy_j), (b.characterized_area_mm2, b.modeled_energy_j))
        for selected in (("die", "a"), ("a",), ("a", "a")):
            with self.assertRaises(ValueError):
                replace(model, static_selection=selected)
        summary = model.structures[0]
        with self.assertRaisesRegex(ValueError, "PVT summary"):
            replace(model, static_selection=("die",), structures=(replace(summary,
                operating_point=replace(summary.operating_point, voltage_v=0.9)), *model.structures[1:]))

    # 未知时间或缺少单一来源保留已知子集，不能返回部分成本作为总量。
    def test_unknown_coverage(self):
        model, work, table = fixture()
        r = analyze_physical(model, replace(work, observation=None), table)
        self.assertEqual(r.dynamic_energy_j, 3)
        self.assertIsNone(r.leakage_energy_j)
        self.assertIsNone(r.modeled_energy_j)
        partial = replace(table, points=tuple(p for p in table.points if not (p.key.structure_id == "b" and p.key.metric == "dynamic")))
        r = analyze_physical(model, work, partial)
        self.assertEqual(r.known_dynamic_energy_j, 1.5)
        self.assertIsNone(r.dynamic_energy_j)
        r = analyze_physical(model, replace(work, unknown_activity=("omitted refresh",)), table)
        self.assertIsNone(r.modeled_energy_j)
        self.assertEqual(r.known_dynamic_energy_j, 3)

    # PVT越域只使相关条件点未知，不缩放或删除原工作。
    def test_pvt_mismatch(self):
        model, work, table = fixture()
        structure = model.structures[1]
        model = replace(model, structures=(model.structures[0], replace(structure,
            operating_point=replace(structure.operating_point, voltage_v=0.9)), model.structures[2]))
        r = analyze_physical(model, work, table)
        self.assertIsNone(r.characterized_area_mm2)
        self.assertEqual(r.known_area_mm2, 2)
        self.assertIsNone(r.dynamic_energy_j)

    # 下界/宿主时间不是窗口类型，零时长不容纳非零活动。
    def test_observation_semantics(self):
        model, work, table = fixture()
        for basis in ("lower_bound", "host", "measured"):
            with self.assertRaises(ValueError):
                replace(work.observation, basis=basis)
        with self.assertRaises(ValueError):
            analyze_physical(model, replace(work, observation=replace(work.observation, duration_s=0)), table)
        idle = replace(work, activities=(), observation=replace(work.observation, duration_s=0))
        self.assertEqual(analyze_physical(model, idle, table).modeled_energy_j, 0)

    # 活动不能收费到包含真实叶子的摘要节点，重复账本行与非法数值也被拒绝。
    def test_activity_guards(self):
        model, work, table = fixture()
        with self.assertRaises(ValueError):
            replace(work, activities=(work.activities[0], work.activities[0]))
        with self.assertRaises(ValueError):
            analyze_physical(model, replace(work, activities=(replace(work.activities[0], resource_id="die"),)), table)
        with self.assertRaises(TypeError):
            replace(work.activities[0], amount=True)

    # 同层接触合法，内部交叠/越界失败；跨层允许投影重叠但仍分别保存面积。
    def test_geometry_layers(self):
        model, work, table = fixture()
        a = Placement(resource_id="a", rectangle=Rectangle(x_mm=0, y_mm=0, width_mm=1, height_mm=2))
        b = Placement(resource_id="b", rectangle=Rectangle(x_mm=1, y_mm=0, width_mm=1, height_mm=2))
        self.assertTrue(analyze_physical(replace(model, placements=(a, b)), work, table).area_fits_placement)
        overlap = replace(b, rectangle=replace(b.rectangle, x_mm=0))
        with self.assertRaisesRegex(ValueError, "overlap"):
            analyze_physical(replace(model, placements=(a, overlap)), work, table)
        r = analyze_physical(replace(model, placements=(a, replace(overlap, layer=1))), work, table)
        self.assertEqual(r.placed_area_by_layer_mm2, ((0, 2), (1, 2)))
        with self.assertRaisesRegex(ValueError, "outside"):
            analyze_physical(replace(model, placements=(a, replace(b, rectangle=replace(b.rectangle, x_mm=2)))), work, table)

    # 已知面积超出分配边界是必要条件失败；摘要无法映射到叶子几何时不臆造分摊。
    def test_area_fits_and_unknown_projection(self):
        model, work, table = fixture()
        small = replace(model.boundary, width_mm=1, height_mm=1)
        self.assertFalse(analyze_physical(replace(model, boundary=small, placements=(Placement(resource_id="die", rectangle=small),)), work, table).area_fits_placement)
        leaves = (Placement(resource_id="a", rectangle=Rectangle(x_mm=0, y_mm=0, width_mm=1, height_mm=2)),
                  Placement(resource_id="b", rectangle=Rectangle(x_mm=1, y_mm=0, width_mm=1, height_mm=2)))
        self.assertIsNone(analyze_physical(replace(model, static_selection=("die",), placements=leaves), work, table).area_fits_placement)

    # 功率乘时长发生正值下溢时明确拒绝，不能悄悄变成零能量。
    def test_numerical_limits(self):
        model, work, table = fixture()
        tiny = replace(table, points=tuple(replace(p, value=5e-324) if p.key.metric == "leakage" else p for p in table.points))
        with self.assertRaisesRegex(ValueError, "underflow"):
            analyze_physical(model, replace(work, observation=replace(work.observation, duration_s=0.01)), tiny)
        huge = replace(table, points=tuple(replace(p, value=1e308) if p.key.metric == "dynamic" else p for p in table.points))
        with self.assertRaises(ValueError):
            analyze_physical(model, work, huge)

    # 恒功率一阶解与半时间常数手算，以及分段冷却峰值验证。
    def test_thermal_piecewise(self):
        source = fixture()[0].geometry_source
        rc = ThermalRc(resistance_k_per_w=2, capacitance_j_per_k=5, ambient_temperature_k=300)
        trace = ThermalTrace(resource_id="die", model=rc, parameter_source=source, initial_temperature_k=300,
            limit_temperature_k=309, segments=(PowerSegment(duration_s=10 * log(2), power_w=10, source=source),
                                             PowerSegment(duration_s=10 * log(2), power_w=0, source=source)))
        r = analyze_thermal_trace(trace)
        self.assertAlmostEqual(r.boundary_temperatures_k[1], 310)
        self.assertAlmostEqual(r.boundary_temperatures_k[2], 305)
        self.assertAlmostEqual(r.peak_temperature_k, 310)
        self.assertFalse(r.within_limit)
        self.assertAlmostEqual(r.supplied_energy_j, 100 * log(2))
        self.assertEqual(analyze_thermal_trace(replace(trace, segments=())).boundary_temperatures_k, (300,))

    # 50组随机RC/功率/初态用80位Decimal指数作为独立数值参考。
    def test_thermal_decimal_reference(self):
        rng = random.Random(90210)
        with localcontext() as context:
            context.prec = 80
            for _ in range(50):
                r, c, ambient, initial, power, duration = [rng.randint(1, 20) for _ in range(6)]
                ambient, initial = ambient + 280, initial + 280
                expected = Decimal(ambient) + Decimal(power * r) + (Decimal(initial - ambient - power * r)) * (-Decimal(duration) / Decimal(r * c)).exp()
                actual = ThermalRc(resistance_k_per_w=r, capacitance_j_per_k=c, ambient_temperature_k=ambient).temperature_after(
                    initial_temperature_k=initial, power_w=power, duration_s=duration)
                self.assertAlmostEqual(actual, float(expected), places=11)

    # 分段拆分恒功率与整体一次积分一致，零功率冷却不超过初态。
    def test_thermal_semigroup_and_sources(self):
        source = fixture()[0].geometry_source
        rc = ThermalRc(resistance_k_per_w=1, capacitance_j_per_k=2, ambient_temperature_k=300)
        trace = ThermalTrace(resource_id="die", model=rc, parameter_source=source, initial_temperature_k=320,
            limit_temperature_k=320, segments=(PowerSegment(duration_s=1, power_w=0, source=source),) * 5)
        r = analyze_thermal_trace(trace)
        self.assertAlmostEqual(r.boundary_temperatures_k[-1], rc.temperature_after(initial_temperature_k=320, power_w=0, duration_s=5))
        self.assertEqual(r.peak_temperature_k, 320)
        self.assertTrue(r.within_limit)
        with self.assertRaises(ValueError):
            replace(trace.segments[0], duration_s=0)


if __name__ == "__main__":
    unittest.main()
