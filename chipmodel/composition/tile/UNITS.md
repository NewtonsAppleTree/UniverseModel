# tile：共享资源的局部组合边界

Tile/Core/SM/Macro 的组合复用父目录的 [ResourceNode](../UNITS.md)，不为名字另造一份空类。参数是 instance_id、parent_id、model_id 和 ports；前三者无物理单位，端口声明 payload 单位/协议。

容器 model_id=None；其子节点引用 MAC/CIM、SRAM/buffer、控制和网络端口。若选择一个完整 tile 摘要成本，则不能同时选择被它覆盖的内部模型作为同一指标的计量方。

最关心共享 SRAM/端口、局部复用、发射边界与 ADC/累加共享。Tile 容量或吞吐必须来自唯一叶子资源和具体使用路径，不能由 tile 名称增加常数。计算需要的数据传输由显式操作承担。

先定义局部资源和端口，再检查归属/连接。独立台架中 tile 可以直接成为根节点，parent_id=None，不要求先构造 Die/Package。没有独立的 tile latency 公式。

## 已实现的数字局部组合

`DigitalTile`绑定一个MAC、一个SRAM scratch与共同搬运清单；`TileWork`提供MAC数、独立本地访问、DMA请求和预留，`analyze_tile`验证容量/身份并合并bank工作。行为是静态服务下界组合，不是额外tile latency常数。输入与配置冻结，输出无跨调用动态状态。

CH6可选mac_arithmetic和mac_profile_source绑定该MAC资源的显式格式/服务来源；TileWork必须同时给出请求签名和logical_macs，仅声明一侧会失败。mac_analysis解释格式匹配/尾批/额外工作，复用已有MAC服务而不重复求和；两侧均None保留历史无格式账本，见[能力指南](../../docs/compute_capabilities.md)。

本地与DMA共用相同backing/端口；资源包络、逐bank L/II服务和MAC服务分别解释瓶颈。最敏感的是映射复用、地址布局、端口数、L/II和各域时钟。CH5的CIM完整组合也已实现，见下节。独立测试和Linear适配用法见[指南](../../docs/foundation_usage.md)。

## 已实现的CIM局部台架

`CimTile`引用唯一DAC/切片阵列/TIA/ADC/hold/数字资源，`analyze_cim`组合数值链、有限保持和寄存器容量、共享ADC与跨phase II。每行需要持续DAC；phase内阶段barrier，phase间串行，输出资源下界与显式策略分析时间，不宣称通用事件完成时间。

接口顺序：CimNumericParams+CimInput→CimTile归属/服务参数→analyze_cim→数值/动作/样本时间与未知成本。最敏感的是ADC精度、差分位置、ADC lane/时钟、TIA扫描与MUX间隔、保持年龄和数字服务。profile_source必须说明假设/来源。复现与证据见[CH5指南](../../docs/cim_bench.md)。

<!-- model-fields:start -->

### [cim.py](cim.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `CimStage` | `resource_id` | `str` | 1（标识/枚举） | DAC、TIA 或数字处理流水线的唯一物理 ID。 |
| `CimStage` | `pipeline` | `PipelineParams` | lane, cycle | P/L/II [lane, cycle]；item 由阶段的工作单位定义。 |
| `CimStage` | `clock` | `ClockDomain` | Hz | 本阶段时钟 [Hz]，不同域先换成 second。 |
| `CimTile` | `numeric` | `CimNumericParams` | —（结构/对象） | 编码、电导与 DAC/TIA/ADC 数值参数。 |
| `CimTile` | `nodes` | `tuple[ResourceNode, ...]` | —（结构/对象） | 无环归属图；摘要/内部资源互斥。 |
| `CimTile` | `array_resource_ids` | `tuple[str, ...]` | 1（标识/枚举） | slice-major、positive/negative 的独立阵列身份。 |
| `CimTile` | `array_pipeline` | `PipelineParams` | cycle | 每个阵列一次完整读取的 L/II [cycle]；lane_count 必须为1。 |
| `CimTile` | `array_clock` | `ClockDomain` | Hz | 各切片阵列共用的固定时钟 [Hz]。 |
| `CimTile` | `dac` | `CimStage` | —（结构/对象） | 每行一个持续驱动DAC，lane_count≥R；向当前差分对理想广播。 |
| `CimTile` | `tia` | `CimStage` | —（结构/对象） | 每 item 形成一个可保持的标量电压，模拟差分含在此阶段。 |
| `CimTile` | `adc_resource_id` | `str` | 1（标识/枚举） | 所有列/支路/切片共享的 ADC bank ID。 |
| `CimTile` | `adc_clock` | `ClockDomain` | Hz | ADC 与 MUX 控制的时钟 [Hz]。 |
| `CimTile` | `mux_settle_cycles` | `int` | cycle | 每 phase 首批 setup；相邻发起至少此间隔 [cycle]。 |
| `CimTile` | `adc_inflight_per_lane` | `int` | sample/lane | 每 lane 内部独立采样/转换槽 [sample/lane]。 |
| `CimTile` | `hold_resource_id` | `str` | 1（标识/枚举） | TIA后标量sample/hold的唯一资源身份。 |
| `CimTile` | `hold` | `SampleHoldLimits` | —（结构/对象） | 外部样本槽数与从TIA完成到ADC接收的有效期。 |
| `CimTile` | `digital` | `CimStage` | —（结构/对象） | 每 item 完成一次重建、差分或融合requantize/shift-add。 |
| `CimTile` | `code_buffer_slots` | `int` | code | 数字阶段所属的ADC码值暂存容量 [code]；每phase需容纳全部转换码。 |
| `CimTile` | `accumulator_slots` | `int` | integer | 数字阶段所属的持久输出累加槽 [integer]；至少C个。 |
| `CimTile` | `profile_source` | `str` | 1（标识/枚举） | L/II、MUX、保持及数字原语假设的来源/版本。 |
| `CimActionCounts` | `logical_macs` | `int` | MAC | R*C [MAC]，一次稠密逻辑MatVec。 |
| `CimActionCounts` | `physical_arrays` | `int` | array | ceil(Bw/Bcell)*branches [array]。 |
| `CimActionCounts` | `physical_weight_bits` | `int` | bit | 实际阵列cell数*cell_bits [bit]，含尾slice未用位。 |
| `CimActionCounts` | `phases` | `int` | phase | input_bits*weight_slices [phase]。 |
| `CimActionCounts` | `dac_updates` | `int` | DAC update | R*phases [DAC update]，当前差分两支路共享行电压。 |
| `CimActionCounts` | `array_reads` | `int` | array read | physical_arrays*input_bits [array read]。 |
| `CimActionCounts` | `cell_evaluations` | `int` | cell evaluation | R*C*array_reads [cell evaluation]，包括零输入相位。 |
| `CimActionCounts` | `tia_samples` | `int` | sample | C*phases*converted_branches [sample]。 |
| `CimActionCounts` | `adc_conversions` | `int` | conversion | 与实际readout数相等 [conversion]。 |
| `CimActionCounts` | `digital_reconstructions` | `int` | operation | 每ADC码重建一次电压 [operation]。 |
| `CimActionCounts` | `digital_subtractions` | `int` | operation | 仅ADC后差分为C*phases [operation]。 |
| `CimActionCounts` | `shift_adds` | `int` | operation | 每列/phase一次融合requantize和移位累加 [operation]。 |
| `CimActionCounts` | `digital_operations` | `int` | operation | reconstructions+subtractions+shift_adds [operation]。 |
| `CimStageWindow` | `action_id` | `str` | 1（标识/枚举） | 与可组合ActionEstimate一致的身份。 |
| `CimStageWindow` | `resource_id` | `str` | 1（标识/枚举） | 该阶段物理资源。 |
| `CimStageWindow` | `work_items` | `int` | item | 本窗口实际工作量 [item]。 |
| `CimStageWindow` | `first_issue_s` | `float` | s | 满足依赖和资源II后第一次发起 [s]。 |
| `CimStageWindow` | `completion_s` | `float` | s | 本窗口最后一项完成 [s]。 |
| `CimSampleTiming` | `sample_id` | `str` | 1（标识/枚举） | 指向数值链中相同的CimReadout。 |
| `CimSampleTiming` | `adc_lane` | `int` | —（结构/对象） | 确定性按sample_index mod lanes分派的lane索引。 |
| `CimSampleTiming` | `captured_s` | `float` | s | TIA对应item完成并进入外部hold的时刻 [s]。 |
| `CimSampleTiming` | `adc_start_s` | `float` | s | ADC内部采样接收、外部hold释放时刻 [s]。 |
| `CimSampleTiming` | `adc_complete_s` | `float` | s | ADC码值就绪时刻 [s]。 |
| `CimSampleTiming` | `hold_age_s` | `float` | s | adc_start_s-captured_s [s]；与保持上限比较。 |
| `CimAnalysis` | `numeric` | `CimNumericResult` | —（结构/对象） | 完整数值轨迹、程序初态及功能输出。 |
| `CimAnalysis` | `counts` | `CimActionCounts` | —（结构/对象） | 编码与外围的实际动作账本。 |
| `CimAnalysis` | `actions` | `tuple[ActionEstimate, ...]` | —（结构/对象） | 串行phase策略的依赖/工作，可与外部显式动作组合。 |
| `CimAnalysis` | `budgets` | `tuple[ResourceBudget, ...]` | —（结构/对象） | 唯一资源供给包络；hold仅作容量/年龄约束。 |
| `CimAnalysis` | `contributions` | `tuple[ResourceContribution, ...]` | —（结构/对象） | 各资源累计工作与包络贡献。 |
| `CimAnalysis` | `resource_service_bounds` | `tuple[tuple[str, float], ...]` | s | 忽略依赖的各资源全批隔离服务 [s]。 |
| `CimAnalysis` | `resource_lower_bound_s` | `float` | s | max(resource_service_bounds) [s]；不等于端到端运行时间。 |
| `CimAnalysis` | `bottlenecks` | `tuple[str, ...]` | 1（标识/枚举） | 达到最大资源服务下界的物理资源ID。 |
| `CimAnalysis` | `policy_bounds` | `TimeBounds` | —（结构/对象） | 只对所声明串行phase策略的依赖/资源界。 |
| `CimAnalysis` | `serial_policy_time_s` | `float` | s | 串行phase、阶段barrier、II与MUX下的分析完成时间 [s]。 |
| `CimAnalysis` | `windows` | `tuple[CimStageWindow, ...]` | —（结构/对象） | 本地策略的阶段服务窗口。 |
| `CimAnalysis` | `samples` | `tuple[CimSampleTiming, ...]` | —（结构/对象） | 全部样本的身份、时间与保持年龄。 |
| `CimAnalysis` | `peak_hold_samples` | `int` | sample | 全TIA完成后、ADC开始前的样本峰值 [sample]。 |
| `CimAnalysis` | `peak_code_slots` | `int` | code | ADC全部完成后、数字阶段前的码值峰值 [code]。 |
| `CimAnalysis` | `required_adc_inflight_per_lane` | `int` | sample/lane | min(groups,ceil(L/II_effective)) [sample/lane]。 |
| `CimAnalysis` | `energy_j` | `None` | J | 读取/外围/漏电总能耗 [J]，未特征化。 |
| `CimAnalysis` | `programming_time_s` | `None` | s | 权重编程耗时 [s]，已驻留边界不等于免费编程。 |
| `CimAnalysis` | `programming_energy_j` | `None` | J | 权重编程能耗 [J]，未知。 |
| `CimAnalysis` | `unknown_reasons` | `tuple[str, ...]` | 1（标识/枚举） | 来源缺口与未覆盖服务，不能填为零。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `CimStage` | 一个物理阶段的服务参数及资源身份；时序是假设或特征化输入，不由数值公式推导。 |
| `CimTile` | 输入/权重已驻留，bit/slice phases 串行；DAC广播到当前切片的差分两阵列。 |
| `CimActionCounts` | 结构工作量在模拟/数字求差之间分项，逻辑MAC不等于转换或cell动作。 |
| `CimStageWindow` | 指定串行策略下的分析窗口；没有事件回调或器件可见性主张。 |
| `CimSampleTiming` | 每个样本的捕获、接收与转换完成，外部hold在ADC接收时释放。 |
| `CimAnalysis` | 本地台架输出将功能、资源下界与显式策略估算分开；编程和物理成本保持未知。 |
| `analyze_cim(tile: CimTile, inputs: CimInput, *, max_cell_evaluations: int=1000000)` | 建立有限phase台架：DAC→两支阵列并行→TIA全批→ADC全批→数字更新；phase之间全排空。 |

### [digital.py](digital.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `DigitalTile` | `resources` | `TransferResources` | —（结构/对象） | 真实存储、DMA、链路与 owner 清单。 |
| `DigitalTile` | `scratch_id` | `str` | 1（标识/枚举） | 本地操作数/累加器 SRAM 的 backing ID。 |
| `DigitalTile` | `mac_resource_id` | `str` | 1（标识/枚举） | MAC 模型叶子身份；不可与搬运资源重叠。 |
| `DigitalTile` | `mac` | `PipelineParams` | lane, cycle | P lanes、L/II [lane, cycle]，格式能力由上层声明。 |
| `DigitalTile` | `compute_clock` | `ClockDomain` | Hz | MAC 时钟 f_compute [Hz]。 |
| `DigitalTile` | `mac_arithmetic` | `MacArithmetic \| None` | —（结构/对象） | 可选显式MAC能力；None保留历史只声明工作量的边界。 |
| `DigitalTile` | `mac_profile_source` | `str` | 1（标识/枚举） | 所选操作/格式对应的服务参数来源。 |
| `TileWork` | `work_id` | `str` | 1（标识/枚举） | 已映射任务身份。 |
| `TileWork` | `executed_macs` | `int` | MAC | 实际执行含映射额外工作的 MAC 数 [MAC]。 |
| `TileWork` | `local_accesses` | `tuple[SramAccess, ...]` | —（结构/对象） | scratch 上的计算读写；不包含 DMA 源读/目标写。 |
| `TileWork` | `transfers` | `tuple[TransferRequest, ...]` | —（结构/对象） | 独立外部搬运请求。 |
| `TileWork` | `reservations` | `tuple[BufferReservation, ...]` | —（结构/对象） | scratch 中同时预留的地址区域。 |
| `TileWork` | `mac_arithmetic` | `MacArithmetic \| None` | —（结构/对象） | 调用方的操作/格式请求；显式能力不能接受未声明请求。 |
| `TileWork` | `logical_macs` | `int \| None` | MAC | 可选有效逻辑工作 [MAC]；显式格式请求时必须提供。 |
| `TileAnalysis` | `transfer` | `TransferAnalysis` | —（结构/对象） | 源读/通道/链路/目标写明细与未知外存成本。 |
| `TileAnalysis` | `scratch_service` | `SramService` | —（结构/对象） | 本地计算与 DMA 合并后的逐 bank 服务。 |
| `TileAnalysis` | `contributions` | `tuple[ResourceContribution, ...]` | —（结构/对象） | 所有 MAC、bank、DMA、link 的累计包络贡献。 |
| `TileAnalysis` | `bounds` | `TimeBounds` | —（结构/对象） | 已声明依赖与包络下界。 |
| `TileAnalysis` | `service_bounds` | `tuple[tuple[str, float], ...]` | s | MAC/各 bank/搬运的额外必要服务下界 [s]。 |
| `TileAnalysis` | `lower_bound_s` | `float` | s | max(bounds,service_bounds) [s]；无可行调度承诺。 |
| `TileAnalysis` | `bottlenecks` | `tuple[str, ...]` | 1（标识/枚举） | 达到最大必要服务界的约束身份。 |
| `TileAnalysis` | `energy_j` | `None` | J | 未提供物理 profile 的能耗 [J]，明确未知。 |
| `TileAnalysis` | `energy_unknown_reason` | `str` | 1（标识/枚举） | 未知成本来源说明。 |
| `TileAnalysis` | `mac_analysis` | `MacAnalysis \| None` | —（结构/对象） | 可选格式验证/尾批解释；与已计费MAC服务同源，不再次求和。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `DigitalTile` | MAC 与一个 SRAM scratch 共享已有资源清单；buffer 只是该 backing 的地址预留。 |
| `TileWork` | 本地访问必须由映射显式提供；MAC 数和外部搬运量不能推导复用策略。 |
| `TileAnalysis` | 功能验证属于任务参考；此结果只报告服务下界和容量/工作量，不输出虚构能耗。 |
| `analyze_tile(tile: DigitalTile, work: TileWork)` | 只验证静态预留覆盖；不由地址覆盖推断数据已就绪、别名安全或双缓冲重叠。 |

<!-- model-fields:end -->
