# 可独立调用的组件接口提案

本文定义局部仿真需要的对象、调用面、适配器与指标，服务于[可组合仿真规划](../architecture/composable_simulation.md)。字段和签名是设计草案，尚未实现；接口冻结与原计划字段迁移按规划第 10 节执行。生命周期继续遵守[现行规范](resource_lifecycle.md)。

首批验证对象为 CIM array、DAC、ADC、采样保持、数字累加和缓冲。接口应允许其他计算、存储、控制及互连组件使用相同管理语义，再按能力增加专用请求。

这些协议怎样组织成 Python/C++ 模型类、参数和私有状态，见[Unit 类与参数设计](../../chipmodel/docs/unit_model_design.md)。该设计给出带单位的纯推导示例和首批组件字段，不改变本文的公共请求生命周期。

## 1 通用接口的边界

统一身份、单位、生命周期、背压和观测；操作的有效载荷按协议区分。不要用一个任意字典承载所有设备，也不要让 ADC、DRAM 和 NoC 实现没有意义的相同 compute 函数。

每种接口至少回答：输入来源、必需字段、合法前置状态、单位、数据所有权、何时接受、何时完成、错误行为、可选输出，以及版本兼容规则。端口方向相反、字段名相同，不足以证明两个组件能连接。

## 2 输入输出对象

| 对象 | 必要内容 | 维护归属 |
| --- | --- | --- |
| ComponentSpec | instance_id、type_id、implementation/version、参数、时钟/电源域、端口、能力与覆盖范围 | contracts/hardware；参数定义由 configuration 管理 |
| PortSpec | port_id、方向、protocol/version、payload 类型、地址/可见域、顺序、流控和容量单位 | contracts/hardware |
| ConnectionSpec | 端点引用、适配器、路由约束、共享资源标识 | contracts/hardware |
| BenchSpec | 作用域、组件/连接、外部边界、初态、驱动器、停止条件、观测与来源 | contracts 中的公共实验描述；evaluation 或调用脚本消费 |
| StimulusSpec | 请求列表/生成器/轨迹/计划引用、到达规则、随机子流、背压重试策略 | contracts/workload 与 plan；驱动器在 simulator/adapters |
| InitialStateSpec | 数据加载、权重编码、缓存/器件状态、状态版本、冷/热启动语义 | 公共身份在 contracts；状态内容由模型解释 |
| Request | 身份、操作类型、目标端口、输入/输出引用、依赖、参数与完成条件 | contracts/events |
| Acceptance | accepted/backpressured/rejected、原因、许可/credit 或重试通知 | contracts/events |
| Completion | request_id、终态、数据效果、源释放、可见性、资源时间与错误 | contracts/events |
| ObservationSpec | 指标范围、采样窗口、直方图/聚合、trace 筛选、保存形式 | contracts/results；simulator/stats/trace 执行 |
| BenchResult | 状态、实际边界、输入身份、覆盖、输出引用、指标、诊断与停止原因 | contracts/results；与 SimulationResult 共用核心内容 |

BenchSpec 是装配说明，不应拥有运行中的组件队列。BenchResult 不另造一套与 SimulationResult 不兼容的计数器；可作为包含仿真结果与实验上下文的外层对象。

身份至少分开 type_id、instance_id、port_id、request_id、operation_id、data_id/version、allocation_id/generation 和 run_epoch。重试保持同一请求身份；新一次语义操作使用新身份。

## 3 管理与执行调用面

以下名字展示责任分解，可以实现为函数或对象方法，不是可直接调用的代码。

| 调用 | 输入 | 输出与约束 |
| --- | --- | --- |
| describe | 类型或已创建实例 | 参数定义、端口、能力、支持的运行模式 |
| validate | ComponentSpec、连接能力、数值规则 | 结构/条件诊断；不得执行请求或改变状态 |
| create | 冻结规格、注入服务 | 新会话独享实例；不隐式读取全局配置 |
| initialize | InitialStateSpec | 初态身份与加载诊断；必须在运行前完成 |
| submit | Request、当前时间上下文 | Acceptance；接受不代表已消费源或输出可见 |
| on_event | 引擎分发的到期事件 | 局部状态变化、完成通知、待调度事件 |
| observe | ObservationSpec | 只读快照；不能取得可变内部队列引用 |
| finalize | 排空或截断策略 | 终态、未完成清单、有效统计窗口 |

可选能力包括 evaluate（纯功能）、estimate（纯成本）、cancel、snapshot/restore。没有实现某能力的组件必须显式声明 unsupported。estimate 应复用 costmodel 的条件估计；evaluate 不应偷偷创建全局时间引擎。

create 接收的服务按需注入：时间/事件上下文、成本查询、数据访问、随机子流、指标接收器。接口属于 contracts，具体实现可由宿主脚本提供；查询成本不需要事件引擎，元数据仿真不需要真实数组内容。

参考签名可写成 `submit(Request, SimContext) -> Acceptance`。其中 SimContext 仅暴露当前时刻和受约束的事件调度；不能让组件直接修改全局时间或读取未来事件结果。零延迟状态变化也须遵守引擎的 delta round 规则。

## 4 端口协议族

| 协议族 | 典型载荷 | 关键语义 |
| --- | --- | --- |
| compute | 操作、shape、精度、DataRef、输出分配 | 功能、累加、饱和与数据依赖 |
| memory | 地址/区域、读写、长度、掩码、事务属性 | 对齐、访问权限、原子性、返回与可见范围 |
| transfer | 源/目的、步长/张量描述、长度、路径 | 源消费、目的可见、分块完成与故障 |
| stream | chunk、元素类型、序号、帧尾/有效掩码 | 有限缓冲、顺序、ready/valid 或 credit |
| sampled_signal | 采样值/引用、单位、范围、时间窗、校准 | 电压/电流等数值含义、稳定时间和误差 |
| message/packet | 端点、序号、payload、路由/QoS | 包与消息完成区别、重试与丢失模型 |
| control | 启动、等待、屏障、编程、校准、复位 | 作用范围、可取消性、状态转移 |

memory 原子操作、缓存一致性、虚拟地址翻译均为可选能力。支持 read/write 不表示支持 atomic、snoop 或任意地址空间。stream 到 memory 需要显式搬运或缓冲适配器。

内部信号级接口与事务级接口可以并存。RTL 的 ready/valid 每周期握手由适配器翻译为公共事务事件；上层无需依赖具体 RTL 端口名称。

## 5 可配置的输入输出

| 项目 | 推荐选择 | 合法性要求 |
| --- | --- | --- |
| 输入来源 | 内存对象、文件 DataRef、确定性生成器、轨迹、上游端口 | 来源与内容/生成规则哈希进入运行身份 |
| 输出去向 | 内存结果、目标存储、下游端口、artifacts 文件 | 目标容量、所有权与可见性必须明确 |
| 初态 | 冷启动、显式初始化、完整兼容快照 | 仅装载张量不等于恢复在途事务和器件历史 |
| 模型 | functional、analytical、event、cycle、RTL adapter | 以能力向量声明数值/时序/能量覆盖 |
| 输入压力 | 开环时间表、闭环源、最大在途数 | 被背压的请求不得消失或被计为已完成 |
| 观察 | 全量/过滤 trace、聚合指标、局部输出 | 观测设置不得改变执行路径与随机采样 |
| 停止 | 计数完成、时间窗、输入耗尽后排空、显式中断 | 区分窗口结束和成功完成 |

接口外部字段采用稳定 snake_case 与显式单位；界面可以显示中文。用户编辑模板/实例/实验覆盖后生成新配置；正在运行的实验只能通过已定义的控制请求改变状态。

策略以 policy_id/version 和参数选择，不把任意可执行字符串塞进配置。私有扩展例如 `vendor_x.calibration` 必须声明解释者；影响执行的未知扩展拒绝，纯展示元数据可保留。

## 6 CIM 路径的专用字段

首批路径采用可替换的编码、输入驱动、阵列、采样保持、转换与累加阶段。某实现已经包含整个宏时，可以只暴露宏级 compute 请求；其内部阶段由宏拥有，不再独立计费。

| 阶段 | 必需输入 | 主要输出与状态 |
| --- | --- | --- |
| 权重映射/编程 | 逻辑权重、符号/位切片规则、cell 能力、位置 | 映射、program_epoch、有效权重与编程统计 |
| 输入编码与 DAC | 输入位/幅值、通道映射、输入周期、参考范围 | 驱动电压/脉冲描述、稳定时刻、输出负载条件 |
| CIM array | 驱动描述、权重状态、选择行列、误差模型 | 列电流/电荷/等效和、采样时刻、阵列动作量 |
| 采样保持与复用 | 样本向量、保持容量、有效窗、MUX 路由 | 可消费样本、保持期限、路由与占用 |
| ADC | 样本、输入范围、分辨率、转换模式、校准 | 数字码、量化/饱和标记、完成及源释放 |
| 移位与累加 | 数字码、输入/权重切片位置、符号、累加规则 | 部分和版本、最终输出、溢出/饱和诊断 |
| 缓冲及控制 | 分配、槽状态、依赖、阶段完成 | 源租约、槽归还、后继发射与输出可见 |

符号可由差分阵列、偏置补偿或数字分解表达；选择不同方案会改变物理阵列数、ADC 次数和累加量。差分模拟求值与分别量化后相减有不同误差与转换成本，不能仅改一个 signed 标志。

sampled_signal 应明确 quantity_kind、unit、range、sample_time、valid_until、shape、payload_mode 和 calibration_ref。payload_mode 可以为真实数值向量或受限统计描述；统计模式不能用于要求精确输入相关饱和、稀疏和误差反馈的实验。

DAC 到阵列的接口至少校验输出范围、极性、通道/行映射、稳定时间与驱动负载；阵列到 ADC 至少校验被测物理量、输入范围、采样窗口与 MUX 共享。需要电流转电压或缩放时显式加入前端，不能把 ampere 数值直接当作 volt 送入 ADC。

ADC 共享要求样本保持到消费完成，或为每组重新驱动/求值。增大 ADC 数会改变负载、面积、布线和校准条件；通过字段校验不代表原成本表仍适用。

双缓冲建议用每槽 `free → filling → ready → consuming → draining → free` 表示一类简单策略；实际输入/输出槽可拆分。源数据只能在 source_consumed 后复用，目标需要 destination_visible。部分更新采用分块租约，不能用全局 busy 布尔值替代。

## 7 指标名称与计算口径

每条 MetricValue 建议包含 name、value 或 unavailable、unit、resource/scope、window、aggregation、basis（analytic/simulated/measured）、coverage 和来源。不带范围的 bandwidth、cycles、utilization 不足以比较。

| 指标 | 定义或计算 | 必须声明 |
| --- | --- | --- |
| clock_period | 1/f | 时钟域；物理关键路径限制另行验证 |
| service_latency | 资源开始服务到定义完成的时间 | 是否包括阵列稳定、转换、写回 |
| initiation_interval | 相邻请求可启动的最小间隔 | 前提是哪些资源与端口可用 |
| request_latency | 规定完成时刻减提交/到达时刻 | 是否含排队、软件与输出接收 |
| elapsed_time | 测量起点到终点 | 预热、输入装载、编程和排空 |
| domain_cycles | 指定时钟域的周期计量 | 固定 f 可用 T×f；多域不能直接相加 |
| logical_work | GEMM 的 M×N×K MAC；MatVec 的 R×C MAC | MAC 是否按 2 ops；输出形状与数值语义 |
| executed_work | 实际执行的 tile、位串行、padding、重算和转换 | 稀疏掩码与跳过机制；与逻辑工作分开 |
| adc_conversions | 实际转换次数及有效码位 | ADC 共享、差分位置、过采样、输入切片 |
| logical/allocated/access/wire_bytes | 逻辑有效、分配、存储访问、链路字节 | 打包、元数据、行/页放大、协议开销 |
| peak_live_bytes | 同时有效分配的最大容量 | 预留槽、别名、临时部分和与元数据 |
| throughput | 完成工作量/测量时间 | 工作单位、批量、稳态及终止条件 |
| utilization | 已占槽位时间/可用槽位时间 | 槽位数、窗口、禁用或降频区间 |
| energy | 动作能量累计 + 各状态漏电积分 | 阵列、外围、控制、传输是否覆盖 |
| numerical_quality | 误差、饱和/溢出、必要时任务质量 | 参考、分布、种子、相关性及容差 |

固定频率下 C cycles 的时间为 C/f。变频时按每段或积分计算，不能用最后一个频率换算整个实验。时钟门控下“墙钟折算周期”“实际时钟边沿数”“忙碌周期”也不同。

理想吞吐为并行资源数 × 每次发射工作量 / II。连续 n 项在无外部争用的流水线中可用首项延迟 + (n−1)×II 检查；发生背压后必须由实际事件推导。

数据路径的必要下界可写为 `T >= max(无争用关键依赖路径时间, max_r(资源 r 的工作量/其服务率))`。该式要求工作量与服务率使用相同单位和范围；它一般不可直接当作可达到的完成时间。计算、访存与通信完全串行时才相加；部分重叠应模拟。

多级缓存分别记录请求、命中、miss、MSHR 合并、写回、预取、下级访问；不能用一个全局 miss_rate 推导所有层次流量。DRAM 请求字节、阵列内部读出量和外部总线字节也不等价。

## 8 数据 版本与替换

数据对象沿用 DataRef 的位置、版本、分配世代与内容引用。真实数值与元数据运行使用相同位置/依赖语义，但结果中的功能验证状态不同。

替换模型前核对端口协议、数值语义、能力谓词、可见性、成本范围和支持初态。接口签名相同不代表结果可比。模拟 ADC 换为理想量化器会改变误差覆盖，必须进入模型身份与结果声明。

扩展公开操作或改变语义需新版本；仅改变内部数据结构可保持公共版本但更新实现版本。手写计划声明 manual 生产者，导入轨迹声明 trace_import 生产者，不能伪装为编译器结果。

## 9 最小错误与验收集合

错误应返回字段路径、组件/端口、发生阶段及可操作原因。至少区分 invalid_spec、incompatible_protocol、unsupported_operation、infeasible_mapping、missing_characterization、out_of_domain、backpressured、data_not_visible、cancelled 和 internal_error。

运行前检查：端口未闭合、单位不匹配、地址越界、负容量、零 II、未声明量化范围、ADC 数/列映射不合法、样本保持不足、输出分配太小。backpressured 是可恢复流控，不能被当作执行失败或成功吞掉。

运行时检查：源复用过早、重复完成、缓存失效后继续使用、复位残留事件、输出接收阻塞与停止后未排空。恢复快照时核对组件/数据/事件/随机状态，单独复制 SRAM 数组不能视为完整恢复。

首批固定夹具应能比较真实数值与独立整数参考，手算 ADC 分组和样本生命周期；随后改变接收速率、ADC 共享数和缓冲容量，证明结果对真实瓶颈作出反应。
