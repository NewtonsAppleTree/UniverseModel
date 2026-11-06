# periphery：转换器与采样边界

本模块包含 IdealAdc、VoltageDac、SampleHoldLimits。详细 ADC 数值与时序说明见 [adc_model.md](../../../docs/adc_model.md)。ADC 保留原有接口，DAC 的数值函数与时序参数分离，可用公共 PipelineParams 分析已给定的 L/II。

ADC bin 宽度为跨度/2^N；本 DAC 是端点对齐映射，步长为跨度/(2^N−1)。两者不能宣称互为无误差逆变换。最关心 nominal bits 与 ENOB 的区别、输入/输出范围、极性、ADC 转换数和采样有效窗。

SampleHoldLimits 只检查同时保留样本数与样本年龄；单位分别是 sample、second，不等于 ADC lane 数或请求数。等于期限仍有效。保持时刻、源释放、输出背压和模拟误差未实现。

先确定量纲/编码 → 显式参数 → 校验与派生 → 单个或批量转换/静态有效性检查。数值结果不代表目标硬件已完成事件。所有物理速度、功率与误差需要外部特征化，不能从位数猜测。

<!-- model-fields:start -->

### [adc.py](adc.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `AdcParams` | `resolution_bits` | `int` | bit | Nominal resolution N [bit]；不等同于 ENOB。 |
| `AdcParams` | `lane_count` | `int` | lane | 并行转换通道 P [lane]；不表示 MUX 输入数。 |
| `AdcParams` | `conversion_cycles` | `int` | cycle | Conversion latency L [cycle]；从发起到码值就绪。 |
| `AdcParams` | `initiation_interval_cycles` | `int` | cycle | 每 lane 最小发起间隔 II [cycle]；独立于 L。 |
| `AdcParams` | `input_min_v` | `float` | V | 输入下限 Vmin [V]；输出采用 offset-binary 编码。 |
| `AdcParams` | `input_max_v` | `float` | V | 输入上限 Vmax [V]；要求 Vmax > Vmin。 |
| `AdcDerived` | `code_count` | `int` | code | 码阶数 K = 2**N [code]；合法码值为 0..K-1。 |
| `AdcDerived` | `quantization_step_v` | `float` | V/code | LSB ΔV = (Vmax - Vmin) / K [V/code]。 |
| `AdcDerived` | `conversion_time_s` | `float` | s | 单样本服务延迟 L / f [s]；不含排队与采样建立。 |
| `AdcDerived` | `initiation_interval_s` | `float` | s | 每 lane 发起间隔 II / f [s]。 |
| `AdcDerived` | `ideal_conversions_per_s` | `float` | conversion/s | Bank 稳态上限 P * f / II [conversion/s]。 |
| `AdcDerived` | `minimum_inflight_per_lane` | `int` | slot/lane | 维持 II 所需在途槽下界 ceil(L / II) [slot/lane]。 |
| `AdcSample` | `code` | `int` | code | Offset-binary 码值 [code]；电压为负也不改用补码。 |
| `AdcSample` | `clipped_low` | `bool` | 1（布尔） | 输入严格小于 Vmin；钳位到 code=0。 |
| `AdcSample` | `clipped_high` | `bool` | 1（布尔） | 输入严格大于 Vmax；钳位到 code=K-1。 |
| `AdcBatchEstimate` | `sample_count` | `int` | sample | 待转换样本数 S [sample]；一个样本对应一次转换。 |
| `AdcBatchEstimate` | `group_count` | `int` | group | 发起批次数 G = ceil(S / P) [group]；末批可以不满。 |
| `AdcBatchEstimate` | `completion_cycles` | `int` | cycle | 末次码值就绪 C = L + (G-1)*II [cycle]；S=0 时为 0。 |
| `AdcBatchEstimate` | `completion_time_s` | `float` | s | 批次完成时间 C / f [s]；不是宿主 Python 耗时。 |
| `IdealAdc` | `model_id` | `ClassVar[str]` | 1（标识/枚举） | 量化与估算语义版本。 |
| `IdealAdc` | `params` | `AdcParams` | —（结构/对象） | 本实例的冻结配置；不接受单独覆盖派生量。 |
| `IdealAdc` | `frequency_hz` | `float` | Hz | 固定转换时钟 f [Hz]；本版本不支持运行中 DVFS。 |
| `IdealAdc` | `derived` | `AdcDerived` | —（结构/对象） | 构造时解析的只读派生量。 |
| `IdealAdc` | `_minimum` | `Fraction` | V | Vmin 的精确 binary64 数值 [V]。 |
| `IdealAdc` | `_step` | `Fraction` | V/code | 精确码阶 [V/code]；避免边界运算误入邻码。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `AdcParams` | ADC 的设计输入：N、P、L、II 与输入电压区间共同决定量化和服务能力。 |
| `AdcDerived` | 只读派生规格：K=2^N、ΔV=(Vmax−Vmin)/K、T=L/f、rate=P*f/II。 |
| `derive_adc(p: AdcParams, *, frequency_hz: float)` | 按固定转换时钟推导码阶和时序；在途槽需求下界为 ceil(L/II)。 |
| `AdcSample` | 单样本数值结果：输出码与严格越限标志分开，端点命中不算越限。 |
| `AdcBatchEstimate` | S 个样本按 P lanes 分组：G=ceil(S/P)，末次完成 C=L+(G−1)II。 |
| `IdealAdc` | 理想 ADC 把电压量化与无争用分析放在同一入口，不持有事件或缓冲状态。 |
| `IdealAdc.convert(self, voltage_v: float)` | q=clamp(floor((V−Vmin)/ΔV),0,K−1)；精确比值避免邻近阈值的浮点误判。 |
| `IdealAdc.convert_many(self, voltages_v: Iterable[float])` | 对有限电压序列逐样本量化，返回同序不可变结果；不表示硬件同时发起。 |
| `IdealAdc.estimate_batch(self, sample_count: int)` | 估算空闲 bank 上 S 个已就绪样本的尾批完成时间；S=0 时为零。 |

### [dac.py](dac.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `VoltageDac` | `resolution_bits` | `int` | bit | 无符号 DAC 编码宽度 N [bit]；首版支持 1..53。 |
| `VoltageDac` | `output_min_v` | `float` | V | q=0 时的输出电压 Vmin [V]。 |
| `VoltageDac` | `output_max_v` | `float` | V | q=2^N−1 时的输出电压 Vmax [V]。 |
| `SampleHoldLimits` | `slot_count` | `int` | sample | 同时可保留的标量样本数 [sample]。 |
| `SampleHoldLimits` | `valid_duration_s` | `float` | s | 从采样完成起允许的保持时长 [s]。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `VoltageDac` | 数字码 q∈[0,2^N−1] 映射至 Vmin..Vmax，LSB=(Vmax−Vmin)/(2^N−1)。 |
| `VoltageDac.convert(self, code: int)` | V=Vmin+q*(Vmax−Vmin)/(2^N−1) [V]；越界码拒绝，不隐式截断。 |
| `SampleHoldLimits` | Sample/hold 的静态有效性约束，不维护实际槽所有权或采样事件。 |
| `SampleHoldLimits.validate(self, *, sample_count: int, age_s: float)` | 要求样本数≤槽数、使用时样本年龄≤保持期限；等于期限仍有效。 |

<!-- model-fields:end -->
