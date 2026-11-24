# nic：显式缓冲、供数/接收与集群端点

研究节点内存到网卡的路径、瞬时缓冲和共享资源如何限制通信。复用 S2 物理预留及 S3 DMA/PCIe 服务；NIC 只引用现有资源、buffer backing、方向容量与权限。当前实现**显式完整缓冲的静态供数/接收台架**，不拥有数据内容、队列、链路执行或一致性状态。

| Unit / [model.py](model.py) | 专业行为与边界 |
| --- | --- |
| NicPort | 引用已建模NIC设备、其唯一缓冲backing、NetworkEndpointSpec与rdma_write_enabled |
| NicSystem | 同一DmaSystem与完整NIC端点/方向预算；校验真实资源、归属、重复/父子计量 |
| NicRegistration | endpoint/allocation、对象内字节区间、逻辑生命周期及read/write权限 |
| NicFlow / NicBatch | flow与CopyChain一一绑定；所有同时流量使用同一CopyBatch，保留跨流hazard检查 |
| analyze_nic | 可独立调用；输出NicAnalysis及每流应用/缓冲身份，saved_paths可无寻路回读 |

## 参数、公式和计量边界

endpoint的node_id必须等于拓扑scope；external port不能冒充节点内部PCIe端口。buffer_backing_ids必须来自NIC自身的资源子树，多个NIC不能重复占有同一buffer。TX链的最后目标为NIC buffer；RX链的第一源为NIC buffer。应用端与buffer必须属于同一MemoryObject、相同对象内偏移，长度来自CopyChain的payload_bytes [B]。真实数据复制、源可用性和接收完成并未执行。

注册区间为 `[offset_bytes,offset_bytes+length_bytes)` [B]，不能暴露分配padding；`[begin_phase,end_phase)`为非空逻辑阶段，不能超过allocation的生命周期。rdma_write同时需要显式启用、精确endpoint/allocation、覆盖访问区间及活跃phase，TX需read、RX需write权限。只声明一个registration_id或协议名不授予能力。普通send不能携带RDMA grant冒充其语义。未建模实际rkey、远端认证、QP、重试或ordering。

constraints为唯一node-owned、payload口径的declared_ceiling [B/s]；tx/rx可以显式共享一个预算。它们引用拓扑中的实际资源，与DMA engine/PCIe wire/root service互斥。节点内分析输出DMA工作，集群接入后**由cluster一次性计算NIC方向工作**，不再在节点时间上附加同一NIC收费。多rank或端口共享一个service时总量相加，容量仍一份。物理有限缓冲容量独立于方向带宽。

顺序：MemorySystem/PcieProfile/engine/service → DmaSystem → NicSystem → 显式buffer/application MemoryPlan → CopyBatch/NicBatch → analyze_nic。调用不依赖cluster、配置或AI；跨模块比较在evaluation的system_network.py进行。export使用标准库NetworkEndpointSpec/BandwidthConstraint，systemmodel不反向导入clustermodel。

## 敏感参数、来源和证据

敏感量为payload、同时流量数、共享root与NIC容量、缓冲空间、DMA启动及注册/路径条件。`manual:buffered-nic-fixture/v1`例子使用每node 1 GB/s共享root、TX/RX各2 GB/s NIC及4 GB/s fabric声明；均为人工必要服务上限，没有设备标定。512 B单消息需1120条线路累计PCIe frame B、root下界512 ns；两路各512 B合计root下界1024 ns，NIC下界512 ns。

模型测试检查手算、多个设备共享NIC、显式RDMA、权限/区间/生命周期、同节点路径、重复预算与带宽敏感性；12例为4成功、8预期失败。完整输入/记录回读与边界见[S5指南](../../docs/network_usage.md)。无packet queue、远端内存可见性、零拷贝/隐式读完成、实际并发调度或完整性能/能耗结论。

<!-- model-fields:start -->

### [model.py](model.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `NicPort` | `resource_id` | `str` | 1（标识/枚举） | Existing modeled NIC device, owning the buffer subtree. |
| `NicPort` | `endpoint` | `NetworkEndpointSpec` | —（结构/对象） | Standard-library cluster boundary; capacities are referenced, never cloned per rank. |
| `NicPort` | `buffer_backing_ids` | `tuple[str, ...]` | resource ID | Explicit finite transmit/receive buffers under this NIC [resource ID]. |
| `NicPort` | `rdma_write_enabled` | `bool` | 1（布尔） | Declared remote-write capability; registration/path checks are still mandatory. |
| `NicPort` | `source_ref` | `str` | 1（标识/枚举） | Buffered architecture/capability provenance; no implicit coherent access. |
| `NicSystem` | `dma` | `DmaSystem` | —（结构/对象） | Local posted-write supply/drain service plus finite memory/topology. |
| `NicSystem` | `ports` | `tuple[NicPort, ...]` | —（结构/对象） | Unique endpoint, device and external port inventory. |
| `NicSystem` | `constraints` | `tuple[BandwidthConstraint, ...]` | 1（标识/枚举） | NIC TX/RX payload ceilings; each actual resource defined exactly once. |
| `NicSystem` | `source_ref` | `str` | 1（标识/枚举） | Whole assembly version/assumptions. |
| `NicSystem` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Include every local and external declaration in immutable provenance. |
| `NicRegistration` | `registration_id` | `str` | 1（标识/枚举） | Unique registration handle; no executable key or implicit remote authentication. |
| `NicRegistration` | `endpoint_id` | `str` | 1（标识/枚举） | NIC endpoint permitted to access this allocation. |
| `NicRegistration` | `allocation_id` | `str` | 1（标识/枚举） | Exact application allocation in the batch placement, not a replaceable address alias. |
| `NicRegistration` | `offset_bytes` | `int` | B | Object-relative first registered byte [B], nonnegative. |
| `NicRegistration` | `length_bytes` | `int` | B | Positive registered extent [B], within useful object data. |
| `NicRegistration` | `begin_phase` | `int` | —（结构/对象） | Inclusive registration lifetime phase, not target time. |
| `NicRegistration` | `end_phase` | `int` | —（结构/对象） | Exclusive lifetime phase, bounded by allocation lifetime. |
| `NicRegistration` | `operations` | `tuple[Literal['read', 'write'], ...]` | —（结构/对象） | Local source read or destination write grant. |
| `NicRegistration` | `source_ref` | `str` | 1（标识/枚举） | Registration/permission assumption provenance. |
| `NicFlow` | `flow_id` | `str` | 1（标识/枚举） | Unique flow identity; upper composition maps it to a message and application rank. |
| `NicFlow` | `endpoint_id` | `str` | 1（标识/枚举） | Installed NIC endpoint. |
| `NicFlow` | `chain_id` | `str` | 1（标识/枚举） | Exactly one supply/drain CopyChain, counted once in the local batch. |
| `NicFlow` | `direction` | `Literal['tx', 'rx']` | —（结构/对象） | TX finishes in NIC buffer; RX begins there. |
| `NicFlow` | `mode` | `Literal['send', 'rdma_write']` | —（结构/对象） | Declared message semantic; RDMA requires explicit registration/capability. |
| `NicFlow` | `registration_id` | `str \| None` | 1（标识/枚举） | Mandatory for rdma_write, absent for ordinary buffered send. |
| `NicBatch` | `copies` | `CopyBatch` | —（结构/对象） | Explicit application, staging and NIC buffer allocations; no hidden receive capacity. |
| `NicBatch` | `flows` | `tuple[NicFlow, ...]` | —（结构/对象） | One-to-one chain bindings. |
| `NicBatch` | `registrations` | `tuple[NicRegistration, ...]` | 1（标识/枚举） | Explicit immutable RDMA grants. |
| `NicFlowAnalysis` | `flow_id` | `str` | 1（标识/枚举） | Original immutable flow identity. |
| `NicFlowAnalysis` | `endpoint_id` | `str` | 1（标识/枚举） | Selected network boundary. |
| `NicFlowAnalysis` | `direction` | `str` | 1（标识/枚举） | TX or RX. |
| `NicFlowAnalysis` | `payload_bytes` | `int` | B | Exact useful application bytes [B]. |
| `NicFlowAnalysis` | `object_id` | `str` | 1（标识/枚举） | Logical content identity from the allocation. |
| `NicFlowAnalysis` | `content_version` | `str` | 1（标识/枚举） | MemoryObject source reference; declaration, not a measured content checksum. |
| `NicFlowAnalysis` | `object_offset_bytes` | `int` | B | Offset within the logical application object [B]. |
| `NicFlowAnalysis` | `application_allocation_id` | `str` | 1（标识/枚举） | Registered/read/written application copy. |
| `NicFlowAnalysis` | `buffer_allocation_id` | `str` | 1（标识/枚举） | Explicit finite NIC staging copy. |
| `NicAnalysis` | `system_identity` | `str` | 1（标识/枚举） | Full sourced NIC/local assembly hash. |
| `NicAnalysis` | `dma` | `TransferAnalysis` | —（结构/对象） | Local DMA/PCIe shared work only; excludes exported NIC wire capacities. |
| `NicAnalysis` | `flows` | `tuple[NicFlowAnalysis, ...]` | —（结构/对象） | Exact validated application/buffer bindings. |
| `NicAnalysis` | `unknown_costs` | `tuple[str, ...]` | 1（标识/枚举） | Fabric execution, NIC scheduling/visibility and physical costs remain unmodeled. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `NicPort` | A network endpoint references one NIC and explicit packet staging storage; local DMA and fabric service remain separate. |
| `NicSystem` | Exported NIC payload ceilings are disjoint from local DMA/PCIe work and owned by the actual node. |
| `NicSystem.identity_hash` | Include every local and external declaration in immutable provenance. |
| `NicRegistration` | Registration authorizes one application's physical allocation subrange at explicit logical phases. |
| `NicFlow` | One logical flow binds exactly one local whole-buffer DMA chain to one fabric-facing direction. |
| `NicBatch` | Simultaneous flows share one placement and DMA batch so shared work and cross-flow hazards cannot be hidden. |
| `NicFlowAnalysis` | Supply/drain evidence retains exact application data identity while leaving fabric completion and visibility unknown. |
| `NicAnalysis` | Local service and exported NIC service are separate ledgers; upper composition must charge each exactly once. |
| `analyze_nic(system: NicSystem, batch: NicBatch, *, saved_paths: tuple[SystemPath, ...] \| None=None)` | Resolve all shared local work once, then validate buffer ownership, data continuity and explicit RDMA grants. |

<!-- model-fields:end -->
