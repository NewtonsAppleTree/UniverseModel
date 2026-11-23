# composition：组合关系与可证明的时间界

本模块不新增硬件服务能力。它连接计算、存储、搬运、通信和物理条件，并检查它们是否以一致的身份和单位描述同一条路径。

| 结构 | 责任 | 子层说明 |
| --- | --- | --- |
| ResourceNode/Port/Connection | 唯一实例、无环归属、静态协议/单位检查 | [Tile](tile/UNITS.md)、[Die](die/UNITS.md)、[Package](package/UNITS.md) |
| validate_model_selection | 同一计量口径选择摘要或内部资源，避免重叠计费 | 容器 model_id=None；资源可被多个真实操作使用 |
| ActionEstimate/ResourceDemand | 任务的完成后依赖与实际工作量 | 操作 DAG 与物理拓扑分开 |
| ResourceBudget/TimeBounds | 供给包络与完成时间下界 | 不运行调度器，不输出实际完成时间 |

## 系统公式与关键参数

对资源 r，必须有依据地声明任意长度 T 的统计窗口最多供给 `b_r + rate_r*T` 工作。b 是首批/突发供给 credit，单位与工作量相同。于是 `T≥max(0,(ΣW_r−b_r)/rate_r)`；依赖路径另给 `T≥max_path Σlatency_i`。最终取两类下界最大值。

如果每 P 个 lane 在周期零能发起一批、每 II cycles 再发起一批，发起包络可以用 b=P、rate=P*f/II；不能一律设 b=0 并将短批次 W/r 当作严格下界。传输按连续流体服务且没有初始 credit 时才可用 b=0。输出完成与发起速率还需相应 latency 约束。

最关心依赖、共享资源、实际工作量、单位、统计窗口和供给模型。ResourceDemand 必须有对应 budget 且单位一致。仅已声明的资源进入分析；漏掉存储、同步或热限制只会使这个下界偏乐观，不能将其命名为系统预测时间。

## 使用顺序与边界

定义资源/端口 → validate_graph → 选择当前指标的计量资源并 validate_model_selection → 组装操作与显式资源工作 → estimate_time_bounds。任务前驱表示整体完成后才能启动；分块可见/流式重叠需要拆分操作或后续事件模型。

协议字符串应标明双方约定的编码/shape 版本；当前检查相等，不推导任意 shape 兼容或模拟电气负载。连接可有环，归属与操作依赖不允许有环。Port 完整闭合、共享仲裁、死锁、取消和可见性生命周期仍属后续台架。

## 搬运账本与数字Tile

[transfer.py](transfer.py)通过MemoryResource、DmaResource、PathLink和共同TransferResources校验owner、地址域、路径与服务单位。`analyze_transfers`输出逐请求边界、actions/budgets、逐资源贡献、共同SRAM服务和未知成本。完整摘要与展开后代不同时计费；NoC多hop只支持同构同钟，D2D只支持单条有向链路。

[DigitalTile](tile/UNITS.md)进一步合并本地计算访问、DMA和buffer预留。先装配资源→输入显式请求/工作→validate_reservations→analyze_transfers/analyze_tile。当前统计不建立存储内容、事件或真实可行调度。

包络与DAG中间量使用Fraction，整数配置保留精度；仅输出时转binary64，正值下溢/溢出报错。浮点输入按其确切binary64值运算。手算、参数来源和适用范围见[基础指南](../docs/foundation_usage.md)。

[CIM局部台架](tile/UNITS.md)现已复用相同归属、计量选择、actions/budgets及资源贡献；增加有限样本保持、内部ADC在途、数字寄存器和显式串行phase分析。它不要求完整Die/Package或compiler；读取能耗和编程成本保持未知。

## CH7外存与缓存接入

[memory.py](memory.py)先运行cache元数据轨迹，再把回填读交给DRAM span；每channel只计一次burst需求，rank共享预算。dirty写回保持在有序事务中，写服务、lookup、队列和完整执行时间未知。初态须匹配profile且驻留行在backing内，backing容量须由完整cache行组成。

MemoryResource可选SRAM、DRAM读profile或容量边界，三者互斥；DRAM拥有CK/data clock。TransferRequest.source_row_state显式声明DRAM读条件，非DRAM源不可附加。读入搬运/Tile复用同一账本，逻辑byte与burst byte分开；memory/channel/i/read_bus为无初始credit的共享服务预算，派生ID碰撞被拒绝。外存写不借用读时序；DRAM条件界不与内部行/bus界重复相加。独立接口与验证见[CH7指南](../docs/memory_access.md)。

## CH8多Tile与Die/Package

[TileBinding](tile/UNITS.md)只引用共享清单，[Die拓扑](die/UNITS.md)验证domain/物理归属和clock，[ChipAssembly](package/UNITS.md)累计全部job的真实MAC/local/DMA工作。共享容量与初始credit不按Tile数量复制；有向D2D分别报告payload/protocol/wire；未排序的共享预留不允许重叠。

project_scopes对同一资源包络指标给出summary或expanded视图，禁止祖先与后代混选，不提供另一份可叠加成本。整体执行时间、CDC/队列与物理成本仍未知，复现与反例见[CH8指南](../docs/assembly.md)。

<!-- model-fields:start -->

### [bounds.py](bounds.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `ResourceBudget` | `resource_id` | `str` | 1（标识/枚举） | 唯一资源身份，与 demand 引用一致。 |
| `ResourceBudget` | `work_unit` | `str` | 1（标识/枚举） | 资源工作单位，如 MAC、B、conversion。 |
| `ResourceBudget` | `rate_per_s` | `int \| float` | work_unit/s | 可证明的供给速率上界 r [work_unit/s]；整数配置保留精度。 |
| `ResourceBudget` | `initial_credit` | `int \| float` | work_unit | 时间零额外供给上界 b [work_unit]；整数计数先精确扣除。 |
| `ResourceDemand` | `resource_id` | `str` | 1（标识/枚举） | 承担此工作量的资源身份。 |
| `ResourceDemand` | `work_unit` | `str` | 1（标识/枚举） | 与 budget 一致的工作单位。 |
| `ResourceDemand` | `amount` | `int \| float` | work_unit | 实际工作量 W [work_unit]；包含映射额外工作，整数精确累计。 |
| `ActionEstimate` | `action_id` | `str` | 1（标识/枚举） | 当前任务内唯一的操作身份。 |
| `ActionEstimate` | `latency_s` | `float` | s | 满足输入条件后的最小完成延迟 [s]。 |
| `ActionEstimate` | `dependencies` | `tuple[str, ...]` | 1（标识/枚举） | 必须先完成的操作 ID；不表示全部硬件连接。 |
| `ActionEstimate` | `demands` | `tuple[ResourceDemand, ...]` | —（结构/对象） | 此操作声明的资源工作量。 |
| `TimeBounds` | `critical_path_s` | `float` | s | 操作 DAG 上延迟和的最大值 [s]。 |
| `TimeBounds` | `resource_bound_s` | `float` | s | max_r(max(0,(ΣW_r−b_r)/r_r)) [s]。 |
| `TimeBounds` | `lower_bound_s` | `float` | s | max(critical_path_s,resource_bound_s) [s]。 |
| `TimeBounds` | `serial_latency_sum_s` | `float` | s | 所有操作最小延迟之和 [s]；不是已验证的系统上界。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `ResourceBudget` | 资源供给包络 W(T)≤initial_credit+rate*T；首批/流水线突发能力必须显式给出。 |
| `ResourceDemand` | 一次操作实际消耗的资源工作量；不同单位的 demand 禁止直接累加。 |
| `ActionEstimate` | 操作以完成后依赖表示；latency 是该操作的最小延迟，不是峰值倒数。 |
| `TimeBounds` | 只对已声明的任务/资源给出必要时间界；缺失资源仍可能进一步限制系统。 |
| `estimate_time_bounds(actions: tuple[ActionEstimate, ...], budgets: tuple[ResourceBudget, ...])` | 在依赖 DAG 上动态规划；按唯一资源累加工作，再应用各自的供给包络。 |

### [graph.py](graph.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `Port` | `name` | `str` | 1（标识/枚举） | 节点内唯一端口名；无量纲标识。 |
| `Port` | `direction` | `str` | 1（标识/枚举） | input 或 output；双向接口显式拆为两个端口。 |
| `Port` | `protocol` | `str` | 1（标识/枚举） | 协议/数值格式版本标识，不根据单位自动推断。 |
| `Port` | `unit` | `str` | 1（标识/枚举） | Payload 物理量单位，如 V、A、code、B。 |
| `ResourceNode` | `instance_id` | `str` | 1（标识/枚举） | 整张图唯一的物理实例身份。 |
| `ResourceNode` | `parent_id` | `str \| None` | 1（标识/枚举） | 归属父节点；局部台架根节点为 None。 |
| `ResourceNode` | `model_id` | `str \| None` | 1（标识/枚举） | 可选成本/功能模型身份；None 表示纯容器。 |
| `ResourceNode` | `ports` | `tuple[Port, ...]` | —（结构/对象） | 本节点端口定义；空 tuple 表示没有声明端口。 |
| `Connection` | `source_id` | `str` | 1（标识/枚举） | 源实例身份。 |
| `Connection` | `source_port` | `str` | 1（标识/枚举） | 源 output 端口名。 |
| `Connection` | `target_id` | `str` | 1（标识/枚举） | 目标实例身份。 |
| `Connection` | `target_port` | `str` | 1（标识/枚举） | 目标 input 端口名。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `Port` | 一个静态端口的边界契约；协议身份必须包含双方约定的编码/shape 语义。 |
| `ResourceNode` | Tile/Die/Package 与叶子资源共用归属节点；容器 model_id=None，不额外计费。 |
| `Connection` | 一条有向连接只引用现存端口；协议转换器必须作为显式节点出现。 |
| `validate_graph(nodes: tuple[ResourceNode, ...], connections: tuple[Connection, ...])` | 校验唯一身份、无环包含与端口兼容；允许局部多根资源及 ring 等有环连接。 |
| `validate_model_selection(nodes: tuple[ResourceNode, ...], selected_ids: tuple[str, ...])` | 同一指标口径中选择摘要或内部细模型；祖先和后代不可同时成为收费方。 |

### [memory.py](memory.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `CachedDramAnalysis` | `cache` | `CacheTrace` | —（结构/对象） | 精确元数据命中/替换与有序外存事务。 |
| `CachedDramAnalysis` | `read_services` | `tuple[DramSpanEstimate, ...]` | —（结构/对象） | 每次cache fill的DRAM条件估算。 |
| `CachedDramAnalysis` | `channel_read_bytes` | `tuple[tuple[int, int], ...]` | B | 每channel累计burst有效接口字节 [B]，rank共享。 |
| `CachedDramAnalysis` | `read_lower_bound_s` | `float` | s | max(所有fill条件界,每channel字节/带宽) [s]。 |
| `CachedDramAnalysis` | `execution_time_s` | `None` | —（结构/对象） | lookup、写回、队列与调度未知，整体执行时间不推定。 |
| `CachedDramAnalysis` | `unknown_costs` | `tuple[str, ...]` | 1（标识/枚举） | 已触及的cache/DRAM缺项；空轨迹可为空。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `CachedDramAnalysis` | 只引用cache及一个DRAM backing；DRAM读填充计一次，dirty写回保留未知。 |
| `analyze_cached_dram(params: CacheParams, dram: DramReadProfile, accesses: tuple[MemoryAccess, ...], *, row_state: str, initial_state: CacheState \| None=None, flush: bool=False, max_line_touches: int=100000)` | 验证完整cache行均落入backing；初态显式恢复，row_state仅用于每个fill的条件分析。 |

### [transfer.py](transfer.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `MemoryResource` | `resource_id` | `str` | 1（标识/枚举） | 唯一物理 backing 身份；owner 由资源图给出。 |
| `MemoryResource` | `domain_id` | `str` | 1（标识/枚举） | 唯一地址域及路由端点身份。 |
| `MemoryResource` | `capacity_bytes` | `int` | B | 可寻址容量 [B]。 |
| `MemoryResource` | `sram` | `SramParams \| None` | —（结构/对象） | SRAM服务；与dram_read互斥，两者均None时仅声明容量。 |
| `MemoryResource` | `clock` | `ClockDomain \| None` | —（结构/对象） | SRAM 时钟；容量边界不能附带虚构服务时钟。 |
| `MemoryResource` | `unknown_reason` | `str \| None` | 1（标识/枚举） | 缺少服务 profile 的原因；已建模 SRAM 为 None。 |
| `MemoryResource` | `dram_read` | `DramReadProfile \| None` | —（结构/对象） | DRAM读服务及其自有CK/data clock；写服务始终未知。 |
| `DmaResource` | `resource_id` | `str` | 1（标识/枚举） | 物理通道身份，重复请求共享同一预算。 |
| `DmaResource` | `params` | `DmaParams` | —（结构/对象） | 每请求启动、burst 与通道占用参数。 |
| `DmaResource` | `clock` | `ClockDomain` | Hz | 通道时钟 f_dma [Hz]。 |
| `DmaResource` | `direct_memory_ids` | `tuple[str, ...]` | 1（标识/枚举） | 显式直接可达的 memory IDs；两端均在此列才可省略路径。 |
| `PathLink` | `resource_id` | `str` | 1（标识/枚举） | 共享链路的唯一物理身份。 |
| `PathLink` | `source_domain` | `str` | 1（标识/枚举） | 此方向的源端点/中间路由域。 |
| `PathLink` | `target_domain` | `str` | 1（标识/枚举） | 此方向的目标端点/中间路由域。 |
| `PathLink` | `params` | `NoCPathParams \| SerialLinkParams` | —（结构/对象） | 单 hop NoC 或 D2D 编码 profile。 |
| `PathLink` | `clock` | `ClockDomain \| None` | —（结构/对象） | NoC 必需；串行链路使用 bit rate，无此时钟。 |
| `TransferResources` | `nodes` | `tuple[ResourceNode, ...]` | —（结构/对象） | 资源归属图；容器 model_id=None。 |
| `TransferResources` | `memories` | `tuple[MemoryResource, ...]` | —（结构/对象） | 唯一地址域和 backing 清单。 |
| `TransferResources` | `channels` | `tuple[DmaResource, ...]` | —（结构/对象） | 串行 DMA 通道清单。 |
| `TransferResources` | `links` | `tuple[PathLink, ...]` | —（结构/对象） | 固定方向链路清单。 |
| `TransferRequest` | `request_id` | `str` | 1（标识/枚举） | 批内唯一传输身份。 |
| `TransferRequest` | `source_id` | `str` | 1（标识/枚举） | 源 backing ID。 |
| `TransferRequest` | `target_id` | `str` | 1（标识/枚举） | 目标 backing ID。 |
| `TransferRequest` | `source_address_bytes` | `int` | B | 源资源本地地址 [B]。 |
| `TransferRequest` | `target_address_bytes` | `int` | B | 目标资源本地地址 [B]。 |
| `TransferRequest` | `payload_bytes` | `int` | B | 保守恒的逻辑字节 D [B]。 |
| `TransferRequest` | `channel_id` | `str` | 1（标识/枚举） | 承担本请求的 DMA 通道 ID。 |
| `TransferRequest` | `path` | `tuple[str, ...]` | 1（标识/枚举） | 有向 link IDs；空路径须符合直接可达声明。 |
| `TransferRequest` | `dependencies` | `tuple[str, ...]` | 1（标识/枚举） | 先完成的传输 request IDs；无隐式全局序列化。 |
| `TransferRequest` | `source_row_state` | `str \| None` | 1（标识/枚举） | DRAM源读的显式hit/closed/conflict条件；非DRAM源须为None。 |
| `TransferLeg` | `request_id` | `str` | 1（标识/枚举） | 来源请求身份。 |
| `TransferLeg` | `resource_id` | `str` | 1（标识/枚举） | 实际承载资源 ID。 |
| `TransferLeg` | `role` | `str` | 1（标识/枚举） | source_read、dma、link 或 target_write。 |
| `TransferLeg` | `logical_bytes` | `int` | B | 此边界的有效载荷 [B]。 |
| `TransferLeg` | `service_unit` | `str` | 1（标识/枚举） | word、cycle、flit 或 bit。 |
| `TransferLeg` | `service_amount` | `int \| None` | —（结构/对象） | 对应服务工作量；未知 memory 为 None。 |
| `TransferLeg` | `protocol_bytes` | `int` | B | 链路编码前头尾开销 [B]；非链路为零。 |
| `TransferLeg` | `packet_count` | `int` | packet | 链路 packet 数 [packet]；非链路为零。 |
| `TransferLeg` | `isolated_time_s` | `float \| None` | s | 空闲服务或DRAM条件span下界 [s]；未知为None。 |
| `TransferLeg` | `unknown_reason` | `str \| None` | 1（标识/枚举） | 服务未知的明确原因。 |
| `ResourceContribution` | `resource_id` | `str` | 1（标识/枚举） | bank 端口、DMA 或有向链路的服务身份。 |
| `ResourceContribution` | `work_unit` | `str` | 1（标识/枚举） | 与预算一致的服务单位。 |
| `ResourceContribution` | `amount` | `int \| float` | —（结构/对象） | ΣW；整数计数保留精度。 |
| `ResourceContribution` | `lower_bound_s` | `float` | s | max(0,(ΣW-b)/r) [s]。 |
| `TransferAnalysis` | `legs` | `tuple[TransferLeg, ...]` | —（结构/对象） | 请求→边界明细。 |
| `TransferAnalysis` | `actions` | `tuple[ActionEstimate, ...]` | —（结构/对象） | 每请求 latency=max(已知隔离资源时间)，含显式依赖。 |
| `TransferAnalysis` | `budgets` | `tuple[ResourceBudget, ...]` | —（结构/对象） | 唯一资源供给包络。 |
| `TransferAnalysis` | `contributions` | `tuple[ResourceContribution, ...]` | —（结构/对象） | 每资源累计必要服务贡献。 |
| `TransferAnalysis` | `sram_services` | `tuple[tuple[str, SramService], ...]` | 1（标识/枚举） | 全批源读/目标写在共同 backing 上合并。 |
| `TransferAnalysis` | `bounds` | `TimeBounds` | —（结构/对象） | 依赖和资源包络下界；不会串加流水线各 hop 整包时间。 |
| `TransferAnalysis` | `lower_bound_s` | `float` | s | max(bounds,各 backing 全批隔离服务) [s]。 |
| `TransferAnalysis` | `unknown_costs` | `tuple[str, ...]` | 1（标识/枚举） | 已触及但未建模的 memory 成本原因。 |
| `TransferAnalysis` | `dram_services` | `tuple[tuple[str, DramSpanEstimate], ...]` | 1（标识/枚举） | backing ID及各源读的逐行条件估算。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `MemoryResource` | 地址以资源本地 byte offset 表示；domain_id 明确路由端点，不跨资源推断地址别名。 |
| `DmaResource` | 串行请求 DMA 通道；本模型控制和数据通路不覆盖源存储、链路与目标存储。 |
| `PathLink` | 一条单向资源；反方向或另一条物理通道必须使用不同 ID。 |
| `TransferResources` | 一份共同资源清单决定共享、包含和计量粒度，避免重复的摘要模型收费。 |
| `TransferRequest` | 有限拷贝请求，不承诺数据已写回可见；dependencies 仅表示调用者声明的完成先后。 |
| `TransferLeg` | 每条请求的一个边界贡献；工作量单位取决于资源，逻辑字节不含协议开销。 |
| `ResourceContribution` | 各资源的包络贡献独立报告，保留实际工作与供给边界以解释瓶颈。 |
| `TransferAnalysis` | 分析输出保留账本、可组合 actions/budgets 和未建模成本；没有目标完成事件。 |
| `sram_budgets(memory: MemoryResource)` | 对 bank 创建独立 R/W 或共享 RW 的服务包络；初始 P 项允许起点瞬时发起。 |
| `sram_demands(memory: MemoryResource, service: SramService)` | 把实际 word 事务绑定到唯一 bank 端口；仅引用 backing 的资源，不按 buffer 再计量。 |
| `dram_budgets(memory: MemoryResource)` | DRAM所有rank共享每channel的一份数据总线预算；byte为完整burst字节，无起点免费传输。 |
| `resource_contributions(actions: tuple[ActionEstimate, ...], budgets: tuple[ResourceBudget, ...])` | 累计账本后用精确包络函数生成贡献，不把多个共享请求当作独立硬件。 |
| `analyze_transfers(resources: TransferResources, requests: tuple[TransferRequest, ...])` | 展开存储和路径边界；同构 NoC 用 wormhole 公式，单条 D2D 用编码模型。 |

<!-- model-fields:end -->
