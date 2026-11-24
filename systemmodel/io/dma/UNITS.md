# dma：本地源写入、完整拷贝链与共享服务下界

研究同一任务/预算下直传与host staging增加哪些存储读写、DMA启动及共享线路工作。专业模型引用S2内存预留和S1显式路径，复用chipmodel的DmaParams、ClockDomain与资源依赖下界，不生成另一份芯片状态或第二套DMA公式。

| Unit / 文件 | 独立行为与覆盖 |
| --- | --- |
| DmaEngine / [model.py](model.py) | 单个串行DMA通道、祖先拥有的egress、显式本地read_backing_ids、DMA参数/时钟与来源 |
| DmaSystem / model.py | memory/profile/engine/line服务组合；校验唯一物理资源、归属、格式与ceiling口径 |
| CopyLeg / CopyChain / CopyBatch | 显式源/目标视图与地址；链内完整copy完成依赖；批内独立链和一个逻辑phase |
| analyze_transfers / [analysis.py](analysis.py) | 放置→解地址→检查本地源/目的权限→实际路径→帧/DMA/共享工作→hazard→必要时间界 |
| validate_transfers / analysis.py | 同一声明和已保存SystemPath重分析；不重新寻找路径 |
| TransferAnalysis / analysis.py | placement、leg、memory_work、staging、actions、budgets、contributions、bounds及unknown_costs |

## 参数、单位与资源关系

代码旁注是字段维护定义。egress端口owner必须是engine和本地源backing的祖先，源视图domain必须等于egress domain；read_backing_ids显式授予本地源直连服务范围。只模拟posted-write搬运，不把远端源读当作免费的本地访问。target view的write权限和每一段路由能力都检查。

| 量 | 关系与范围 |
| --- | --- |
| payload_bytes | 正逻辑B；每条链所有leg都搬运同样D。对象可大于copy子区间 |
| source_address / target_address | 对应view域中的B地址；由S2解为backing物理区间并验证phase/权限 |
| bytes_per_cycle / max_burst_bytes | DMA通道数据拍 [B/cycle]、burst最大B，burst按拍对齐 |
| startup_cycles / burst_overhead_cycles | 每leg启动、每burst串行控制 [cycle]，不含软件launch或内存时延 |
| completion_cycles | 已有公式`startup + ceil(D/max_burst)×overhead + ceil(D/bytes_per_cycle)`；单通道必要服务工作 |
| clock.frequency_hz | 本通道cycle/s；cycle只在所属clock下换成second |
| frame_byte / payload_byte / cycle | 分离资源工作口径，不能跨单位直接相加 |
| constraints | 复用唯一BandwidthConstraint；只接受declared_ceiling，frame必须匹配profile_id |
| initial_credit | 本包显式设0；通道/线路服务无预付工作；不把已完成搬运算入任务 |
| leg.lower_bound_s | 当前leg已知必要资源时间的最大值；重复使用同一资源先累计工作，独立hop不串加完整包时间 |
| resource_bound_s | `max_r(Σ_leg W_r / rate_r)`；共享资源预算仅一份 |
| critical_path_s | 链内每个完整copy的必要延迟之和，再在独立链间取最大 |
| bounds.lower_bound_s | max(critical_path_s, resource_bound_s)；不是可达调度完成时间 |
| memory_work | 按唯一backing累加有用read/write B，不推断cache、DRAM burst或访存延迟 |
| staging_allocation_ids | 链中间实际使用的allocation，alias不重复；容量仍由完整MemoryPlan检查 |

链内后一leg源物理区间必须等于前一leg目标（允许地址alias）；整份D先搬完再读，输入placement必须为staging预留足够空间。没有分块流水、自动buffer分配、源数据内容验证或完成/可见性事件。每个leg禁止源/目的物理重叠，不推断memmove语义；独立链允许read/read共享，禁止任何未排序的read/write或write/write相交。全部copy使用同一个逻辑phase，phase不是实际时间。

engine、PCIe service与topology constraint计量选择共同检查，禁止相同resource或父摘要/子细服务同时收费。多条有向wire引用同一PCIe service时实际多次访问分别计工作；每个经过的wire必须有服务，未建模线路直接拒绝。未使用预算不贡献时间，未知backing服务则逐项保留unknown_costs。

## 调用、敏感性、证据

先构造DmaSystem和CopyBatch，再独立analyze_transfers；实验配置/记录在evaluation层，不依赖workload或整条工具链。最多1024 leg是宿主材料化/冲突检查上限，不是硬件队列。逐对hazard最坏O(L²)，视图解析重用S2完整校验，不把宿主性能当目标性能。

关键敏感量：D、DMA启动/突发/时钟、TLP粒度、线路/共享ceiling、链的完整copy依赖及staging容量。手算512 B：100启动+2×4控制+16数据=124 cycle；1 GB/s共享payload资源给512 ns必要界；两leg中转或两独立同路径copy共享工作为1024 B。1 B为105 cycle，由启动主导；测试含去启动与倍增共享带宽敏感性、160组分包参考、alias连续性、方向不对称和非法hazard。

所有性能仅为具名假设下的已知服务/依赖下界；实际内存服务、PCIe控制/信用/重放、排队、软件launch、数据可见性和完整物理能耗未知。来源与14例实验口径见[S3指南](../../docs/transfer_usage.md)，状态见[STATUS](../../../docs/STATUS.md)。

<!-- model-fields:start -->

### [analysis.py](analysis.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `CopyLegAnalysis` | `chain_id` | `str` | 1（标识/枚举） | Owning logical copy chain. |
| `CopyLegAnalysis` | `leg_id` | `str` | 1（标识/枚举） | Unique action identity. |
| `CopyLegAnalysis` | `engine_id` | `str` | 1（标识/枚举） | One serial DMA channel resource. |
| `CopyLegAnalysis` | `source` | `ResolvedSpan` | —（结构/对象） | Readable local source bytes, not a simulated memory read. |
| `CopyLegAnalysis` | `target` | `ResolvedSpan` | —（结构/对象） | Writable destination bytes, not proof of data visibility. |
| `CopyLegAnalysis` | `path` | `SystemPath` | —（结构/对象） | Actual posted-write route; no implicit P2P or intermediate endpoint transit. |
| `CopyLegAnalysis` | `dma` | `DmaEstimate` | —（结构/对象） | Existing channel startup/burst service, excluding memory and link service. |
| `CopyLegAnalysis` | `traffic` | `PcieTraffic` | —（结构/对象） | Exact useful/padded/protocol bytes for one traversal. |
| `CopyLegAnalysis` | `lower_bound_s` | `float` | s | Maximum known necessary resource service within this leg [s], not sum of hop times. |
| `MemoryWork` | `backing_id` | `str` | 1（标识/枚举） | Unique physical backing, shared by all address aliases. |
| `MemoryWork` | `read_bytes` | `int` | B | Total requested useful source bytes [B]; no cache/DRAM transaction inference. |
| `MemoryWork` | `write_bytes` | `int` | B | Total requested useful destination bytes [B]. |
| `ServiceWork` | `resource_id` | `str` | 1（标识/枚举） | Unique channel, line service or declared shared constraint. |
| `ServiceWork` | `work_unit` | `str` | 1（标识/枚举） | cycle, frame_byte or payload_byte; different representations cannot be summed. |
| `ServiceWork` | `amount` | `int` | —（结构/对象） | Sum of all actual visits' work in work_unit, exact integer. |
| `ServiceWork` | `rate_per_s` | `float` | work_unit/s | Declared zero-credit service ceiling [work_unit/s]. |
| `ServiceWork` | `lower_bound_s` | `float` | s | amount / rate_per_s [s]. |
| `TransferAnalysis` | `system_identity` | `str` | 1（标识/枚举） | Complete memory/PCIe/channel/source SHA256. |
| `TransferAnalysis` | `batch_identity` | `str` | 1（标识/枚举） | Complete placement/request/chain/source SHA256. |
| `TransferAnalysis` | `placement` | `PlacementAnalysis` | —（结构/对象） | Valid physical/address reservation analysis at all declared phases. |
| `TransferAnalysis` | `legs` | `tuple[CopyLegAnalysis, ...]` | —（结构/对象） | Canonical chain order, preserving execution dependency order inside each chain. |
| `TransferAnalysis` | `memory_work` | `tuple[MemoryWork, ...]` | —（结构/对象） | Unique backing read/write totals; timing unknown. |
| `TransferAnalysis` | `staging_allocation_ids` | `tuple[str, ...]` | 1（标识/枚举） | Actual intermediate physical reservations, deduplicated across aliases. |
| `TransferAnalysis` | `actions` | `tuple[ActionEstimate, ...]` | —（结构/对象） | Whole-copy dependency DAG and actual resource demands. |
| `TransferAnalysis` | `budgets` | `tuple[ResourceBudget, ...]` | —（结构/对象） | Unique ceilings; initial_credit=0 is an explicit service assumption. |
| `TransferAnalysis` | `contributions` | `tuple[ServiceWork, ...]` | —（结构/对象） | Aggregate service demand and explanatory bounds. |
| `TransferAnalysis` | `bounds` | `TimeBounds` | —（结构/对象） | Maximum of necessary dependency and shared-work bounds. |
| `TransferAnalysis` | `unknown_costs` | `tuple[str, ...]` | 1（标识/枚举） | Explicit omitted services/costs; unknown never becomes zero energy/time. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `CopyLegAnalysis` | One copy exposes its resolved bytes, request route and channel/TLP accounting for independent replay. |
| `MemoryWork` | Read/write byte counts remain explicit even when backing timing is unknown. |
| `ServiceWork` | Work is accumulated once per physical resource, retaining repeated visits from real transfer paths. |
| `TransferAnalysis` | Static transfer evidence combines byte conservation, staging reservations and necessary service/dependency bounds. |
| `analyze_transfers(system: DmaSystem, batch: CopyBatch)` | Analyze declared local-source posted writes and whole-buffer staging with deterministic path search when needed. |
| `validate_transfers(system: DmaSystem, batch: CopyBatch, saved_paths: tuple[SystemPath, ...])` | Independently recheck saved paths and deterministic work/bounds without selecting new routes or running hardware. |

### [model.py](model.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `DmaEngine` | `resource_id` | `str` | 1（标识/枚举） | One exclusive serial DMA channel service, not an aggregate device summary. |
| `DmaEngine` | `egress_port_id` | `str` | 1（标识/枚举） | Initiating address-terminal port owned by an ancestor of this engine. |
| `DmaEngine` | `read_backing_ids` | `tuple[str, ...]` | 1（标识/枚举） | Explicit local source attachments; no implicit remote pull/read service. |
| `DmaEngine` | `params` | `DmaParams` | —（结构/对象） | Existing chipmodel startup, beat width and burst-control service model. |
| `DmaEngine` | `clock` | `ClockDomain` | —（结构/对象） | Clock converting this engine's cycles to seconds. |
| `DmaEngine` | `source_ref` | `str` | 1（标识/枚举） | Hardware channel service/attachment assumption; excludes software launch overhead. |
| `DmaSystem` | `memory` | `MemorySystem` | —（结构/对象） | Authoritative physical capacity, mappings' hardware identity and node topology. |
| `DmaSystem` | `profile` | `PcieProfile` | —（结构/对象） | One negotiated conventional posted-write format across this fabric. |
| `DmaSystem` | `engines` | `tuple[DmaEngine, ...]` | —（结构/对象） | Unique channel resources; references never multiply service capacity. |
| `DmaSystem` | `pcie_services` | `tuple[PcieService, ...]` | —（结构/对象） | Unique raw-line services, each wire attached at most once. |
| `DmaSystem` | `source_ref` | `str` | 1（标识/枚举） | Whole-service assembly provenance; calibration is not implied. |
| `DmaSystem` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Hardware identity includes source, memory, channels, clocks, framing, coding and every shared resource. |
| `CopyLeg` | `leg_id` | `str` | 1（标识/枚举） | Globally unique leg/action ID within a batch. |
| `CopyLeg` | `engine_id` | `str` | 1（标识/枚举） | Explicit hardware DMA channel. |
| `CopyLeg` | `source_region_id` | `str` | 1（标识/枚举） | Readable local view; may alias a prior chain destination. |
| `CopyLeg` | `source_address` | `int` | B | First useful source byte in its address domain [B]. |
| `CopyLeg` | `target_region_id` | `str` | 1（标识/枚举） | Writable destination view served by the posted-write route. |
| `CopyLeg` | `target_address` | `int` | B | First useful target byte in its address domain [B]. |
| `CopyLeg` | `link_ids` | `tuple[str, ...] \| None` | 1（标识/枚举） | Explicit route, or deterministic connectivity search. |
| `CopyLeg` | `max_hops` | `int` | link | Host traversal guard [link], unrelated to target time. |
| `CopyChain` | `chain_id` | `str` | 1（标识/枚举） | Independent logical transfer identity in a batch. |
| `CopyChain` | `payload_bytes` | `int` | B | Positive useful payload D [B], conserved through every leg. |
| `CopyChain` | `legs` | `tuple[CopyLeg, ...]` | —（结构/对象） | Ordered nonempty copies; each next source must equal the previous physical destination. |
| `CopyBatch` | `placement` | `MemoryPlan` | —（结构/对象） | Explicit source/destination/staging reservations; does not allocate hidden host buffers. |
| `CopyBatch` | `phase` | `int` | —（结构/对象） | Shared logical liveness phase, not target start time or duration. |
| `CopyBatch` | `chains` | `tuple[CopyChain, ...]` | —（结构/对象） | Independent chains, with complete sequential copies inside each chain. |
| `CopyBatch` | `source_ref` | `str` | 1（标识/枚举） | Transfer strategy/input provenance; source contents and visibility are assumptions. |
| `CopyBatch` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Input identity includes full placement, phase, complete chain order and all requested paths. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `DmaEngine` | An engine reads only explicitly attached local backings and sends posted writes from a terminal egress. |
| `DmaSystem` | Sidecar service model preserves S0/S2 schemas while binding ownership and eliminating overlapping service summaries. |
| `DmaSystem.identity_hash` | Hardware identity includes source, memory, channels, clocks, framing, coding and every shared resource. |
| `CopyLeg` | One complete copy leg names local source and remotely writable destination views; dependencies come from chain order. |
| `CopyChain` | Chains impose full-copy completion before the next leg; staging holds the whole payload without chunk pipelining. |
| `CopyBatch` | A batch names one valid memory placement and simultaneous phase; independent chains must have no write conflicts. |
| `CopyBatch.identity_hash` | Input identity includes full placement, phase, complete chain order and all requested paths. |

<!-- model-fields:end -->
