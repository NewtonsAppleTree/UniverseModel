# interfaces：结构、PVT、来源与成本值

[costs.py](costs.py)定义冻结的CostSource、OperatingPoint、CostKey、CostPoint和CostEstimate。它们是查询边界，不承担硬件调度或器件计算。

结构/PVT/metric/action/work_unit共同决定查询身份；area与leakage的action/unit固定instance，dynamic必须声明动作与计数粒度。非假设来源必须带原始工件SHA256、版本、提取方法及限制；来源类别不自动升级为实测或校准。

CostPoint.value单位由metric定义为mm²、W或J/动作单位；值非负有限。relative_uncertainty是相对情景误差幅度，None为未知，不称置信区间。dynamic契约排除另计背景功率，profile提供者须确认覆盖口径。CostEstimate的点和请求精确一致；无点时value=None并保留原因。

先验证来源与参数，再构造冻结查询。结构、PVT、动作与单位的任何变化都需要重新匹配；不根据名称猜测兼容性。验证包括真实来源单位换算、未知传播、非有限数/重复键和伪留出反例，见[测试](../../tests/costmodel/test_costs.py)。

<!-- model-fields:start -->

### [costs.py](costs.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `CostSource` | `source_id` | `str` | 1（标识/枚举） | 来源身份，用于追溯与比较。 |
| `CostSource` | `kind` | `Literal['characterization', 'measurement', 'analytical', 'assumption']` | —（结构/对象） | 证据类别；assumption仅为显式假设。 |
| `CostSource` | `reference` | `str` | 1（标识/枚举） | 文献、URL或本地实验方法引用，不在查询时访问网络。 |
| `CostSource` | `revision` | `str` | 1（标识/枚举） | 来源版本/工具版本/实验版本。 |
| `CostSource` | `artifact_sha256` | `str \| None` | 1（标识/枚举） | 原始来源工件SHA256；纯假设可为None。 |
| `CostSource` | `extraction` | `str` | 1（标识/枚举） | 字段提取、单位换算或观测方法。 |
| `CostSource` | `limitations` | `tuple[str, ...]` | 1（标识/枚举） | 未覆盖成本、误差/校准缺口与适用边界。 |
| `OperatingPoint` | `process` | `str` | 1（标识/枚举） | 工艺/库/角身份，不仅是nm标签。 |
| `OperatingPoint` | `voltage_v` | `float` | V | VDD [V]，严格为正。 |
| `OperatingPoint` | `temperature_k` | `float` | K | 条件温度 [K]，严格为正。 |
| `CostKey` | `structure_id` | `str` | 1（标识/枚举） | 完整结构版本或参数哈希，不能只用MAC/SRAM通用名称复用器件值。 |
| `CostKey` | `operating_point` | `OperatingPoint` | —（结构/对象） | 要求精确匹配的PVT条件。 |
| `CostKey` | `metric` | `Literal['area', 'leakage', 'dynamic']` | —（结构/对象） | 输出分别为mm²、W、J/动作单位。 |
| `CostKey` | `action` | `str` | 1（标识/枚举） | dynamic必须说明动作语义；area/leakage固定instance。 |
| `CostKey` | `work_unit` | `str` | 1（标识/枚举） | 计数粒度，如MAC、word、bit；不得把byte等同word。 |
| `CostPoint` | `key` | `CostKey` | —（结构/对象） | 结构/PVT/成本项/动作粒度键。 |
| `CostPoint` | `value` | `float` | J/动作单位 | area [mm²]、leakage [W]或dynamic [J/动作单位]。 |
| `CostPoint` | `source` | `CostSource` | —（结构/对象） | 字段来源与限制。 |
| `CostPoint` | `coverage` | `str` | 1（标识/枚举） | 所含实体/动作边界；动态项须排除背景功率。 |
| `CostPoint` | `relative_uncertainty` | `float \| None` | —（结构/对象） | 相对情景误差幅度；None为未知，不是0或置信区间。 |
| `CostEstimate` | `key` | `CostKey` | —（结构/对象） | 原始查询键。 |
| `CostEstimate` | `point` | `CostPoint \| None` | —（结构/对象） | 精确匹配点，未知时None。 |
| `CostEstimate` | `unknown_reason` | `str \| None` | 1（标识/枚举） | 无来源或越域原因；已知时None。 |
| `CostEstimate` | `value` | `float \| None` | —（结构/对象） | 只读派生属性；未知点返回None而非零；值的单位由key.metric规定。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `text_id(name: str, value: str)` | 非空身份描述结构、来源与适用边界，不解释可执行表达式。 |
| `nonnegative(name: str, value: float)` | 校验非负有限物理量；排除bool及溢出，不把未知变成零。 |
| `frozen_items(name: str, values: object, kind: type)` | 只接受有限序列并冻结成员，防止把字符串或惰性迭代器当模型列表。 |
| `CostSource` | 一个来源绑定具体工件/版本；记录误差缺口，不把公开表当实测。 |
| `OperatingPoint` | 精确工作点：process包含库/工艺角，温度使用绝对温度；没有全域缩放规律。 |
| `CostKey` | 查询键包含完整结构身份与动作粒度；area/leakage按instance，dynamic按明确动作单位。 |
| `CostPoint` | 表中一个已知条件点；dynamic仅含动作能量，排除另计的背景/漏电。 |
| `CostEstimate` | 缺点/越域的查询结果明确保留None；不偷偷选择最近器件或PVT。 |
| `CostEstimate.value` | 未知点返回None而非零；值的单位由key.metric规定。 |

<!-- model-fields:end -->
