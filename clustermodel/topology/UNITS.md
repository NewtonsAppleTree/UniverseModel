# topology：物理端口图、构图与指定割

实现 [graph.py](graph.py)、[builders.py](builders.py)。NetworkGraph 冻结/排序端点、链路、约束和交换实例。direct-network-graph/v1 保持C1直连范围，交换图须显式用 routed-network-graph/v1，未知版本失败。

节点从端点推导；node/switch/graph owner ID彼此区分。全图port_id唯一，每端口最多一条输入/输出，两方向连接同一peer。链接与BandwidthConstraint共用唯一服务资源命名空间。NIC约束归node、内部crossing归switch、链路附加介质归graph；共享引用不新增资源。同owner物理链接拒绝。

只有SwitchConnection赋予转发。物理环合法，NIC不能中转。reachable_endpoints遍历显式交换连接并在接收NIC停止；直连图仍只得到直接邻端点。断开图合法，正消息由路由判断可行性。

独立接口：NetworkGraph自动validate_graph，get_link查方向；cut_capacity(graph,node_ids,switch_ids=())选择完整owner集合S，计算S→外部物理边的B_cut=ΣC_e [B/s]。要求统一payload/frame及frame_format_id；空割0、基准/kind为None。拟合贡献标effective_service。这个和不代表可达到吞吐，也不求min-cut；实际过割量由分析层计算。

纯函数direct_network、single_switch_network、two_partition_network接收显式端点/NIC约束和LinkParams模板。模板仅替换身份/端口；反向独立，共享介质须明确提供。交换容量[B/s]、处理延迟[s]和来源必填，辅助crossbar按payload每crossing一次生成共享约束。异构方向/限制可手工构图或replace。

敏感量为端口、方向、共享所有权、拓扑/路由和割集合。图无额外物理成本/状态。验证[直连测试](../../tests/clustermodel/test_topology.py)、[交换/路由/构图测试](../../tests/clustermodel/test_cluster.py)，依据[基础指南](../docs/foundation_usage.md)。

## 多层构图、库存与静态可用性

leaf_spine_network接收非空leaf→endpoint分区及spine集合，每个端点出现一次，每个leaf与每个spine双向相连；方向数为2·(endpoint_count+leaf_count·spine_count)。leaf/spine共享容量[B/s]与必要处理延迟[s]分别显式给定。多个node端口可位于不同leaf并共享同一NIC约束；不自动推断rank跨NIC分流。

[inspection.py](inspection.py)的inspect_network统计安装node/endpoint/switch/约束、当前方向/物理端口对和未接端点，仅对调用者指定的source_endpoint_ids做可达性查询。双方向存在不证明全双工独立容量；同节点端点另列，不能据此声称本地服务可用。未查询源不宣称已经完成全网连通分析。

[scenarios.py](scenarios.py)的NetworkOutage/OutageView选择方向或完整node/switch。apply_outage保留原图哈希、source_ref及实际移除集合，复制图并移除对应方向；安装资源声明与rank引用保留，不把不可达需求删掉。空选择为等价图，未知选择失败。没有时间、概率、修复或协议收敛；重新选择路径只是在新静态图上查询。

新敏感量为leaf/spine规模、非均匀分区、方向可用性和查询源范围。验证[横向测试](../../tests/clustermodel/test_breadth.py)，完整说明见[指南](../docs/breadth_usage.md)。

## 查询规模与索引

graph.py内部的_NetworkIndex仅保存当前不可变图的派生查找表：端点、物理方向、显式crossing及按link ID排序的邻接。空间为O(P+L+X)，P为端口数、L为方向数、X为显式交换连接数；表项引用现有资源，不生成第二份容量。它不进入NetworkGraph字段、配置、哈希或产物，没有全局缓存。

一次流量分析和一次多源inspect_network分别复用各自索引；独立reachable_endpoints仍可直接调用。构图校验预先汇总egress引用，所有入端口的frame约束仍须与实际出方向格式一致。crossbar自身有O(p²)显式连接，索引不改变这个输入规模。验证见[收尾测试](../../tests/clustermodel/test_closeout.py)，宿主规模证据见[完成报告](../docs/completion.md)。

<!-- model-fields:start -->

### [builders.py](builders.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `direct_network(*, graph_id: str, endpoints: tuple[NetworkEndpointSpec, ...], constraints: tuple[BandwidthConstraint, ...], link_profile: LinkParams)` | Build two directly attached NIC boundaries, preserving caller-supplied node/shared bandwidth constraints. |
| `single_switch_network(*, graph_id: str, endpoints: tuple[NetworkEndpointSpec, ...], constraints: tuple[BandwidthConstraint, ...], access_profile: LinkParams, switch_capacity_Bps: float, forwarding_latency_s: float, source_ref: str, switch_id: str='s0')` | Build one full-duplex access attachment per endpoint and one explicitly shared switch service resource. |
| `two_partition_network(*, graph_id: str, left: tuple[NetworkEndpointSpec, ...], right: tuple[NetworkEndpointSpec, ...], constraints: tuple[BandwidthConstraint, ...], access_profile: LinkParams, uplink_profile: LinkParams, switch_capacity_Bps: float, forwarding_latency_s: float, source_ref: str, left_switch_id: str='sL', right_switch_id: str='sR')` | Join two explicit endpoint partitions through independent uplink directions; shared duplex needs a supplied constraint. |
| `leaf_spine_network(*, graph_id: str, leaves: Mapping[str, tuple[NetworkEndpointSpec, ...]], spine_ids: tuple[str, ...], constraints: tuple[BandwidthConstraint, ...], access_profile: LinkParams, uplink_profile: LinkParams, leaf_capacity_Bps: float, spine_capacity_Bps: float, leaf_forwarding_latency_s: float, spine_forwarding_latency_s: float, source_ref: str)` | Build a complete leaf-to-spine fabric with explicit endpoint partitions and independent full-duplex uplinks. |

### [graph.py](graph.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `NetworkGraph` | `graph_id` | `str` | 1（标识/枚举） | Fabric owner identity; must be distinct from every node_id. |
| `NetworkGraph` | `endpoints` | `tuple[NetworkEndpointSpec, ...]` | —（结构/对象） | Immutable external NIC ports; at least one endpoint. |
| `NetworkGraph` | `links` | `tuple[LinkParams, ...]` | —（结构/对象） | Directed channels between different node/switch owners; disconnected graphs are valid. |
| `NetworkGraph` | `constraints` | `tuple[BandwidthConstraint, ...]` | 1（标识/枚举） | Unique node/switch/fabric limits referenced by endpoints, crossings and links. |
| `NetworkGraph` | `switches` | `tuple[SwitchParams, ...]` | —（结构/对象） | Unique fabric switches; endpoints never act as forwarding devices. |
| `NetworkGraph` | `schema_version` | `Literal['direct-network-graph/v1', 'routed-network-graph/v1']` | —（结构/对象） | Explicit graph semantics. |
| `NetworkGraph` | `node_ids` | `tuple[str, ...]` | 1（标识/枚举） | 只读派生属性；Node membership is derived from endpoint ownership; it is not an independently editable count. |
| `CutCapacity` | `node_ids` | `tuple[str, ...]` | 1（标识/枚举） | Selected complete nodes S; all NIC ports of a node move together. |
| `CutCapacity` | `link_ids` | `tuple[str, ...]` | 1（标识/枚举） | Directed links from S to its complement; reverse links excluded. |
| `CutCapacity` | `capacity_Bps` | `float` | B/s | Sum of matching link service capacities [B/s]; not attainable aggregate throughput. |
| `CutCapacity` | `byte_basis` | `str \| None` | 1（标识/枚举） | Common frame/payload representation; None for an empty outgoing cut. |
| `CutCapacity` | `frame_format_id` | `str \| None` | 1（标识/枚举） | Common frame representation identity, if applicable. |
| `CutCapacity` | `capacity_kind` | `str \| None` | 1（标识/枚举） | effective_service if any contributing rate is fitted; None for empty cuts. |
| `CutCapacity` | `shared_constraint_ids` | `tuple[str, ...]` | 1（标识/枚举） | Fabric constraints still applicable beyond the link sum. |
| `CutCapacity` | `switch_ids` | `tuple[str, ...]` | 1（标识/枚举） | Selected whole switches in S; all their ports move together. |
| `CutCapacity` | `empty` | `bool` | 1（布尔） | 只读派生属性；No outgoing links means no network service across this direction, not proof that any demand is feasible. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `NetworkGraph` | A graph references NIC boundaries and explicit fabric forwarding capabilities without creating execution state. |
| `NetworkGraph.node_ids` | Node membership is derived from endpoint ownership; it is not an independently editable count. |
| `_NetworkIndex` | Index one immutable graph for a batch of queries; derived lookup state never enters graph identity or artifacts. |
| `_NetworkIndex.get_link(self, link_id: str)` | Resolve a directed channel in expected O(1) time, preserving diagnostics for an unknown identity. |
| `_NetworkIndex.get_crossing(self, ingress: str, egress: str)` | Only a declared switch relation allows transit; sharing a node or owner is insufficient. |
| `_NetworkIndex.reachable_endpoints(self, endpoint_id: str)` | Traverse active directed channels, stopping at all receiving NIC ports, including other NICs of the source node. |
| `validate_graph(graph: NetworkGraph)` | Validate wiring, ownership and byte representations; NICs cannot implicitly bridge ports. |
| `port_owners(graph: NetworkGraph)` | Map physical ports to their node or switch owner; validate_graph detects overwritten duplicate ports. |
| `next_links(graph: NetworkGraph, ingress_port_id: str)` | Enumerate legal next physical links from a switch ingress, never from a receiving NIC endpoint. |
| `get_link(graph: NetworkGraph, link_id: str)` | Resolve a declared link by identity; missing links are errors, never a zero-capacity placeholder. |
| `reachable_endpoints(graph: NetworkGraph, endpoint_id: str)` | Traverse declared switch crossings, stopping at endpoint ports; preserve direct-graph reachability semantics. |
| `CutCapacity` | An outgoing node cut reports only a link capacity sum; shared resources can further restrict service. |
| `CutCapacity.empty` | No outgoing links means no network service across this direction, not proof that any demand is feasible. |
| `cut_capacity(graph: NetworkGraph, node_ids: tuple[str, ...], *, switch_ids: tuple[str, ...]=())` | Sum only a specified directed cut in a compatible byte basis; this is not a min-cut or routing solver. |

### [inspection.py](inspection.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `EndpointReachability` | `source_endpoint_id` | `str` | 1（标识/枚举） | Queried source boundary. |
| `EndpointReachability` | `reachable_remote_ids` | `tuple[str, ...]` | 1（标识/枚举） | Other-node endpoints reachable by declared switch crossings. |
| `EndpointReachability` | `unreachable_remote_ids` | `tuple[str, ...]` | 1（标识/枚举） | Other-node endpoints lacking an outgoing valid forwarding path. |
| `EndpointReachability` | `same_node_ids` | `tuple[str, ...]` | 1（标识/枚举） | Other endpoints on this source node; excluded from remote connectivity claims. |
| `NetworkOverview` | `node_count` | `int` | node | Installed endpoint-owning nodes [node], including isolated owners after static outages. |
| `NetworkOverview` | `endpoint_count` | `int` | endpoint | Installed NIC boundary ports [endpoint]. |
| `NetworkOverview` | `switch_count` | `int` | switch | Installed declared switches [switch], including isolated switches. |
| `NetworkOverview` | `constraint_count` | `int` | resource | Unique shared capacity declarations [resource]; independent of reference count. |
| `NetworkOverview` | `directed_link_count` | `int` | link | Currently present physical directions [link]. |
| `NetworkOverview` | `physical_connection_count` | `int` | connection | Distinct unordered physical port pairs with at least one present direction [connection]. |
| `NetworkOverview` | `bidirectional_connection_count` | `int` | connection | Port pairs with both directions present [connection]; shared duplex limits still apply. |
| `NetworkOverview` | `one_way_connection_count` | `int` | connection | Port pairs having only one direction present [connection]. |
| `NetworkOverview` | `unattached_endpoint_ids` | `tuple[str, ...]` | 1（标识/枚举） | Endpoints with neither an input nor output physical link. |
| `NetworkOverview` | `reachability` | `tuple[EndpointReachability, ...]` | —（结构/对象） | Only explicitly requested source queries; empty means not queried. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `EndpointReachability` | Reachability concerns remote NIC boundaries only; same-node service is a separate systemmodel responsibility. |
| `NetworkOverview` | Counts describe the supplied graph view, never a sum of attainable bandwidth or capacity duplicated by rank. |
| `inspect_network(graph: NetworkGraph, *, source_endpoint_ids: tuple[str, ...]=())` | Inspect inventory in linear graph space; perform forwarding traversal only for caller-selected source endpoints. |

### [scenarios.py](scenarios.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `NetworkOutage` | `source_ref` | `str` | 1（标识/枚举） | Explicit scenario assumption or observed failure-source/version reference. |
| `NetworkOutage` | `disabled_link_ids` | `tuple[str, ...]` | 1（标识/枚举） | Selected directed channels; reverse direction is not implicitly disabled. |
| `NetworkOutage` | `disabled_node_ids` | `tuple[str, ...]` | 1（标识/枚举） | All incident channels of these nodes become unavailable. |
| `NetworkOutage` | `disabled_switch_ids` | `tuple[str, ...]` | 1（标识/枚举） | All incident channels of these switches become unavailable. |
| `NetworkOutage` | `schema_version` | `Literal['network-static-outage/v1']` | —（结构/对象） | Static availability semantics. |
| `OutageView` | `original_graph_hash` | `str` | 1（标识/枚举） | Canonical identity of the graph before removing channels. |
| `OutageView` | `outage` | `NetworkOutage` | —（结构/对象） | Exact requested static availability change and its source. |
| `OutageView` | `removed_link_ids` | `tuple[str, ...]` | 1（标识/枚举） | Union of explicitly selected and owner-incident directions removed. |
| `OutageView` | `graph` | `NetworkGraph` | —（结构/对象） | Remaining active links; installed nodes/switches/constraints stay declared, with no traffic deletion. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `NetworkOutage` | Outages identify unavailable directions or complete owners while retaining installed endpoint/resource identities. |
| `OutageView` | A static view retains its cause and original graph identity; preserved capacities are installed declarations. |
| `apply_outage(graph: NetworkGraph, outage: NetworkOutage)` | Remove directions from a fresh graph, preserving rank references so unavailable demands fail visibly. |

<!-- model-fields:end -->
