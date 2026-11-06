# thermal：一阶 lumped RC 的温度响应

ThermalRc 采用能量守恒 `Cth*dT/dt=P−(T−Ta)/Rth`。恒环境、恒功率下，τ=Rth*Cth [s]，稳态 T∞=Ta+P*Rth [K]，瞬态 T(t)=T0+(T∞−T0)*(1−exp(−t/τ))。

最关心 Rth、Cth、环境温度、真实功率时间段和峰值温度。功率必须来自明确覆盖范围的测量/成本结果，不由此模型反推。使用 kelvin，摄氏度输入由边界先加 273.15；温差的 K 与摄氏度增量数值相同。

先提供有来源的 R/C/Ta → 查询稳态，或给定 T0/P/时长查询瞬态。函数无动态状态，可按分段恒功率由调用方传递上段终温。零时长保持初温，零功率向环境冷却。

这是单节点近似；没有 Die 间耦合、空间热点、温敏漏电、散热器多极点或 DVFS 反馈。RC 值和近似范围应由校准确定。

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
| `ThermalRc.temperature_after(self, *, initial_temperature_k: float, power_w: float, duration_s: float)` | T(t)=T0+(T∞−T0)*(1−exp(−t/τ))；expm1 避免短时间步长的消减误差。 |

<!-- model-fields:end -->
