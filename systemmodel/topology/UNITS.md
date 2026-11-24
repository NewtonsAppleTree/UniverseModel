# topology：节点有向端口与显式访问路径

SystemTopology拥有不可变的唯一scope资源树、地址域、端口、SystemLink、PortForwarding和共享BandwidthConstraint清单。复用chipmodel ResourceNode；节点库存中的旧ports须为空，实际芯片内部端口留在被引用模型中。此处无动态队列、时钟、执行状态或物理成本。

| Unit | 语义与边界 |
| --- | --- |
| SystemLink | 一个egress到不同owner的ingress，每个有向端口最多连接一次；连接ID不额外提供带宽 |
| PortForwarding | 同owner的transit ingress→egress关系；端口同属一个组件不会自动转发，terminal不能当中转 |
| SystemTopology | 包含树无环，连接图可有环；校验协议相同、权限子集、域归属和共享资源引用 |
| PathRequest/SystemPath | copy/read/write静态权限请求与已校验的有序路径；不把协议名当作访问授权 |
| find_path/validate_path | 确定性最少link跳数搜索或指定simple path检查；结果不是最快路径或已完成传输 |

资源/域/端口/连接有各自的类型命名空间。BandwidthConstraint.resource_id必须对应库存中的实际model_id资源，owner_id必须是其parent。一次选择不能同时计入资源摘要与内部后代。同一wire/crossing及它紧邻端口不能重复声明同一收费资源；沿更长路径的多次真实访问保留为constraint_visits，不做跨阶段去重，也不推导字节或时间。

address_bits以bit计，合法span为0≤address且address+length_bytes≤2**address_bits，length_bytes>0。这个关系来自整数地址定义，不说明物理容量、地址翻译或驻留。copy/read/write仅表示本路径上的权限，read响应路径与实际搬运语义留待S2/S3；无CXL一致性或RDMA授予。

共享capacity_Bps为[B/s]，payload/frame口径、frame_format_id、capacity_kind及source_ref按公共契约保留；图不把不同资源或不同byte basis相加。空constraint_ids表示没有建模该段服务，绝不代表无限带宽或零成本。示例16e9/8e9只是手工payload条件声明，未校准PCIe。

先构造SystemTopology，再构造PathRequest，调用find_path；或直接validate_path检查指定link_ids。最少跳数以每个link为1，分支按link_id稳定排序；max_hops是宿主搜索/路径长度上限，不是cycle。路径必须从带domain的egress到带domain的ingress，逐link/crossing支持该operation。无路或预算内未找到时明确失败，不隐式尝试host staging。

最敏感条件是方向/权限、显式crossing、共享归属、路径长度预算；库存排序不改变identity_hash，来源或能力变更会改变身份。测试包括30个小型有环图与独立owner排列穷举、手算双卡路径、非法模型/方向/协议/域/重复计费和查询纯性。见[模型测试](../../tests/systemmodel/test_foundation.py)和[指南](../docs/foundation_usage.md)。

<!-- model-fields:start -->

### [graph.py](graph.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `SystemLink` | `link_id` | `str` | 1（标识/枚举） | Unique directed connection identity, not an additional bandwidth resource. |
| `SystemLink` | `source_port_id` | `str` | 1（标识/枚举） | Existing egress port. |
| `SystemLink` | `target_port_id` | `str` | 1（标识/枚举） | Existing ingress port of a different component. |
| `SystemLink` | `operations` | `tuple[AccessOperation, ...]` | —（结构/对象） | Operations supported by this link and both endpoint ports. |
| `SystemLink` | `source_ref` | `str` | 1（标识/枚举） | Wiring/permission evidence or manual assumption. |
| `SystemLink` | `constraint_ids` | `tuple[str, ...]` | 1（标识/枚举） | Unique service references for one crossing; empty means service remains unmodeled. |
| `PortForwarding` | `forwarding_id` | `str` | 1（标识/枚举） | Unique crossing identity; no automatic all-to-all forwarding. |
| `PortForwarding` | `ingress_port_id` | `str` | 1（标识/枚举） | Transit ingress; terminal address ports cannot forward. |
| `PortForwarding` | `egress_port_id` | `str` | 1（标识/枚举） | Transit egress owned by the same component. |
| `PortForwarding` | `operations` | `tuple[AccessOperation, ...]` | —（结构/对象） | Allowed operations for this exact crossing. |
| `PortForwarding` | `source_ref` | `str` | 1（标识/枚举） | Explicit forwarding/permission assumption or evidence. |
| `PortForwarding` | `constraint_ids` | `tuple[str, ...]` | 1（标识/枚举） | Shared resource references for this internal crossing. |
| `SystemTopology` | `scope_id` | `str` | 1（标识/枚举） | Sole root container in the resource inventory. |
| `SystemTopology` | `resources` | `tuple[ResourceNode, ...]` | —（结构/对象） | Reused chipmodel ownership nodes; models are references, never cloned state. |
| `SystemTopology` | `domains` | `tuple[AddressDomainSpec, ...]` | —（结构/对象） | Explicit terminal address namespaces; no backing capacity inferred. |
| `SystemTopology` | `ports` | `tuple[SystemPortSpec, ...]` | —（结构/对象） | Node-level ports; separate from any chip-internal port graph. |
| `SystemTopology` | `links` | `tuple[SystemLink, ...]` | —（结构/对象） | Directed physical attachment relations, at most one link per port direction. |
| `SystemTopology` | `forwardings` | `tuple[PortForwarding, ...]` | —（结构/对象） | Explicit switch/root-complex transit permission. |
| `SystemTopology` | `constraints` | `tuple[BandwidthConstraint, ...]` | 1（标识/枚举） | Existing resource IDs with one sourced service declaration each. |
| `SystemTopology` | `source_ref` | `str` | 1（标识/枚举） | Whole-topology origin/version or manual fixture identity. |
| `SystemTopology` | `coverage` | `tuple[str, ...]` | 1（标识/枚举） | Scope, assumptions and omitted mechanisms. |
| `SystemTopology` | `schema_version` | `Literal['system-topology/v1']` | —（结构/对象） | Static wiring and permissions, not target execution. |
| `SystemTopology` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Hash the complete sourced structure and shared-capacity declarations; no runtime state enters this identity. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `freeze_inventory(name: str, values: tuple[T, ...], expected: type[T], key: str)` | Freeze/sort an inventory and reject duplicate IDs before a dictionary can hide conflicting resources. |
| `SystemLink` | A wire joins one egress to one ingress; shared service is referenced separately from connectivity. |
| `PortForwarding` | Only an explicit ingress-to-egress relation permits transit within a switch/root complex. |
| `SystemTopology` | One immutable node/board topology owns a containment tree; links and crossings may form cycles. |
| `SystemTopology.identity_hash` | Hash the complete sourced structure and shared-capacity declarations; no runtime state enters this identity. |
| `validate_topology(topology: SystemTopology)` | Enforce unique scope/ownership, same-protocol wiring, explicit transit and nonduplicated per-stage charges. |

### [query.py](query.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `PathRequest` | `source_port_id` | `str` | 1（标识/枚举） | Terminal egress in the source address domain. |
| `PathRequest` | `target_port_id` | `str` | 1（标识/枚举） | Terminal ingress in the target address domain. |
| `PathRequest` | `operation` | `AccessOperation` | —（结构/对象） | Required permission on every visited port/link/crossing. |
| `PathRequest` | `link_ids` | `tuple[str, ...] \| None` | 1（标识/枚举） | Explicit nonempty simple path, or None for deterministic minimum-hop search. |
| `PathRequest` | `max_hops` | `int` | link | Host traversal/path-length guard [link]; never hardware latency. |
| `SystemPath` | `topology_identity` | `str` | 1（标识/枚举） | Identity of the full immutable topology and provenance. |
| `SystemPath` | `source_domain_id` | `str` | 1（标识/枚举） | Actual source terminal address namespace. |
| `SystemPath` | `target_domain_id` | `str` | 1（标识/枚举） | Actual target terminal address namespace. |
| `SystemPath` | `operation` | `AccessOperation` | —（结构/对象） | Operation checked on the entire path. |
| `SystemPath` | `link_ids` | `tuple[str, ...]` | 1（标识/枚举） | Ordered directed connections. |
| `SystemPath` | `forwarding_ids` | `tuple[str, ...]` | 1（标识/枚举） | Ordered internal crossings, exactly one between consecutive links. |
| `SystemPath` | `constraint_visits` | `tuple[str, ...]` | 1（标识/枚举） | Ordered references at ports/wires/crossings; no byte count or bandwidth sum implied. |
| `SystemPath` | `constraint_ids` | `tuple[str, ...]` | 1（标识/枚举） | 只读派生属性；Unique limits describe which resources constrain a route; their capacities are not summed along the path. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `PathRequest` | Requests explicitly choose terminal port directions and one operation; optional links fix a reproducible route. |
| `SystemPath` | Results preserve every service reference visit; repeated use is distinct from duplicated physical capacity. |
| `SystemPath.constraint_ids` | Unique limits describe which resources constrain a route; their capacities are not summed along the path. |
| `validate_path(topology: SystemTopology, request: PathRequest, link_ids: tuple[str, ...])` | Validate an explicit simple route and retain each visited resource; no runtime, memory access or service model executes. |
| `find_path(topology: SystemTopology, request: PathRequest)` | Breadth-first search minimizes link count; link-ID ordered branches break ties, not latency/capacity optimization. |

<!-- model-fields:end -->
