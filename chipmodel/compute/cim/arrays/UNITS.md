# arrays：理想电导阵列与物理量转换

ConductanceArray 拥有冻结的 G[R,C] 初态，接收 R 个电压，返回 C 个列电流。公式 `I_j=Σ_i G_ij*V_i` 仅适用于理想线性导电与零线阻假设；它不是完整 SPICE 电路。

最关心 R/C、G 范围、驱动电压、输出电流范围和 ADC 前端增益。`transimpedance` 显式执行 `Vout=offset+I*gain`，gain [Ω] 可为负以表达反相极性；实际输出摆幅限制/带宽/settling 未实现，不能隐式裁剪电流。

构造参数 → 校验/冻结矩阵 → evaluate → 按需要做跨阻适配。矩阵从外部 list 深拷贝成 tuple，原输入修改不改变阵列。G 为非负；负权重需差分编码，不能直接塞负电导。当前无 program/reset 动态状态。

<!-- model-fields:start -->

### [conductance.py](conductance.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `ConductanceArrayParams` | `rows` | `int` | row | 驱动行数 R [row]。 |
| `ConductanceArrayParams` | `columns` | `int` | column | 读出列数 C [column]。 |
| `ConductanceArrayParams` | `conductance_min_s` | `float` | S | 允许电导下限 Gmin [S]；可为理想零电导。 |
| `ConductanceArrayParams` | `conductance_max_s` | `float` | S | 电导上限 Gmax [S]。 |
| `ConductanceArrayParams` | `max_abs_input_v` | `float` | V | 输入绝对电压上限 \|V\| [V]。 |
| `ConductanceArray` | `params` | `ConductanceArrayParams` | —（结构/对象） | 阵列结构与电气范围。 |
| `ConductanceArray` | `conductances_s` | `tuple[tuple[float, ...], ...]` | S | G[R,C] [S]；行优先。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `ConductanceArrayParams` | 阵列几何与电气适用域；cell 数不直接给出吞吐或有效权重容量。 |
| `ConductanceArray` | 一份固定编程后的电导矩阵；深拷贝到 tuple，避免外部修改影响功能结果。 |
| `ConductanceArray.evaluate(self, voltages_v: tuple[float, ...])` | 给定 R 个行电压 [V]，计算 C 个列电流 I=GᵀV [A]；不隐式把 A 转成 V。 |
| `transimpedance(currents_a: tuple[float, ...], *, gain_ohm: float, offset_v: float)` | 显式模拟前端增益：Vout=Voffset+I*Rtia；Rtia [Ω] 为带符号跨阻，极性由调用方决定。 |

<!-- model-fields:end -->
