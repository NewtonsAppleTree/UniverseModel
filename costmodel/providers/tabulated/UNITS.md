# tabulated：精确条件点与误差报告

[lookup.py](lookup.py)实现CostTable、query_cost和check_reference。CostTable拒绝重复键；query_cost只返回完整结构/PVT/成本项/动作/单位匹配点，无匹配时不返回零或隐式外推值。

输入点值由来源决定，面积mm²、功率W、能量J/动作的换算在提取边界完成，查询不作换算。check_reference报告绝对误差及abs(pred−ref)/abs(ref)，参考为零时相对误差未定义。holdout要求不同的非假设参考工件；该检查仅阻止明显复用，不能证明实验方法独立或器件代表性。

实际[两标准单元表](../../../config/costs/nangate45_typical.json)来自固定版本LEF/Liberty，提取工具逐文件核对SHA256、标称PVT/功率单位并以Decimal核对LEF尺寸乘积与Liberty面积。它只证明来源点再现，无独立器件校准误差/留出实测。灵敏度与缺点实验见[CH9指南](../../../chipmodel/docs/physical_evidence.md)。

<!-- model-fields:start -->

### [lookup.py](lookup.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `CostTable` | `table_id` | `str` | 1（标识/枚举） | 特征化表及版本身份。 |
| `CostTable` | `points` | `tuple[CostPoint, ...]` | —（结构/对象） | 有来源的条件点；可以为空以明确全部未知。 |
| `ReferenceError` | `role` | `str` | 1（标识/枚举） | source_reproduction或holdout；本身不证明参考独立性。 |
| `ReferenceError` | `absolute_error` | `float` | —（结构/对象） | \|预测−参考\|，单位与成本项相同。 |
| `ReferenceError` | `relative_error` | `float \| None` | —（结构/对象） | \|预测−参考\|/\|参考\|；参考为0时未定义。 |
| `ReferenceError` | `reference_source` | `CostSource` | —（结构/对象） | 参考工件/方法，保留来源类别与限制。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `CostTable` | 表的唯一键绑定结构/PVT/动作，顺序不决定模型优先级。 |
| `query_cost(table: CostTable, key: CostKey)` | 精确查表，不插值/外推；源类别与误差未知状态随匹配点返回。 |
| `ReferenceError` | 差值仅说明所给参考上的误差；来源点再现不是器件有效性验证。 |
| `check_reference(estimate: CostEstimate, reference_value: float, reference_source: CostSource, *, role: Literal['source_reproduction', 'holdout'])` | 留出比较必须来自不同工件且非假设参考；仍由研究者证明方法独立和代表性。 |

<!-- model-fields:end -->
