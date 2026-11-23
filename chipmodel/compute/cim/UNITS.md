# cim：驻留权重与外围成本的共同边界

第一性问题是减少权重移动的收益，能否覆盖编码、驱动、采样、转换、累加和编程的代价。阵列 cell 数不等同于有效吞吐；同一宏不能同时收取摘要和全部外围费用。

| 子模块 | Unit | 量纲与最关键的关系 |
| --- | --- | --- |
| [arrays](arrays/UNITS.md) | ConductanceArray、显式跨阻 | G [S]×V [V]→I [A]，再由 TIA 转回 V |
| [encoding](encoding/UNITS.md) | 位串行/差分动作量、位权累加 | logical MAC、cell-evaluation、conversion 与物理 bit 分开 |
| [periphery](periphery/UNITS.md) | ADC、DAC、SampleHoldLimits | 编码范围、LSB、L/II、lane 数、保持有效期 |

可独立运行任一段。完整数值链为 code→DAC→array→显式 TIA→ADC→累加。模拟差分发生在 ADC 前还是后，会改变转换数和误差；两种结果不能仅靠 signed 标志互换。

现有等效列和手算夹具采用无量纲整数模型，本电导/电压参考有不同数值边界。当前未覆盖编程寿命、INL/DNL、噪声、线阻、MUX 负载、共享外围背压与器件能量。最关心实际任务精度、转换次数、样本保持和输出容量；按结论敏感性再扩展。

## CH5完整局部数值链

[matvec.py](matvec.py)新增CimNumericParams、CimInput及encode_conductances/evaluate_cim。完整R×C矩阵的幅度切片按G=Gmin+digit*ΔG编程；每个无符号输入bit经1-bit DAC→列电流→显式TIA→ADC中点重建→ties-to-even部分和→最终移位累加。模拟/数字差分分开计量；非零Gmin、尾slice、负跨阻、限幅/输出溢出均有独立验证。

工作量、权重/编码/输入身份和逐样本电压/码值进入只读结果。位宽、量程、ΔG、TIA增益/偏置是关键敏感参数。先定义数值配置和矩阵→encode_conductances或evaluate_cim→按需接[局部CimTile](../../composition/tile/UNITS.md)。输入/权重已驻留，编程与物理能耗未知。研究对照、精度与时序边界见[CH5指南](../../docs/cim_bench.md)。

<!-- model-fields:start -->

### [matvec.py](matvec.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `CimNumericParams` | `encoding` | `BitSerialParams` | —（结构/对象） | 无符号输入相位、权重幅度切片及差分位置。 |
| `CimNumericParams` | `array` | `ConductanceArrayParams` | —（结构/对象） | 每份切片阵列的实际 R×C 与电气范围。 |
| `CimNumericParams` | `conductance_step_s` | `float` | S/digit | 权重 digit 每级增加的电导 ΔG [S/digit]。 |
| `CimNumericParams` | `dac` | `VoltageDac` | V | 必须为 1-bit、Vmin=0；每相位输出 0 或 Vread [V]。 |
| `CimNumericParams` | `tia_gain_ohm` | `float` | Ω | 带符号非零跨阻 Rtia [Ω]。 |
| `CimNumericParams` | `tia_offset_v` | `float` | V | TIA 输出偏置 [V]；解码时显式移除。 |
| `CimNumericParams` | `adc` | `AdcParams` | —（结构/对象） | Offset-binary 量化；可更换量程/精度，并观察量化损失。 |
| `CimNumericParams` | `output_bits` | `int` | bit | 最终有符号整数宽度 [bit]；1..64，中间累加为无限精度。 |
| `CimNumericParams` | `overflow` | `Literal['error', 'saturate', 'wrap']` | —（结构/对象） | 只在最终输出应用的溢出策略。 |
| `CimInput` | `work_id` | `str` | 1（标识/枚举） | 调用者的数据/工作身份；样本 ID 在此命名空间内产生。 |
| `CimInput` | `input_codes` | `tuple[int, ...]` | integer | R 个无符号逻辑输入 [integer]。 |
| `CimInput` | `weights` | `tuple[tuple[int, ...], ...]` | R,C | 行优先整数 W[R,C]；权重预先驻留的边界数据。 |
| `CimReadout` | `sample_id` | `str` | 1（标识/枚举） | work/bit/slice/branch/column 唯一样本 ID。 |
| `CimReadout` | `column` | `int` | column | 输出列索引 [column]。 |
| `CimReadout` | `branch` | `str` | 1（标识/枚举） | difference、positive、negative 或 unsigned。 |
| `CimReadout` | `current_a` | `float` | A | 本次 TIA 输入的列电流或差分电流 [A]。 |
| `CimReadout` | `voltage_v` | `float` | V | TIA 输出、ADC 输入 [V]。 |
| `CimReadout` | `adc_sample` | `AdcSample` | —（结构/对象） | 码值及严格越量程标志。 |
| `CimPhase` | `phase_id` | `str` | 1（标识/枚举） | 此 bit/slice 组合的身份。 |
| `CimPhase` | `input_bit` | `int` | bit | 输入 bit 索引 [bit]。 |
| `CimPhase` | `weight_slice` | `int` | slice | 权重幅度 slice 索引 [slice]。 |
| `CimPhase` | `row_codes` | `tuple[int, ...]` | code | 本次每行的 DAC 码 0/1 [code]。 |
| `CimPhase` | `row_voltages_v` | `tuple[float, ...]` | V | DAC 实际行驱动 [V]。 |
| `CimPhase` | `readouts` | `tuple[CimReadout, ...]` | —（结构/对象） | 列优先，数字差分时同列 positive/negative 相邻。 |
| `CimPhase` | `partials` | `tuple[int, ...]` | —（结构/对象） | ADC 中点重建、仿射恢复后 ties-to-even 舍入的整数部分和。 |
| `CimPhase` | `shift` | `int` | bit | input_bit+weight_slice*cell_bits [bit]。 |
| `CimNumericResult` | `input_identity` | `str` | 1（标识/枚举） | 完整 CimInput 的内容哈希。 |
| `CimNumericResult` | `weight_identity` | `str` | 1（标识/枚举） | 原始整数权重内容哈希。 |
| `CimNumericResult` | `encoding_identity` | `str` | 1（标识/枚举） | 编码/阵列/ΔG 与传递函数配置身份。 |
| `CimNumericResult` | `programmed_arrays` | `tuple[ConductanceArray, ...]` | —（结构/对象） | slice-major、positive/negative 顺序的已编程初态。 |
| `CimNumericResult` | `work` | `BitSerialWork` | —（结构/对象） | 逻辑 MAC、实际 cell/ADC 动作与物理权重位。 |
| `CimNumericResult` | `phases` | `tuple[CimPhase, ...]` | —（结构/对象） | bit-major/slice-major 的显式工作序列。 |
| `CimNumericResult` | `unbounded_output` | `tuple[int, ...]` | —（结构/对象） | 量化后部分和的无限精度移位累加结果。 |
| `CimNumericResult` | `output` | `tuple[int, ...]` | —（结构/对象） | 应用最终输出溢出策略后的结果。 |
| `CimNumericResult` | `output_overflowed` | `tuple[bool, ...]` | —（结构/对象） | 量化后无限精度结果是否超出输出宽度。 |
| `CimNumericResult` | `clipped_samples` | `int` | sample | ADC 严格越量程的样本数 [sample]。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `CimNumericParams` | 一份明确的整数→电导→电压→码值→整数映射；不将 ADC 位数视作任务精度。 |
| `CimInput` | 稠密完整阵列输入；正负权重用幅度与独立差分支路表示，未支持有符号输入编码。 |
| `CimReadout` | 一个输出列/差分支路的真实转换输入与量化结果，保持其数据身份贯穿时序分析。 |
| `CimPhase` | 一次输入 bit 与权重 slice 的完整局部数值路径；所有列完整执行，不跳过零。 |
| `CimNumericResult` | 功能输出保留真实程序矩阵、中间值与编码来源；没有隐含目标时间。 |
| `encode_conductances(p: CimNumericParams, weights: tuple[tuple[int, ...], ...])` | G=Gmin+digit*ΔG；尾 slice 的未使用高位保持零，正负幅度存入不同阵列。 |
| `evaluate_cim(p: CimNumericParams, inputs: CimInput, *, adc_frequency_hz: float=1.0, max_cell_evaluations: int=1000000)` | 完整数值链；独立 ADC clock 仅供复用其构造接口，数值结果不依赖频率。 |

<!-- model-fields:end -->