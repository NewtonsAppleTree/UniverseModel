# hardware：公共网络与节点边界

[system.py](system.py)新增标准库AddressDomainSpec/SystemPortSpec：地址宽度[bit]只界定整数byte span，不表示物理容量；方向、domain、copy/read/write权限、来源及共享引用显式且不可变。拓扑负责owner/引用/转发校验，协议名不隐含权限或一致性；独立address.validate_span不依赖硬件。范围与验证见[系统首包](../../systemmodel/docs/foundation_usage.md)和[契约测试](../../tests/contracts/test_system.py)。

[network.py](network.py) 提供C1的NetworkEndpointSpec与BandwidthConstraint。它们仅依赖标准库，负责不可变身份、来源、单位、取值和结构校验，不拥有NIC/网络状态或物理成本。其他硬件公共schema继续按实际需求加入；状态见 [STATUS](../../docs/STATUS.md)。

BandwidthConstraint用唯一resource_id和owner_id声明服务率C[B/s]。byte_basis为payload或PHY编码前frame；frame必须有frame_format_id，payload禁止混入帧格式。capacity_kind区分声明的条件模型上限与有效服务率，来源和非空coverage始终显式给出。实测平均吞吐不自动构成真实设备容量上界。

NetworkEndpointSpec绑定node、endpoint与物理port身份；非空tx/rx引用声明注入和接收资源，允许多个端点指向同一资源。组/rank不进入该硬件边界，不能按引用倍增容量。它不授予RDMA、设备内存可见性或节点内转发能力。

辅助校验函数用于实际共享边界：有限非负/正数量、精确离散计数、非空身份、不可变字符串序列。tuple/list复制为tuple，拒绝字符串充当序列、bool充当数量、无穷/NaN和未知schema。来源/覆盖属于输入证据，不是验证已经完成的标志。

顺序：参数/JSON → 值对象校验 → clustermodel图的跨对象引用/归属校验。configuration/artifacts继续通过通用dataclass/JSON使用它，不反向导入硬件。字段和接口在下方由代码生成，不另维护重复schema表。

敏感参数是容量/基准和共享引用；本目录不计算延迟/能量。验证见[公共边界测试](../../tests/contracts/test_network.py)，组合验证见[直连图](../../clustermodel/topology/UNITS.md)；当前无设备校准。

<!-- model-fields:start -->

### [network.py](network.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `BandwidthConstraint` | `resource_id` | `str` | 1（标识/枚举） | Unique shared service resource identity; not a logical group ID. |
| `BandwidthConstraint` | `owner_id` | `str` | 1（标识/枚举） | Resource owner identity; a node, switch or fabric graph, validated by the consuming topology. |
| `BandwidthConstraint` | `capacity_Bps` | `float` | B/s | Positive service capacity C [B/s] in byte_basis, not raw bit/s. |
| `BandwidthConstraint` | `byte_basis` | `Literal['payload', 'frame']` | —（结构/对象） | Logical payload or pre-PHY-encoding frame bytes. |
| `BandwidthConstraint` | `capacity_kind` | `Literal['declared_ceiling', 'effective_service']` | —（结构/对象） | Model ceiling or conditional fitted service. |
| `BandwidthConstraint` | `source_ref` | `str` | 1（标识/枚举） | Explicit source/version reference, including an identity for manual assumptions. |
| `BandwidthConstraint` | `coverage` | `tuple[str, ...]` | 1（标识/枚举） | Immutable applicability and accounting boundary statements. |
| `BandwidthConstraint` | `frame_format_id` | `str \| None` | 1（标识/枚举） | Required for frame basis; binds packetization/overhead representation. |
| `BandwidthConstraint` | `schema_version` | `Literal['network-bandwidth/v1']` | —（结构/对象） | Serialized resource semantics. |
| `NetworkEndpointSpec` | `endpoint_id` | `str` | 1（标识/枚举） | Unique network endpoint identity, independent of rank/group membership. |
| `NetworkEndpointSpec` | `node_id` | `str` | 1（标识/枚举） | Owning systemmodel node identity; multiple endpoints may share one node. |
| `NetworkEndpointSpec` | `port_id` | `str` | 1（标识/枚举） | Globally unique physical NIC port identity in one graph. |
| `NetworkEndpointSpec` | `tx_constraint_ids` | `tuple[str, ...]` | 1（标识/枚举） | Required injection capacity references; duplicates are invalid. |
| `NetworkEndpointSpec` | `rx_constraint_ids` | `tuple[str, ...]` | 1（标识/枚举） | Required receive capacity references; may overlap tx for shared duplex. |
| `NetworkEndpointSpec` | `source_ref` | `str` | 1（标识/枚举） | Endpoint capability source/version, or explicit manual assumption identity. |
| `NetworkEndpointSpec` | `coverage` | `tuple[str, ...]` | 1（标识/枚举） | Boundary conditions; does not grant device-memory visibility or RDMA semantics. |
| `NetworkEndpointSpec` | `schema_version` | `Literal['network-endpoint/v1']` | —（结构/对象） | Serialized endpoint semantics. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `validate_identity(name: str, value: str)` | Identities and provenance strings must be nonempty and have no surrounding whitespace. |
| `finite_quantity(name: str, value: float, *, positive: bool=False)` | Normalize a finite nonnegative/positive binary64 quantity; bool and numeric strings are invalid. |
| `validate_count(name: str, value: int, *, minimum: int=0)` | Byte counts and discrete extents remain exact integers; no implicit bool/float coercion. |
| `string_tuple(name: str, values: tuple[str, ...], *, unique: bool=False, allow_empty: bool=False)` | Own an immutable sequence of identities/statements and optionally reject duplicates or emptiness. |
| `BandwidthConstraint` | A unique resource supplies C [B/s] in a declared byte representation; references do not add capacity. |
| `NetworkEndpointSpec` | Read-only external NIC boundary; tx/rx reference owner-defined capacities and contain no queue state. |

### [system.py](system.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `AddressDomainSpec` | `domain_id` | `str` | 1（标识/枚举） | Unique address-space identity in one topology. |
| `AddressDomainSpec` | `owner_id` | `str` | 1（标识/枚举） | Resource instance owning this address namespace. |
| `AddressDomainSpec` | `address_bits` | `int` | bit | Unsigned byte-address width [bit], 1..64; valid addresses are [0,2**address_bits). |
| `AddressDomainSpec` | `source_ref` | `str` | 1（标识/枚举） | Source/profile or explicit modeling assumption. |
| `AddressDomainSpec` | `schema_version` | `Literal['system-address-domain/v1']` | —（结构/对象） | Namespace only; no allocation/coherence claim. |
| `SystemPortSpec` | `port_id` | `str` | 1（标识/枚举） | Unique directed port identity; ingress/egress halves are separate declarations. |
| `SystemPortSpec` | `owner_id` | `str` | 1（标识/枚举） | Owning resource instance; does not imply forwarding between its ports. |
| `SystemPortSpec` | `direction` | `Literal['ingress', 'egress']` | —（结构/对象） | Direction of the modeled path relative to the owner. |
| `SystemPortSpec` | `protocol` | `str` | 1（标识/枚举） | Explicit protocol/profile identity; peers and forwarding ports must agree. |
| `SystemPortSpec` | `operations` | `tuple[AccessOperation, ...]` | —（结构/对象） | Allowed static operations; no implicit RDMA/P2P/coherence. |
| `SystemPortSpec` | `source_ref` | `str` | 1（标识/枚举） | Capability provenance or explicit assumption. |
| `SystemPortSpec` | `domain_id` | `str \| None` | 1（标识/枚举） | Terminal address namespace; None denotes a transit-only port. |
| `SystemPortSpec` | `constraint_ids` | `tuple[str, ...]` | 1（标识/枚举） | Shared resource references charged once at this port visit; no copied capacity. |
| `SystemPortSpec` | `schema_version` | `Literal['system-port/v1']` | —（结构/对象） | Static direction/permission boundary. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `access_operations(values: tuple[AccessOperation, ...])` | Freeze a nonempty set of supported operations; protocol names never grant additional permissions. |
| `AddressDomainSpec` | An address domain names an integer address space, not physical memory capacity or residency. |
| `AddressDomainSpec.validate_span(self, address: int, length_bytes: int)` | Check a nonempty half-open byte span; this proves address validity, not allocated backing or access permission. |
| `SystemPortSpec` | Separate directed ports make attachment, terminal address ownership and permissions explicit. |

<!-- model-fields:end -->
