# cluster：装配、通信账本与条件下界

实现 [model.py](model.py)、[analysis.py](analysis.py)。ClusterSpec引用资源图、唯一rank放置与组；TrafficInput接收同时就绪的固定正长度P2PMessage及CutRequest。data_id/content_version只是来源身份，不证明数据已产生或数值正确。没有到达、动态依赖、节点内部服务接口。

analyze_traffic(cluster,traffic)：校验消息/rank/group → 固定路由 → 每hop服务量 → 源注入/目标接收/链路/共享介质/交换账本 → 资源、必要路径延迟、指定割界。输出TrafficAnalysis，字段由下表维护。

Q_r=Σq_ir [B]，T_resource=max(Q_r/C_r) [s]。NIC按其边界链路、交换按出口链路匹配frame约束，payload约束计D。每实际crossing对共享资源计一次，重复路径逐次计入；约束需求不能加入total_link_wire_bytes。LinkTraversal保留逐hop帧量或未知原因。

T_dependency=max_i(Σpropagation_s+Σforwarding_latency_s)只计必要首数据延迟；孤立startup不推断逐跳串行成本，完整消息序列化不逐跳相加。T_communication=max(T_resource,T_dependency,T_cut)是松下界。T_cut=D_cut/B_cut按实际有向crossing计量，要求统一表示，不求最优割。

输入冻结，聚合dict/set为调用局部变量，结果不可变。浮点时间溢出或正工作下溢失败。拟合有效率不自动成为物理容量上界。缺帧量/能量为None+原因，空通信界0但漏电未覆盖，完整能量仍未知。瓶颈ID只标达到资源max的正工作限制。

同节点请求unsupported_local_path；未来systemmodel摘要须替换同范围成本。不可达、错误成员、越域profile由evaluation留失败记录，不输出伪造下界。敏感量为消息矩阵、放置/路由、共享NIC/交换/上行、分包和处理延迟。

验证[四节点与反例](../../../tests/clustermodel/test_cluster.py)、[保存回读](../../../tests/integration/test_cluster_experiment.py)，手算见[指南](../../docs/foundation_usage.md)。无实际利用率、排队/完成/目标可见、collective数值、AI质量或物理校准。

## 逻辑需求总览

[traffic.py](traffic.py)提供describe_traffic，先调用validate_traffic_references，再产生TrafficDescription。它统计固定需求的rank/node/endpoint发收字节与消息数、声明group归属和稀疏node→node矩阵；安装但空闲参与者保留零行。local_payload_bytes与inter_node_payload_bytes相加等于逻辑总量，Σ矩阵量、Σ组量（包括None未分组桶）、各层Σ发送量和Σ接收量都等于同一原始需求。

组归属只采用message.group_id，组成员重叠不会再次归属。同节点/不可达需求可以先描述，描述成功不证明其路由或profile可行；analyze_traffic仍要求实际可服务路径。没有生成collective或改变工作负载。敏感量是rank放置、消息矩阵与组归属；验证见[横向模型测试](../../../tests/clustermodel/test_breadth.py)。

## 批量分析优化

analyze_traffic在一次调用内复用图索引、相同端点/策略/显式路径的Route，以及相同link_id和payload_bytes的不可变LinkEstimate。消息身份、每次实际traversal和ResourceCharge仍分别保存和累加；不同长度照常校验profile域，重复hop不会被去重。缓存不跨图或调用，大小受本次不同路径键、link/长度组合数限制；逐消息证据仍占随工作量增长的空间。

指定割从已完成的方向工作量、crossing计数和消息贡献集合归并，保留重复过割次数及字节基准，避免每个割重扫全部消息路径。公式和输出schema不变。独立帧计数、不同长度/显式路径、停用后恢复与profile替换验证见[收尾测试](../../../tests/clustermodel/test_closeout.py)，宿主基准见[完成报告](../../docs/completion.md)。

<!-- model-fields:start -->

### [analysis.py](analysis.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `LinkTraversal` | `link_id` | `str` | 1（标识/枚举） | Directed physical channel identity. |
| `LinkTraversal` | `estimate` | `LinkEstimate` | —（结构/对象） | Exact per-hop work, including framing or its explicit unknown state. |
| `ResourceCharge` | `resource_id` | `str` | 1（标识/枚举） | Unique graph service resource, either link or BandwidthConstraint. |
| `ResourceCharge` | `role` | `str` | 1（标识/枚举） | source_tx, destination_rx, link, fabric_shared, or switch_forwarding. |
| `ResourceCharge` | `service_bytes` | `int` | B | Demand q_ir [B] in the referenced resource's declared byte basis. |
| `MessageAnalysis` | `message_id` | `str` | 1（标识/枚举） | Original P2P demand identity; data/version remain in immutable input. |
| `MessageAnalysis` | `payload_bytes` | `int` | B | Original logical length D [B]. |
| `MessageAnalysis` | `route` | `Route` | —（结构/对象） | Validated selected or explicit physical path. |
| `MessageAnalysis` | `traversals` | `tuple[LinkTraversal, ...]` | —（结构/对象） | Actual ordered hop work; no implicit multicast or reduction. |
| `MessageAnalysis` | `charges` | `tuple[ResourceCharge, ...]` | —（结构/对象） | NIC/link/switch/shared work; repeated crossings charged separately. |
| `MessageAnalysis` | `dependency_time_lower_bound_s` | `float` | s | Sum of necessary propagation and switch processing delays [s]. |
| `ResourceLoad` | `resource_id` | `str` | 1（标识/枚举） | Unique service resource identity. |
| `ResourceLoad` | `owner_id` | `str` | 1（标识/枚举） | Node, switch or graph owner; directional links are graph-owned. |
| `ResourceLoad` | `category` | `str` | 1（标识/枚举） | link, nic, switch, or fabric_shared. |
| `ResourceLoad` | `byte_basis` | `str` | 1（标识/枚举） | payload or frame, matching the capacity denominator. |
| `ResourceLoad` | `frame_format_id` | `str \| None` | 1（标识/枚举） | Representation identity for frame work; None for payload. |
| `ResourceLoad` | `capacity_Bps` | `float` | B/s | Conditional model service ceiling C_r [B/s]. |
| `ResourceLoad` | `capacity_kind` | `str` | 1（标识/枚举） | declared_ceiling or effective_service; fitted rates are conditional model assumptions. |
| `ResourceLoad` | `service_bytes` | `int` | B | Q_r=sum_i(q_ir) [B]; exact integer including repeated crossings. |
| `ResourceLoad` | `time_lower_bound_s` | `float` | s | Q_r/C_r [s]; no queueing or completion prediction. |
| `ResourceLoad` | `message_ids` | `tuple[str, ...]` | 1（标识/枚举） | Unique contributors; per-message charge detail remains in MessageAnalysis. |
| `LinkTraffic` | `link_id` | `str` | 1（标识/枚举） | Directed physical channel identity, including unused channels. |
| `LinkTraffic` | `payload_bytes` | `int` | B | Sum of logical bytes traversing this link [B], with repeated crossings. |
| `LinkTraffic` | `wire_bytes` | `int \| None` | B | Sum of pre-PHY frame bytes [B]; None if a used profile omits framing. |
| `LinkTraffic` | `wire_unknown_reason` | `str \| None` | 1（标识/枚举） | Missing-framing reason; unused links have known zero work. |
| `CutAnalysis` | `cut_id` | `str` | 1（标识/枚举） | Requested cut observation identity. |
| `CutAnalysis` | `capacity` | `CutCapacity` | —（结构/对象） | Compatible directional link capacities, with selected owners and shared references. |
| `CutAnalysis` | `crossing_count` | `int` | crossing | Number of actual outgoing message traversals [crossing]; revisits count again. |
| `CutAnalysis` | `service_bytes` | `int` | B | Actual crossing work D_cut [B] in capacity.byte_basis; zero for no crossing. |
| `CutAnalysis` | `time_lower_bound_s` | `float` | s | D_cut/B_cut [s]; an empty unused cut is zero. |
| `CutAnalysis` | `message_ids` | `tuple[str, ...]` | 1（标识/枚举） | Unique messages that cross this outgoing cut. |
| `TrafficAnalysis` | `messages` | `tuple[MessageAnalysis, ...]` | —（结构/对象） | Immutable per-message route and work evidence. |
| `TrafficAnalysis` | `links` | `tuple[LinkTraffic, ...]` | —（结构/对象） | Every graph link, including zero-work channels. |
| `TrafficAnalysis` | `resources` | `tuple[ResourceLoad, ...]` | —（结构/对象） | Every unique link/constraint, including unused limits. |
| `TrafficAnalysis` | `cuts` | `tuple[CutAnalysis, ...]` | —（结构/对象） | Requested directed cuts only; no global min-cut claim. |
| `TrafficAnalysis` | `logical_payload_bytes` | `int` | B | Sum of original P2P lengths [B], before path replication. |
| `TrafficAnalysis` | `total_link_wire_bytes` | `int \| None` | B | Sum of actual pre-PHY link frame work [B]; not constraint demand sum. |
| `TrafficAnalysis` | `wire_unknown_reason` | `str \| None` | 1（标识/枚举） | Why a used link's framing prevents a complete physical-work total. |
| `TrafficAnalysis` | `resource_time_lower_bound_s` | `float` | s | max_r(Q_r/C_r) [s]. |
| `TrafficAnalysis` | `dependency_time_lower_bound_s` | `float` | s | Maximum necessary path propagation/processing delay [s]. |
| `TrafficAnalysis` | `cut_time_lower_bound_s` | `float` | s | Maximum requested D_cut/B_cut [s]; normally redundant with link bounds. |
| `TrafficAnalysis` | `communication_time_lower_bound_s` | `float` | s | max(resource, dependency, cut) [s], never their sum. |
| `TrafficAnalysis` | `bottleneck_resource_ids` | `tuple[str, ...]` | 1（标识/枚举） | All positive-work resources exactly attaining max_r(Q_r/C_r). |
| `TrafficAnalysis` | `total_energy_j` | `float \| None` | J | Complete network energy [J]; unknown without dynamic/leakage characterization. |
| `TrafficAnalysis` | `energy_unknown_reason` | `str \| None` | 1（标识/枚举） | Missing physical-cost coverage, including duration-dependent leakage. |
| `TrafficAnalysis` | `coverage` | `tuple[str, ...]` | 1（标识/枚举） | Model assumptions/omissions; no target execution or AI quality claim. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `LinkTraversal` | One actual hop retains its profile result; repeated physical hops remain separate traversal entries. |
| `ResourceCharge` | A charge limits existing work and is not an additional physical transfer to add to network wire totals. |
| `MessageAnalysis` | Each demand preserves its route and service evidence independently of aggregated resource limits. |
| `ResourceLoad` | Resource work sums all ranks/groups using one physical capacity definition, with no replicated bandwidth. |
| `LinkTraffic` | Link traffic totals count physical traversals only, independently of the number of service constraints. |
| `CutAnalysis` | A specified directed owner cut measures actual fixed-path crossings and a compatible link capacity sum. |
| `TrafficAnalysis` | Analytical output separates communication work, independent necessary bounds and unknown physical costs. |
| `analyze_traffic(cluster: ClusterSpec, traffic: TrafficInput)` | Resolve each message, count each crossing once, aggregate shared service, and combine independent bounds by max. |

### [model.py](model.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `ClusterSpec` | `cluster_id` | `str` | 1（标识/枚举） | Assembly identity; graph remains the unique physical resource table. |
| `ClusterSpec` | `graph` | `NetworkGraph` | —（结构/对象） | Validated NIC/fabric snapshots with explicit ownership. |
| `ClusterSpec` | `placements` | `tuple[RankPlacement, ...]` | —（结构/对象） | Unique ranks referencing graph endpoints; empty is legal. |
| `ClusterSpec` | `groups` | `tuple[CommunicationGroup, ...]` | —（结构/对象） | Optional ordered logical communication groups. |
| `ClusterSpec` | `schema_version` | `Literal['cluster/v1']` | —（结构/对象） | Static assembly schema identity. |
| `P2PMessage` | `message_id` | `str` | 1（标识/枚举） | Unique demand identity within one analysis. |
| `P2PMessage` | `src_rank` | `str` | 1（标识/枚举） | Existing source logical rank. |
| `P2PMessage` | `dst_rank` | `str` | 1（标识/枚举） | Existing destination logical rank. |
| `P2PMessage` | `payload_bytes` | `int` | B | Logical message length D [B]; positive, excludes control-only messages. |
| `P2PMessage` | `data_id` | `str` | 1（标识/枚举） | Application data identity retained for provenance. |
| `P2PMessage` | `content_version` | `str` | 1（标识/枚举） | Data content/version reference; does not assert availability or values. |
| `P2PMessage` | `group_id` | `str \| None` | 1（标识/枚举） | If supplied, both ranks must be members of this group. |
| `P2PMessage` | `explicit_link_ids` | `tuple[str, ...] \| None` | 1（标识/枚举） | Ordered fixed route; None invokes route_policy. |
| `P2PMessage` | `route_policy` | `Literal['shortest-hop-lex/v1', 'explicit/v1']` | —（结构/对象） | Versioned selection rule. |
| `CutRequest` | `cut_id` | `str` | 1（标识/枚举） | Unique requested observation identity. |
| `CutRequest` | `node_ids` | `tuple[str, ...]` | 1（标识/枚举） | Selected complete nodes S, possibly empty. |
| `CutRequest` | `switch_ids` | `tuple[str, ...]` | 1（标识/枚举） | Selected complete switches S, possibly empty. |
| `TrafficInput` | `messages` | `tuple[P2PMessage, ...]` | —（结构/对象） | Fixed P2P demands; an empty set is zero communication work. |
| `TrafficInput` | `requested_cuts` | `tuple[CutRequest, ...]` | —（结构/对象） | Optional compatible directed owner cuts. |
| `TrafficInput` | `schema_version` | `Literal['cluster-traffic/v1']` | —（结构/对象） | Simultaneous-demand input semantics. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `ClusterSpec` | Compose physical boundaries and logical placements without duplicating node or switch resources. |
| `P2PMessage` | A positive message is a complete logical transfer; data metadata does not prove numerical correctness. |
| `CutRequest` | A cut selects complete owners and one outgoing direction; it is not an optimization request. |
| `TrafficInput` | Every message is ready at the analysis origin; no temporal dependencies or arrival trace are silently projected. |
| `validate_traffic_references(cluster: ClusterSpec, traffic: TrafficInput)` | Validate logical demand references independently of path feasibility, profile domains or target execution. |

### [traffic.py](traffic.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `ParticipantTraffic` | `participant_id` | `str` | 1（标识/枚举） | Identity within the enclosing rank, node or endpoint table. |
| `ParticipantTraffic` | `sent_payload_bytes` | `int` | B | Sum of original outgoing logical payloads [B], without hop replication. |
| `ParticipantTraffic` | `received_payload_bytes` | `int` | B | Sum of original incoming logical payloads [B]. |
| `ParticipantTraffic` | `sent_message_count` | `int` | message | Number of outgoing P2P demands [message]. |
| `ParticipantTraffic` | `received_message_count` | `int` | message | Number of incoming P2P demands [message]. |
| `NodePairTraffic` | `src_node_id` | `str` | 1（标识/枚举） | Source node identity derived from rank placement. |
| `NodePairTraffic` | `dst_node_id` | `str` | 1（标识/枚举） | Destination node identity; may equal source in this logical description. |
| `NodePairTraffic` | `payload_bytes` | `int` | B | Sum of original message lengths for this ordered pair [B]. |
| `NodePairTraffic` | `message_count` | `int` | message | Number of demands for this pair [message]. |
| `GroupTraffic` | `group_id` | `str \| None` | 1（标识/枚举） | Explicit message group; None is the ungrouped bucket. |
| `GroupTraffic` | `payload_bytes` | `int` | B | Logical payload assigned to this group [B]. |
| `GroupTraffic` | `message_count` | `int` | message | Demands explicitly assigned to this group [message]. |
| `TrafficDescription` | `message_count` | `int` | message | Number of fixed positive-length P2P demands [message]. |
| `TrafficDescription` | `logical_payload_bytes` | `int` | B | Sum of original P2P sizes [B]. |
| `TrafficDescription` | `local_payload_bytes` | `int` | B | Same-node logical work [B]; its service still requires a systemmodel summary. |
| `TrafficDescription` | `inter_node_payload_bytes` | `int` | B | Cross-node logical work [B] = total minus local. |
| `TrafficDescription` | `per_rank` | `tuple[ParticipantTraffic, ...]` | —（结构/对象） | Every declared rank, including idle participants. |
| `TrafficDescription` | `per_node` | `tuple[ParticipantTraffic, ...]` | —（结构/对象） | Every installed endpoint-owning node, with shared ranks aggregated. |
| `TrafficDescription` | `per_endpoint` | `tuple[ParticipantTraffic, ...]` | —（结构/对象） | Every installed endpoint, with shared ranks aggregated. |
| `TrafficDescription` | `per_group` | `tuple[GroupTraffic, ...]` | —（结构/对象） | All declared groups plus the ungrouped bucket; no membership expansion. |
| `TrafficDescription` | `node_matrix` | `tuple[NodePairTraffic, ...]` | —（结构/对象） | Sparse directed matrix containing only positive demand pairs. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `ParticipantTraffic` | One rank/node/endpoint row describes logical sends and receives; it does not own additional bandwidth. |
| `NodePairTraffic` | Each message contributes once to its source-node/destination-node pair, including explicit local demands. |
| `GroupTraffic` | Group attribution follows the declared message group only; overlapping membership never replicates work. |
| `TrafficDescription` | Describe logical communication across every placement scope without claiming any route is feasible. |
| `describe_traffic(cluster: ClusterSpec, traffic: TrafficInput)` | Describe valid references before route analysis, retaining local/unreachable demand rather than dropping it. |

<!-- model-fields:end -->
