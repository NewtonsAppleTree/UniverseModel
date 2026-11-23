"""条件成本接口的独立范围、来源、量纲与误差验证。"""

from dataclasses import replace
from pathlib import Path
import unittest

from configuration.resolution.dataclass_config import load_config
from costmodel.interfaces.costs import CostKey, CostPoint, CostSource, OperatingPoint
from costmodel.providers.tabulated.lookup import CostTable, check_reference, query_cost

ROOT = Path(__file__).resolve().parents[2]  # 固定来源配置入口。


# 真实来源点与接口约束；没有测试使用结果宣称器件校准成立。
class CostTests(unittest.TestCase):
    # 原始LEF尺寸独立换算mm²，漏电nW独立换算W。
    def test_pinned_source_points(self):
        table = load_config(CostTable, ROOT / "config/costs/nangate45_typical.json")
        expected = ((0.38 * 1.4 / 1e6, 14.353185 / 1e9), (0.57 * 1.4 / 1e6, 17.393360 / 1e9))
        for i, values in enumerate(expected):
            for j, value in enumerate(values):
                point = table.points[2 * i + j]
                result = query_cost(table, point.key)
                self.assertAlmostEqual(result.value / value, 1)
                self.assertIsNone(point.relative_uncertainty)
                self.assertEqual(point.source.kind, "characterization")
                self.assertEqual(len(point.source.artifact_sha256), 64)

    # 不同工艺/PVT/结构或动作量纲均不自动匹配；缺失动态成本不填零。
    def test_unknown_outside_exact_domain(self):
        table = load_config(CostTable, ROOT / "config/costs/nangate45_typical.json")
        key = table.points[0].key
        keys = (replace(key, structure_id="MAC"), replace(key, operating_point=replace(key.operating_point, voltage_v=1.0)),
                replace(key, operating_point=replace(key.operating_point, temperature_k=300)),
                replace(key, metric="dynamic", action="toggle", work_unit="transition"))
        for request in keys:
            result = query_cost(table, request)
            self.assertIsNone(result.value)
            self.assertIn("No exact", result.unknown_reason)

    # 重复键没有隐式优先级，已知零保持已知。
    def test_unique_points_and_known_zero(self):
        table = load_config(CostTable, ROOT / "config/costs/nangate45_typical.json")
        point = replace(table.points[0], value=0)
        self.assertEqual(query_cost(replace(table, points=(point,)), point.key).value, 0)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            replace(table, points=(point, point))
        self.assertIsNone(query_cost(replace(table, points=()), point.key).value)

    # 源哈希/类别/物理量的直接调用校验与配置解析一致。
    def test_source_and_numeric_guards(self):
        table = load_config(CostTable, ROOT / "config/costs/nangate45_typical.json")
        point = table.points[0]
        for value in (True, float("nan"), float("inf"), -1, 10**400):
            with self.assertRaises((TypeError, ValueError)):
                replace(point, value=value)
        for changes in ({"artifact_sha256": None}, {"artifact_sha256": "a"}, {"kind": "simulated"}, {"limitations": ()}):
            with self.assertRaises(ValueError):
                replace(point.source, **changes)
        with self.assertRaises(ValueError):
            replace(point.key.operating_point, temperature_k=0)

    # 静态实体计量不能使用动作单位，动态键必须声明其实际粒度。
    def test_action_units(self):
        table = load_config(CostTable, ROOT / "config/costs/nangate45_typical.json")
        key = table.points[0].key
        for request in ({"work_unit": "byte"}, {"metric": "dynamic"}):
            with self.assertRaises(ValueError):
                replace(key, **request)
        dynamic = replace(table.points[0], key=replace(key, metric="dynamic", action="read", work_unit="word"))
        result = query_cost(replace(table, points=(dynamic,)), replace(dynamic.key, work_unit="byte"))
        self.assertIsNone(result.value)

    # 来源再现、非零误差与零参考的相对误差未定义分开报告。
    def test_reference_errors(self):
        table = load_config(CostTable, ROOT / "config/costs/nangate45_typical.json")
        point = table.points[0]
        estimate = query_cost(table, point.key)
        self.assertEqual(check_reference(estimate, point.value, point.source, role="source_reproduction").absolute_error, 0)
        self.assertAlmostEqual(check_reference(estimate, point.value * 2, point.source, role="source_reproduction").relative_error, 0.5)
        self.assertIsNone(check_reference(estimate, 0, point.source, role="source_reproduction").relative_error)

    # 留出需要不同工件且不能使用假设参考；该检查不冒充物理独立性证明。
    def test_holdout_identity_guards(self):
        table = load_config(CostTable, ROOT / "config/costs/nangate45_typical.json")
        point = table.points[0]
        estimate = query_cost(table, point.key)
        for source in (point.source, replace(point.source, source_id="renamed"),
                       replace(point.source, source_id="synthetic", kind="assumption", artifact_sha256=None)):
            with self.assertRaisesRegex(ValueError, "holdout"):
                check_reference(estimate, point.value, source, role="holdout")
        independent = replace(point.source, source_id="test-only-independent", artifact_sha256="1" * 64)
        self.assertEqual(check_reference(estimate, point.value, independent, role="holdout").absolute_error, 0)


if __name__ == "__main__":
    unittest.main()
