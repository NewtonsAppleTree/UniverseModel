# memory：物理预留、地址视图与 NUMA 放置

本目录服务 AI 权重、激活、KV 等对象的**静态驻留可行性与放置比较**，不绑定任务格式或特定器件。引用 `NodeSpec` 的唯一资源清单；只拥有容量、预留、映射和 NUMA 声明，不拥有芯片内部数据、真实内存内容或执行状态。S2 是精确整数静态分析，不是访存执行器、分配算法或操作系统仿真。

| Unit / 实现 | 输入与独立行为 | 输出 / 覆盖 |
| --- | --- | --- |
| MemorySystem / [model.py](model.py) | 节点、MemoryBacking、NumaDomain；校验归属、实际 ingress、互斥容量与精确成员 | 含来源的 immutable identity |
| MemoryPlan / model.py | MemoryObject 逻辑需求、MemoryAllocation 物理副本、MemoryRegion 地址视图 | 不可变候选；跨对象不可行条件保留到分析阶段 |
| analyze_placement / [placement.py](placement.py) | 全部预留和生命周期；校验物理/地址并发区间 | PlacementAnalysis、每 backing 的 BackingUsage |
| resolve_span / [access.py](access.py) | 完整放置 + MemoryAccessRequest | ResolvedSpan；只解映射、不检查源可达 |
| analyze_access / access.py | 放置、读写请求、显式或搜索路径 | MemoryAccessAnalysis：容量、物理区间、实际请求路径与 locality |
| validate_access / access.py | 同一声明与保存的 link_ids | 不搜索路径的静态重分析；不执行目标系统 |
| TieredMemorySystem / [tiering.py](tiering.py) | 将所有物理backing唯一划分为MemoryTier | analyze_residency汇总同一phase的容量/存活副本/粒度padding |
| TierMigration / tiering.py | before/during/after、源/目标copy和move/copy | analyze_migration验证完整对象、源目标共存、其他资源不变及额外预留 |
| CxlCopyRequest / [migration.py](migration.py) | 精确CXL请求及host-local端点 | analyze_cxl_migration / validate_cxl_migration，时间未知 |
| analyze_dma_migration / migration.py | 同一during快照与一条完整对象S3 CopyChain | MigrationEvidence含兼容DMA工作/条件下界；validate_dma_migration回读保存路径 |

## 参数、单位与公式

代码行尾是字段的维护定义。主要输入/派生关系：

| 量 | 含义、范围、来源 / 关系 |
| --- | --- |
| resource_id / backing_id | 同一物理资源；必须有 model_id。禁止同时选父摘要与内部子资源 |
| capacity_bytes, allocation_granule_bytes | 正整数 B；容量是粒度的整数倍；来源由 backing.source_ref 明示 |
| access_port_ids | backing 自身或祖先拥有的地址 ingress；共享控制器只引用物理 backing，不重复容量 |
| size_bytes | 逻辑对象正整数 B；来源来自任务或显式需求假设，本包不推断压缩、稀疏率或内容 |
| offset_bytes | 物理起点 B，非负且粒度对齐 |
| reserved | `ceil(size_bytes / allocation_granule_bytes) × allocation_granule_bytes` B，以整数运算实现 |
| begin_phase, end_phase | 非负逻辑阶段；`[begin_phase,end_phase)` 非空，不是 cycle / second，也不证明实际调度可实现 |
| base_address, object_offset_bytes, length_bytes | 地址域起点、对象内偏移、视图长度，单位 B；只暴露对象数据范围，禁止暴露 padding |
| permissions | 非空 read/write 子集，同时受 ingress 与完整请求路径限制 |
| address, phase, operation | 查询落在视图及 allocation 有效期；物理偏移=`offset_bytes + object_offset_bytes + address - base_address` |
| numa_id, member_ids | 显式精确资源成员，无祖先/后代继承；同标签 local、不同 remote、任一未分组 unknown |
| peak_reserved_bytes | 同一 backing 在任一逻辑阶段的最大预留 B；peak_phase 为最早达到峰值的阶段 |
| logical_bytes_at_peak, padding_bytes_at_peak | 在同一个 reserved 峰值时刻计量；二者之和等于 peak_reserved_bytes |
| memory_identity, plan_identity | 绑定容量/拓扑/NUMA/来源及全部候选对象/映射；改变声明必须显式生成新 plan 绑定 |

同一 allocation 的多个 region 是地址别名，只收费一次；同一对象的多个 allocation 是独立副本，分别预留。地址视图继承 allocation 生命周期；同一 domain 中并发视图不能重叠，跨 domain 的相同数值地址独立。若需要同一副本的别名，使用不同不重叠的地址范围。allocation 可以没有视图；每个已声明对象至少有一次 allocation；完全空任务合法。

按逻辑阶段做事件扫描，同阶段先释放再预留；每个 backing 的物理区间和每个 domain 的地址区间分别检查。不同 backing 的各自峰值**不能相加当作同时节点峰值**。未使用 backing 输出零实际占用和 `peak_phase=None`；这不是未知物理成本填零。每份 object/allocation/region 清单上限 10,000 条是宿主运行保护，不是硬件限制；使用排序活跃区间，最坏列表维护为 O(n²)，内存 O(n)，不枚举字节或阶段空间。

## 调用、敏感参数与证据

顺序：NodeSpec → MemorySystem → MemoryPlan → analyze_placement；需要查询时再提供 MemoryAccessRequest → resolve_span / analyze_access。配置与实验比较在 evaluation 层，专业模型可独立调用，不依赖配置、记录或 workload。输出无动态状态变更。

关键敏感量：对象大小、granule、物理偏移、生命周期重叠决定容量；alias/copy 身份决定是否重复预留；地址宽度、视图范围/权限决定映射；显式 forwarding 与逐段权限决定可达；NUMA 精确成员只改变位置分类。NUMA 距离、缓存、一致性、page table/TLB/IOMMU、实际迁移执行、读返回路径、完整请求服务与拥塞均未覆盖。read 路径仅为访问请求方向；可达不证明读数据已返回或副本内容一致。

验证采用 320 B 手算、120 组逐字节物理占用 oracle、80 组地址区间 oracle、域/生命周期边界和 15 个成功/失败实验。1024 B 容量、64 B 粒度来自 `manual:synthetic-memory-fixture/v1`，用于正确性反例，不是 DRAM/NUMA 实测。目标时延和能量由实验层保存为 `None + unknown_reason`。使用指南、完整清单与回读语义见[内存指南](../docs/memory_usage.md)，整体状态见[STATUS](../../docs/STATUS.md)。

## S4 分层与迁移参数

MemoryTier只引用backing_ids，精确分区避免重复容量；access_kind为local/cxl.mem/dma_only策略，不授予访问或速度。TierUsage在同一个phase求和：capacity_bytes=各backing容量之和；reserved_bytes=存活allocation按各自粒度取整之和；logical_bytes=存活物理副本的对象大小之和；padding为两者差。容量不等于host可达容量。

TierMigration三状态使用相同phase/对象全集，during=before+恰好一份目标副本，copy的after=during，move的after仅移除源allocation及其视图。源与目标在复制期间都存活，additional_reserved_bytes=during−before。新目标可以有地址视图；旧视图与无关分配不可变。after只是复制完成后的条件预览，无状态发布。

敏感量为对象大小、目的分配粒度、剩余连续空间、同时存活副本、启用模式/路径、host所有权与传输方法。CXL读提升、整行写迁出；原生时间界为None，兼容DMA保留S3必要下界；二者均无完整能耗。边界/来源、17项模型测试、100组独立行参考及15例见[S4指南](../docs/tiering_usage.md)。

<!-- model-fields:start -->

### [access.py](access.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `MemoryAccessRequest` | `source_port_id` | `str` | 1（标识/枚举） | Initiator address-terminal egress. |
| `MemoryAccessRequest` | `region_id` | `str` | 1（标识/枚举） | Declared address view to resolve. |
| `MemoryAccessRequest` | `address` | `int` | B | First byte in the view's address domain [B]. |
| `MemoryAccessRequest` | `length_bytes` | `int` | B | Requested positive contiguous extent [B]. |
| `MemoryAccessRequest` | `phase` | `int` | —（结构/对象） | Logical liveness phase, nonnegative; not cycle or second. |
| `MemoryAccessRequest` | `operation` | `Literal['read', 'write']` | —（结构/对象） | Permission checked on view and complete request path. |
| `MemoryAccessRequest` | `link_ids` | `tuple[str, ...] \| None` | 1（标识/枚举） | Explicit path, or deterministic search when absent. |
| `MemoryAccessRequest` | `max_hops` | `int` | link | Host search/path guard [link], not a timing budget. |
| `ResolvedSpan` | `memory_identity` | `str` | 1（标识/枚举） | Full MemorySystem SHA256 even for independent resolution without a route. |
| `ResolvedSpan` | `plan_identity` | `str` | 1（标识/枚举） | Exact object/allocation/view declaration SHA256. |
| `ResolvedSpan` | `region_id` | `str` | 1（标识/枚举） | Selected address view. |
| `ResolvedSpan` | `allocation_id` | `str` | 1（标识/枚举） | One physical copy, shared by aliases. |
| `ResolvedSpan` | `object_id` | `str` | 1（标识/枚举） | Logical object identity. |
| `ResolvedSpan` | `backing_id` | `str` | 1（标识/枚举） | Physical storage identity. |
| `ResolvedSpan` | `access_port_id` | `str` | 1（标识/枚举） | Required target ingress. |
| `ResolvedSpan` | `domain_id` | `str` | 1（标识/枚举） | Address namespace of this mapping. |
| `ResolvedSpan` | `address` | `int` | B | Requested domain address [B]. |
| `ResolvedSpan` | `length_bytes` | `int` | B | Validated requested extent [B]. |
| `ResolvedSpan` | `phase` | `int` | —（结构/对象） | Checked logical lifetime phase. |
| `ResolvedSpan` | `operation` | `Literal['read', 'write']` | —（结构/对象） | Checked view permission. |
| `ResolvedSpan` | `physical_offset_bytes` | `int` | B | allocation.offset + view.object_offset + address - view.base [B]. |
| `MemoryAccessAnalysis` | `placement` | `PlacementAnalysis` | —（结构/对象） | Capacity/address feasibility tied to hardware and plan identities. |
| `MemoryAccessAnalysis` | `span` | `ResolvedSpan` | —（结构/对象） | Exact resolved physical interval and request semantics. |
| `MemoryAccessAnalysis` | `path` | `SystemPath` | —（结构/对象） | Actual directed request path and shared resource references. |
| `MemoryAccessAnalysis` | `locality` | `Literal['local', 'remote', 'unknown']` | —（结构/对象） | Equal/different explicit NUMA labels, or missing membership. |
| `MemoryAccessAnalysis` | `initiator_numa_id` | `str \| None` | 1（标识/枚举） | Exact source owner membership; no inheritance. |
| `MemoryAccessAnalysis` | `backing_numa_id` | `str \| None` | 1（标识/枚举） | Exact physical backing membership; no inheritance. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `MemoryAccessRequest` | A read/write query binds a live address view and an explicit initiator; no implicit local bypass exists. |
| `ResolvedSpan` | Resolution identifies backing bytes; it neither reads data nor simulates page tables, TLBs or IOMMUs. |
| `MemoryAccessAnalysis` | Static access evidence includes capacity, mapping and path; locality provides no latency/energy value. |
| `resolve_span(memory: MemorySystem, plan: MemoryPlan, request: MemoryAccessRequest)` | Independently validate a placement and map one address span; source reachability is deliberately checked separately. |
| `analyze_access(memory: MemorySystem, plan: MemoryPlan, request: MemoryAccessRequest)` | Analyze placement, resolve bytes and search/check the request path; read response/data service remains unmodeled. |
| `validate_access(memory: MemorySystem, plan: MemoryPlan, request: MemoryAccessRequest, saved_link_ids: tuple[str, ...])` | Reanalyze saved static declarations and validate their recorded route, without path search or target execution. |

### [migration.py](migration.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `CxlCopyRequest` | `request` | `CxlAccessRequest` | —（结构/对象） | Read for remote-to-local promotion; write for local-to-remote demotion. |
| `CxlCopyRequest` | `local_region_id` | `str` | 1（标识/枚举） | Local destination for read, or local source for write. |
| `CxlCopyRequest` | `local_address` | `int` | B | First host-local useful byte in that view's address domain [B]. |
| `MigrationEvidence` | `transition` | `MigrationAnalysis` | —（结构/对象） | Before/overlap/after feasibility and exact full-object demand. |
| `MigrationEvidence` | `method` | `Literal['host-cxl.mem', 'dma']` | —（结构/对象） | Actual modeled data-movement semantics; no PCIe/CXL framing substitution. |
| `MigrationEvidence` | `cxl_access` | `CxlAccessAnalysis \| None` | —（结构/对象） | Native CXL line-access evidence for a host copy, otherwise None. |
| `MigrationEvidence` | `dma` | `TransferAnalysis \| None` | —（结构/对象） | Existing compatible S3 copy-chain evidence, otherwise None. |
| `MigrationEvidence` | `local_span` | `ResolvedSpan \| None` | —（结构/对象） | Resolved host-local endpoint for native CXL copy. |
| `MigrationEvidence` | `transport_data_bytes` | `int` | B | Native line data or sum of useful per-leg DMA data [B]; method-specific, not a shared frame metric. |
| `MigrationEvidence` | `known_service_lower_bound_s` | `float \| None` | s | S3 partial bound [s], or unknown for uncalibrated native CXL/host service. |
| `MigrationEvidence` | `unknown_costs` | `tuple[str, ...]` | 1（标识/枚举） | Unmodeled service, coherence/publication and physical-cost obligations. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `CxlCopyRequest` | A host copy pairs one remote CXL.mem request with an explicitly named host-local memory view. |
| `MigrationEvidence` | Successful static transport checks do not execute the copy or authorize publication of the proposed after snapshot. |
| `analyze_cxl_migration(system: TieredMemorySystem, migration: TierMigration, phase: int, cxl: CxlMemorySystem, copy: CxlCopyRequest)` | Independently analyze a complete object promotion/demotion through native CXL.mem and host-local memory. |
| `validate_cxl_migration(system: TieredMemorySystem, migration: TierMigration, phase: int, cxl: CxlMemorySystem, copy: CxlCopyRequest, saved_path: SystemPath)` | Replay the saved CXL path and static migration declaration without performing a new route search. |
| `analyze_dma_migration(system: TieredMemorySystem, migration: TierMigration, phase: int, dma: DmaSystem, batch: CopyBatch)` | Reuse S3's explicit transfer service only after checking the complete before/overlap/after migration contract. |
| `validate_dma_migration(system: TieredMemorySystem, migration: TierMigration, phase: int, dma: DmaSystem, batch: CopyBatch, saved_paths: tuple[SystemPath, ...])` | Reanalyze compatible saved DMA routes and work without searching or executing the transfer producer. |

### [model.py](model.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `MemoryBacking` | `resource_id` | `str` | 1（标识/枚举） | Unique modeled storage instance in the node's resource inventory. |
| `MemoryBacking` | `capacity_bytes` | `int` | B | Allocatable physical storage [B], positive, excluding any unmodeled metadata. |
| `MemoryBacking` | `allocation_granule_bytes` | `int` | B | Positive reservation granule [B]; capacity and offsets are multiples. |
| `MemoryBacking` | `access_port_ids` | `tuple[str, ...]` | 1（标识/枚举） | Explicit address-terminal ingress ports serving this backing. |
| `MemoryBacking` | `source_ref` | `str` | 1（标识/枚举） | Capacity/granule/attachment provenance or manual modeling assumption. |
| `NumaDomain` | `numa_id` | `str` | 1（标识/枚举） | Node-local locality label; not an implicit latency or distance value. |
| `NumaDomain` | `member_ids` | `tuple[str, ...]` | 1（标识/枚举） | Exact resource instances assigned to this group, without descendant inheritance. |
| `NumaDomain` | `source_ref` | `str` | 1（标识/枚举） | Locality placement evidence or explicit assumption. |
| `MemorySystem` | `node` | `NodeSpec` | —（结构/对象） | Authoritative node topology and device ownership. |
| `MemorySystem` | `backings` | `tuple[MemoryBacking, ...]` | —（结构/对象） | Unique finite storage resources, not views or logical memory devices. |
| `MemorySystem` | `numa_domains` | `tuple[NumaDomain, ...]` | —（结构/对象） | Optional exact membership; absent members have unknown locality. |
| `MemorySystem` | `source_ref` | `str` | 1（标识/枚举） | Whole-memory-system provenance/version. |
| `MemorySystem` | `coverage` | `tuple[str, ...]` | 1（标识/枚举） | Explicit storage/access scope and omitted mechanisms. |
| `MemorySystem` | `schema_version` | `Literal['system-memory/v1']` | —（结构/对象） | Static capacity, mapping and locality only. |
| `MemorySystem` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Include all capacity, topology, NUMA placement and provenance in the physical-system identity. |
| `MemoryObject` | `object_id` | `str` | 1（标识/枚举） | Logical data identity; multiple allocations can hold separate copies. |
| `MemoryObject` | `size_bytes` | `int` | B | Logical extent [B], positive, excluding allocation padding. |
| `MemoryObject` | `source_ref` | `str` | 1（标识/枚举） | Origin of this explicit storage demand. |
| `MemoryAllocation` | `allocation_id` | `str` | 1（标识/枚举） | Unique storage-copy identity; aliases must refer to this same ID. |
| `MemoryAllocation` | `object_id` | `str` | 1（标识/枚举） | Existing complete logical object to reserve. |
| `MemoryAllocation` | `backing_id` | `str` | 1（标识/枚举） | Existing physical storage resource. |
| `MemoryAllocation` | `offset_bytes` | `int` | B | Physical start [B], aligned to the backing granule. |
| `MemoryAllocation` | `begin_phase` | `int` | phase | Inclusive logical liveness boundary [phase], nonnegative; not target time. |
| `MemoryAllocation` | `end_phase` | `int` | phase | Exclusive boundary [phase], strictly after begin_phase. |
| `MemoryRegion` | `region_id` | `str` | 1（标识/枚举） | Unique address-view identity, not another allocation. |
| `MemoryRegion` | `allocation_id` | `str` | 1（标识/枚举） | Physical allocation this view aliases. |
| `MemoryRegion` | `access_port_id` | `str` | 1（标识/枚举） | One ingress from the backing's declared access ports; fixes the address domain. |
| `MemoryRegion` | `base_address` | `int` | B | Start in that port's byte-address domain [B]. |
| `MemoryRegion` | `object_offset_bytes` | `int` | B | First exposed byte within the logical object [B]. |
| `MemoryRegion` | `length_bytes` | `int` | B | Exposed logical bytes [B], positive; allocation padding is inaccessible. |
| `MemoryRegion` | `permissions` | `tuple[Literal['read', 'write'], ...]` | —（结构/对象） | Explicit address-view permissions; also limited by the port/path. |
| `MemoryPlan` | `memory_identity` | `str` | 1（标识/枚举） | Complete MemorySystem SHA256; stale hardware/NUMA bindings are rejected. |
| `MemoryPlan` | `objects` | `tuple[MemoryObject, ...]` | —（结构/对象） | Logical demand roster; each object needs an allocation; empty workload is legal. |
| `MemoryPlan` | `allocations` | `tuple[MemoryAllocation, ...]` | —（结构/对象） | Explicit copies and phase intervals, including unmapped reservations. |
| `MemoryPlan` | `regions` | `tuple[MemoryRegion, ...]` | —（结构/对象） | Address aliases; unexposed reservations remain valid and consume capacity. |
| `MemoryPlan` | `source_ref` | `str` | 1（标识/枚举） | Plan provenance or fixed placement-policy declaration. |
| `MemoryPlan` | `schema_version` | `Literal['system-memory-plan/v1']` | —（结构/对象） | Static placement, no allocator/scheduler inference. |
| `MemoryPlan` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Plan identity includes actual object sizes, phases, placements, aliases, permissions and source. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `MemoryBacking` | A backing resource owns finite allocatable bytes; address aliases never duplicate this capacity. |
| `NumaDomain` | NUMA groups explicitly place initiators and backings; hierarchy or hop count does not infer locality. |
| `MemorySystem` | Static memory capacity/attachment/NUMA state refers to one immutable node; it contains no allocation or data contents. |
| `MemorySystem.identity_hash` | Include all capacity, topology, NUMA placement and provenance in the physical-system identity. |
| `MemoryObject` | An object is a logical storage demand, without allocating bytes or asserting any tensor contents. |
| `MemoryAllocation` | An allocation owns one whole object copy and reserves a rounded physical interval during declared logical phases. |
| `MemoryRegion` | An address view maps a logical subrange of one allocation; it grants only its explicitly declared operations. |
| `MemoryPlan` | A candidate plan owns demands/copies/views; cross-object infeasibility is reported during placement analysis. |
| `MemoryPlan.identity_hash` | Plan identity includes actual object sizes, phases, placements, aliases, permissions and source. |

### [placement.py](placement.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `BackingUsage` | `backing_id` | `str` | 1（标识/枚举） | Unique physical storage identity. |
| `BackingUsage` | `capacity_bytes` | `int` | B | Declared allocatable capacity [B]. |
| `BackingUsage` | `peak_reserved_bytes` | `int` | B | Maximum simultaneous rounded occupancy [B]. |
| `BackingUsage` | `peak_phase` | `int \| None` | —（结构/对象） | Earliest phase attaining a positive peak; None for an unused backing. |
| `BackingUsage` | `logical_bytes_at_peak` | `int` | B | Sum of object sizes of live copies at peak_phase [B]. |
| `BackingUsage` | `padding_bytes_at_peak` | `int` | B | peak_reserved_bytes - logical_bytes_at_peak [B]. |
| `BackingUsage` | `allocation_ids_at_peak` | `tuple[str, ...]` | 1（标识/枚举） | Exact copies contributing to that peak, sorted by identity. |
| `PlacementAnalysis` | `memory_identity` | `str` | 1（标识/枚举） | Full hardware/NUMA/source SHA256. |
| `PlacementAnalysis` | `plan_identity` | `str` | 1（标识/枚举） | Full logical demand/placement/view/source SHA256. |
| `PlacementAnalysis` | `backings` | `tuple[BackingUsage, ...]` | —（结构/对象） | All physical backings, including unused resources. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `BackingUsage` | Per-backing peaks count physical copies once and describe logical demand at the same peak phase. |
| `PlacementAnalysis` | Independent backing peaks must not be summed and presented as a simultaneous node peak. |
| `analyze_placement(memory: MemorySystem, plan: MemoryPlan)` | Validate references, rounded physical extents, lifetime reuse and address views without materializing bytes/phases. |

### [tiering.py](tiering.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `MemoryTier` | `tier_id` | `str` | 1（标识/枚举） | Unique policy group, independent of physical ownership and NUMA group. |
| `MemoryTier` | `backing_ids` | `tuple[str, ...]` | 1（标识/枚举） | Disjoint physical backing references; no copied capacity fields. |
| `MemoryTier` | `access_kind` | `Literal['local', 'cxl.mem', 'dma_only']` | —（结构/对象） | Declared access policy, checked by the appropriate transport adapter. |
| `MemoryTier` | `source_ref` | `str` | 1（标识/枚举） | Tier/policy assignment provenance, not a performance ranking. |
| `TieredMemorySystem` | `memory` | `MemorySystem` | —（结构/对象） | Unique backing/owner/capacity/source inventory. |
| `TieredMemorySystem` | `tiers` | `tuple[MemoryTier, ...]` | —（结构/对象） | Complete disjoint assignment, without inherited membership. |
| `TieredMemorySystem` | `source_ref` | `str` | 1（标识/枚举） | Whole-tier organization assumption/version. |
| `TieredMemorySystem` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Include complete backing, tier policy and provenance in the immutable tier-system identity. |
| `TierUsage` | `tier_id` | `str` | 1（标识/枚举） | Exact tier identity. |
| `TierUsage` | `capacity_bytes` | `int` | B | Sum of uniquely assigned backing capacity [B], not proof of host reachability. |
| `TierUsage` | `reserved_bytes` | `int` | B | Simultaneous rounded reservations at the queried phase [B]. |
| `TierUsage` | `logical_bytes` | `int` | B | Sum of live physical copies' useful object sizes [B]. |
| `TierUsage` | `padding_bytes` | `int` | B | reserved_bytes - logical_bytes [B]. |
| `TierUsage` | `allocation_ids` | `tuple[str, ...]` | 1（标识/枚举） | Live physical copies counted at this phase. |
| `ResidencyAnalysis` | `system_identity` | `str` | 1（标识/枚举） | Complete tier-system identity. |
| `ResidencyAnalysis` | `plan_identity` | `str` | 1（标识/枚举） | Exact object/allocation/view/source identity. |
| `ResidencyAnalysis` | `phase` | `int` | —（结构/对象） | Shared logical liveness phase, not a target timestamp. |
| `ResidencyAnalysis` | `tiers` | `tuple[TierUsage, ...]` | —（结构/对象） | Simultaneous usage of every tier, including unused capacity. |
| `TierMigration` | `before` | `MemoryPlan` | —（结构/对象） | Existing authoritative object/copy/view roster. |
| `TierMigration` | `during` | `MemoryPlan` | —（结构/对象） | Before plus one new full-object target reservation/views; source remains live. |
| `TierMigration` | `after` | `MemoryPlan` | —（结构/对象） | During, optionally removing exactly the source copy/views for a move. |
| `TierMigration` | `source_allocation_id` | `str` | 1（标识/枚举） | Existing full logical object copy to read. |
| `TierMigration` | `target_allocation_id` | `str` | 1（标识/枚举） | New whole-object copy identity; must not already exist in before. |
| `TierMigration` | `operation` | `Literal['copy', 'move']` | —（结构/对象） | Copy retains source; move retires source only after hypothetical completion. |
| `TierMigration` | `source_ref` | `str` | 1（标识/枚举） | Explicit migration policy/declaration provenance. |
| `TierMigration` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Bind all intermediate reservations, views and operation choices rather than just the final placement. |
| `MigrationAnalysis` | `migration_identity` | `str` | 1（标识/枚举） | Full before/during/after source-bound migration declaration. |
| `MigrationAnalysis` | `before` | `ResidencyAnalysis` | —（结构/对象） | Simultaneous pre-copy usage. |
| `MigrationAnalysis` | `during` | `ResidencyAnalysis` | —（结构/对象） | Source and target coexist at the same logical phase. |
| `MigrationAnalysis` | `after` | `ResidencyAnalysis` | —（结构/对象） | Candidate post-copy usage, conditional on successful external completion. |
| `MigrationAnalysis` | `object_id` | `str` | 1（标识/枚举） | Preserved logical object identity. |
| `MigrationAnalysis` | `payload_bytes` | `int` | B | One complete logical object extent [B], independent of different tier allocation granules. |
| `MigrationAnalysis` | `source_tier_id` | `str` | 1（标识/枚举） | Source backing's exact tier. |
| `MigrationAnalysis` | `target_tier_id` | `str` | 1（标识/枚举） | Destination backing's exact tier. |
| `MigrationAnalysis` | `additional_reserved_bytes` | `int` | B | During minus before simultaneous reserved storage [B]. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `MemoryTier` | A tier groups actual backings by access policy; a name/order does not imply latency, bandwidth or coherent access. |
| `TieredMemorySystem` | Every physical backing belongs to one tier; total capacities are derived from the authoritative memory inventory. |
| `TieredMemorySystem.identity_hash` | Include complete backing, tier policy and provenance in the immutable tier-system identity. |
| `TierUsage` | Capacity and simultaneous occupancy are different observations; multiple copies count even for one logical object. |
| `ResidencyAnalysis` | An observation at one shared logical phase can be summed across tiers; independent historical peaks cannot. |
| `analyze_residency(system: TieredMemorySystem, plan: MemoryPlan, phase: int)` | Validate full interval feasibility, then aggregate live copies at one phase without per-byte/time enumeration. |
| `TierMigration` | Three candidate snapshots make transient duplicate storage explicit; none is mutated or published by analysis. |
| `TierMigration.identity_hash` | Bind all intermediate reservations, views and operation choices rather than just the final placement. |
| `MigrationAnalysis` | Transition feasibility is a reservation proof under declared liveness, not data-copy completion or coherent publication. |
| `analyze_migration(system: TieredMemorySystem, migration: TierMigration, phase: int)` | Permit exactly one new target and optional source retirement; forbid hidden source drops, resized objects or unrelated changes. |

<!-- model-fields:end -->
