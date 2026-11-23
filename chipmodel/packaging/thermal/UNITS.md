# thermal：一阶 lumped RC 的温度响应

ThermalRc 采用能量守恒 `Cth*dT/dt=P−(T−Ta)/Rth`。恒环境、恒功率下，τ=Rth*Cth [s]，稳态 T∞=Ta+P*Rth [K]，瞬态 T(t)=T0+(T∞−T0)*(1−exp(−t/τ))。

最关心 Rth、Cth、环境温度、真实功率时间段和峰值温度。功率必须来自明确覆盖范围的测量/成本结果，不由此模型反推。使用 kelvin，摄氏度输入由边界先加 273.15；温差的 K 与摄氏度增量数值相同。

先提供有来源的 R/C/Ta → 查询稳态，或给定 T0/P/时长查询瞬态。函数无动态状态，可按分段恒功率由调用方传递上段终温。零时长保持初温，零功率向环境冷却。

这是单节点近似；没有 Die 间耦合、空间热点、温敏漏电、散热器多极点或 DVFS 反馈。RC 值和近似范围应由校准确定。

CH9新增[trace.py](trace.py)：ThermalTrace/PowerSegment绑定物理scope和来源，先给定RC/初温/情景阈值，再输入分段外部总功率，返回段末温度、单节点峰值和ΣP_i*T_i供能。每段响应单调，峰值取初态/段末；该外部供能不与成本账本重复相加。不由服务下界构造时长或功率，不将within_limit当作器件认证。验证含50组80位Decimal参考与分段/冷却边界，见[指南](../../docs/physical_evidence.md)。

单节点加热以expm1保留短步长增量；冷却以稳态温度加指数残差计算，避免长时间抵消丢失环境温度。参数归一为binary64；测试含高精度冷热参考和长期收敛，极值不作器件参数。

<!-- model-fields:start -->

### [rc.py](rc.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `ThermalRc` | `resistance_k_per_w` | `float` | K/W | 热阻 Rth [K/W]。 |
| `ThermalRc` | `capacitance_j_per_k` | `float` | J/K | 热容 Cth [J/K]。 |
| `ThermalRc` | `ambient_temperature_k` | `float` | K | 环境温度 Ta [K]。 |
| `ThermalRc` | `time_constant_s` | `float` | s | 只读派生属性；τ=Rth*Cth [s]；K/W*J/K=J/W=s。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `ThermalRc` | 能量平衡 Cth*dT/dt=P−(T−Ta)/Rth；温度统一采用 kelvin。 |
| `ThermalRc.time_constant_s` | τ=Rth*Cth [s]；K/W*J/K=J/W=s。 |
| `ThermalRc.steady_temperature(self, power_w: float)` | 恒功率 P≥0 [W] 时，稳态温度 T∞=Ta+P*Rth [K]。 |
| `ThermalRc.temperature_after(self, *, initial_temperature_k: float, power_w: float, duration_s: float)` | 加热用expm1保留短步长增量；冷却用T∞+(T0−T∞)exp(−t/τ)，避免长时间消去环境温度。 |

### [trace.py](trace.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `PowerSegment` | `duration_s` | `float` | s | 分段时长 [s]，严格为正。 |
| `PowerSegment` | `power_w` | `float` | W | 本段外部给定总功率 [W]，非负。 |
| `PowerSegment` | `source` | `CostSource` | —（结构/对象） | 功率与时间窗口的来源/假设。 |
| `ThermalTrace` | `resource_id` | `str` | 1（标识/枚举） | 热RC所属的独立节点/物理scope。 |
| `ThermalTrace` | `model` | `ThermalRc` | —（结构/对象） | 固定Rth/Cth/Ta，不动态拟合PVT反馈。 |
| `ThermalTrace` | `parameter_source` | `CostSource` | —（结构/对象） | 热参数边界/方法/校准来源。 |
| `ThermalTrace` | `initial_temperature_k` | `float` | K | t=0温度 [K]。 |
| `ThermalTrace` | `limit_temperature_k` | `float` | K | 本情景判定阈值 [K]，不是自动器件认证值。 |
| `ThermalTrace` | `segments` | `tuple[PowerSegment, ...]` | —（结构/对象） | 依次相接的总功率段；允许空轨迹查询初态。 |
| `ThermalResult` | `boundary_temperatures_k` | `tuple[float, ...]` | K | 初态和每段末温度 [K]。 |
| `ThermalResult` | `elapsed_s` | `float` | s | Σduration [s]，显式输入轨迹总时长。 |
| `ThermalResult` | `supplied_energy_j` | `float` | J | ΣP_i*T_i [J]，外部给定的能量输入。 |
| `ThermalResult` | `peak_temperature_k` | `float` | K | max(初态,各段末) [K]，不是空间热点。 |
| `ThermalResult` | `within_limit` | `bool` | 1（布尔） | 本单节点模型的peak≤limit，不证明实际物理可行。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `PowerSegment` | 一个时间段内功率恒定；功率须为scope总输入，已包含的漏电不能再次相加。 |
| `ThermalTrace` | 单节点热边界与功率轨迹；模型只代表明确scope，不推断空间热点或Die耦合。 |
| `ThermalResult` | 每段恒功率一阶响应单调，峰值在初态或段末；外部功率积分不标为芯片预测能耗。 |
| `analyze_thermal_trace(trace: ThermalTrace)` | 顺序应用RC解析解；时间/能量用精确中间量累计，温度递推为binary64。 |

<!-- model-fields:end -->
