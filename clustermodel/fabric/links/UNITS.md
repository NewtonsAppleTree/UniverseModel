# links：单向链路与序列化服务

实现：[model.py](model.py)。LinkParams 是有校验的冻结参数，LinkEstimate 是不可变查询结果，estimate_link 可独立调用。一个Link对应一个有向物理通道；全双工反向另建通道，半双工/共享PHY用显式共享约束引用。NIC队列仍归systemmodel；能力与证据见 [STATUS](../../../docs/STATUS.md)。

## 公式与范围

raw_line 分支要求完整给出聚合线路速率R[bit/s]、编码效率η∈(0,1]、单包最大payload M、头h/尾t和帧对齐a[B]。它禁止同时给payload带宽。`n=ceil(D/M)`，`W=Σ_j a·ceil((d_j+h+t)/a)`，`C=(R/8)·η [B/s]`。wire_bytes是包含头尾/填充的PHY编码前帧字节；service_bytes=W，不再扣一次包效率。frame_format_id由分包/头尾/对齐的版本化内容哈希生成；速率或编码效率变化不改变帧表示。

effective_payload 分支只接受已经包含开销的payload_bandwidth_Bps；`service_bytes=D`，不再给原始线路或分包字段。非空消息的packet_count/wire_bytes未知，以None和原因表示，不能从有效带宽反推。

非空消息的单链路估计 `T=startup_s+propagation_s+service_bytes/C`。startup不含软件launch；不含NIC服务、共享资源排队、远端内存可见或多跳流水。profile的最小/最大消息范围显式检查；per-packet M和whole-message范围不同。D=0是无数据工作，所有计数/时间为0，不代表控制包或同步操作。

实现按完整包数量与尾包用O(1)个聚合量计算，不分配逐包对象。字节和包数使用精确整数；浮点服务率、固定延迟和计算结果必须有限，派生容量下溢或时间溢出直接拒绝。参数声明kind区分模型容量上限和条件有效服务率；实测平均吞吐不自动证明物理上界。

## 调用、敏感性和验证

LinkParams校验 → estimate_link(params, payload_bytes) → LinkEstimate；配置、输入与派生量分开，无动态状态。计数拒绝bool/非整数，tuple/list被复制为不可变序列，未知/混合速率分支失败。字段表由代码自动维护。

D小时对头尾、对齐和启动敏感，D大时对服务率敏感；实际信用窗口或供数不足时不能据此推断完成时间。多跳不机械叠加整个消息的序列化时间。

[独立测试](../../../tests/clustermodel/test_links.py)覆盖200Gbit/s→25GB/s、1025B尾包的1152B帧量、编码只扣一次、有效payload未知、零工作、profile范围、数值溢出/下溢、大消息和敏感性。依据[参数清单](../../../ARCHITECTURE_PARAMETERS.md)第6节；[C1示例](../../docs/c1_usage.md)采用显式手工假设，没有物理网络校准。

<!-- model-fields:start -->

### [model.py](model.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `LinkParams` | `link_id` | `str` | 1（标识/枚举） | Unique directed physical channel identity; reverse direction is another link. |
| `LinkParams` | `src_port_id` | `str` | 1（标识/枚举） | Source port identity; graph construction validates ownership and attachment. |
| `LinkParams` | `dst_port_id` | `str` | 1（标识/枚举） | Destination port identity; cannot equal src_port_id. |
| `LinkParams` | `rate_basis` | `Literal['raw_line', 'effective_payload']` | —（结构/对象） | Mutually exclusive rate/profile interpretation. |
| `LinkParams` | `startup_s` | `float` | s | Per-message isolated startup latency [s]; nonnegative, excludes software launch. |
| `LinkParams` | `propagation_s` | `float` | s | One-way propagation latency [s]; nonnegative, no queue delay. |
| `LinkParams` | `capacity_kind` | `Literal['declared_ceiling', 'effective_service']` | —（结构/对象） | Declared model ceiling or fitted service rate. |
| `LinkParams` | `source_ref` | `str` | 1（标识/枚举） | Explicit source/profile version or manual assumption identity. |
| `LinkParams` | `coverage` | `tuple[str, ...]` | 1（标识/枚举） | Immutable profile applicability and omitted mechanisms. |
| `LinkParams` | `line_rate_bps` | `float \| None` | bit/s | Raw branch: aggregated line rate R [bit/s], positive. |
| `LinkParams` | `coding_efficiency` | `float \| None` | —（结构/对象） | Raw branch: remaining PHY efficiency eta in (0,1]. |
| `LinkParams` | `max_payload_bytes` | `int \| None` | B | Raw branch: maximum per-packet payload M [B], positive integer. |
| `LinkParams` | `header_bytes` | `int \| None` | B/packet | Raw branch: header h [B/packet], nonnegative integer. |
| `LinkParams` | `trailer_bytes` | `int \| None` | B/packet | Raw branch: trailer t [B/packet], nonnegative integer. |
| `LinkParams` | `alignment_bytes` | `int \| None` | B | Raw branch: entire frame alignment a [B], positive integer. |
| `LinkParams` | `payload_bandwidth_Bps` | `float \| None` | B/s | Effective branch: already adjusted payload capacity [B/s]. |
| `LinkParams` | `profile_min_payload_bytes` | `int` | B | Smallest supported nonempty message [B]; zero is a no-op query. |
| `LinkParams` | `profile_max_payload_bytes` | `int \| None` | B | Largest supported message [B]; None declares no upper limit. |
| `LinkParams` | `shared_constraint_ids` | `tuple[str, ...]` | 1（标识/枚举） | Additional fabric-owned resources, e.g. half-duplex medium. |
| `LinkParams` | `schema_version` | `Literal['network-link/v1']` | —（结构/对象） | Link/profile accounting semantics. |
| `LinkParams` | `service_capacity_Bps` | `float` | B/s | 只读派生属性；Capacity C [B/s] uses pre-PHY frame bytes for raw profiles and payload bytes for effective profiles. |
| `LinkParams` | `service_byte_basis` | `str` | 1（标识/枚举） | 只读派生属性；Bind service quantities to their accounting representation, preventing wire/payload mixing. |
| `LinkParams` | `frame_format_id` | `str \| None` | 1（标识/枚举） | 只读派生属性；Frame identity depends on packetization and padding, not line speed or PHY coding efficiency. |
| `LinkEstimate` | `payload_bytes` | `int` | B | Original logical message size D [B]; zero means no work. |
| `LinkEstimate` | `packet_count` | `int \| None` | —（结构/对象） | Number of frames; unknown for nonempty effective-payload profiles. |
| `LinkEstimate` | `wire_bytes` | `int \| None` | B | Pre-PHY frame bytes W [B], including headers/trailers/padding; may be unknown. |
| `LinkEstimate` | `wire_unknown_reason` | `str \| None` | 1（标识/枚举） | Explanation when frame count/wire bytes cannot be derived. |
| `LinkEstimate` | `service_bytes` | `int` | B | Resource service demand [B] in service_byte_basis. |
| `LinkEstimate` | `service_byte_basis` | `str` | 1（标识/枚举） | Frame or payload representation, matching the denominator capacity. |
| `LinkEstimate` | `serialization_s` | `float` | s | Isolated service duration Q/C [s]; excludes startup/propagation. |
| `LinkEstimate` | `isolated_time_s` | `float` | s | Startup + propagation + serialization [s] for D>0; zero for no work. |
| `LinkEstimate` | `empty` | `bool` | 1（布尔） | 只读派生属性；An empty arithmetic query is not a zero-payload control packet or a synchronization operation. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `LinkParams` | A directed link selects exactly one rate representation; physical assumptions are always explicit. |
| `LinkParams.service_capacity_Bps` | Capacity C [B/s] uses pre-PHY frame bytes for raw profiles and payload bytes for effective profiles. |
| `LinkParams.service_byte_basis` | Bind service quantities to their accounting representation, preventing wire/payload mixing. |
| `LinkParams.frame_format_id` | Frame identity depends on packetization and padding, not line speed or PHY coding efficiency. |
| `LinkEstimate` | Immutable query result separates actual service work from unknown framing and isolated latency. |
| `LinkEstimate.empty` | An empty arithmetic query is not a zero-payload control packet or a synchronization operation. |
| `estimate_link(params: LinkParams, payload_bytes: int)` | Estimate one isolated message in O(1) packet-count space; T=L_start+L_prop+Q/C, never a queue simulation. |

<!-- model-fields:end -->
