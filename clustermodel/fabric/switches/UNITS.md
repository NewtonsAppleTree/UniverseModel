# switches：显式交换转发能力

实现 [model.py](model.py)：SwitchParams 拥有端口、必要首数据处理延迟和 SwitchConnection。连接指定 ingress → egress 及非空容量引用；缺连接不能转发。图检查资源属于本 switch，端口不能被其他 owner 重用。

每次 crossing 对连接列出的每个资源计一次：payload 基准计 D [B]，frame 基准计出口消息帧量 W_out [B]，并匹配出口 frame_format_id；入口格式可不同。厂家入口/出口汇总容量须由调用者转换，不自动除二。连接共享 constraint_id 即共享 C [B/s]。

forwarding_latency_s [s] 是每次 crossing 必需的首数据处理延迟，加入路径必要延迟界；不含队列/整体序列化。source_ref/coverage 说明来源与适用性。字段由下表生成。

顺序：SwitchConnection → SwitchParams → NetworkGraph 跨对象校验；实例无队列。构图函数显式枚举 crossbar，直接构造不隐含全连接。敏感量为连接集合、内部容量、计量基准和处理延迟。

[集群测试](../../../tests/clustermodel/test_cluster.py)验证缺连接不可达、交换瓶颈、所有权、帧格式、重复端口/连接和必要延迟。依据[开发计划](../../docs/development_plan.md)；无包缓存、硬件规约或设备校准。

<!-- model-fields:start -->

### [model.py](model.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `SwitchConnection` | `ingress_port_id` | `str` | 1（标识/枚举） | Owned receiving port identity. |
| `SwitchConnection` | `egress_port_id` | `str` | 1（标识/枚举） | Owned transmitting port identity; different from ingress. |
| `SwitchConnection` | `constraint_ids` | `tuple[str, ...]` | 1（标识/枚举） | Nonempty switch-owned limits; payload or outgoing-frame work per crossing. |
| `SwitchParams` | `switch_id` | `str` | 1（标识/枚举） | Unique fabric device owner identity, distinct from nodes and graph. |
| `SwitchParams` | `port_ids` | `tuple[str, ...]` | 1（标识/枚举） | Unique physical ports; sorted as an unordered resource set. |
| `SwitchParams` | `connections` | `tuple[SwitchConnection, ...]` | —（结构/对象） | Explicit allowed directed crossings, including shared limits. |
| `SwitchParams` | `forwarding_latency_s` | `float` | s | Necessary per-crossing first-data processing latency [s]; no queue/startup time. |
| `SwitchParams` | `source_ref` | `str` | 1（标识/枚举） | Source/version for declared forwarding and latency assumptions. |
| `SwitchParams` | `coverage` | `tuple[str, ...]` | 1（标识/枚举） | Applicability and omitted switching/physical behavior. |
| `SwitchParams` | `schema_version` | `Literal['network-switch/v1']` | —（结构/对象） | Static switch capability schema. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `SwitchConnection` | Each permitted ingress-to-egress crossing charges its listed resources exactly once. |
| `SwitchParams` | A switch owns ports and forwarding relations; bandwidth definitions live once in the graph resource table. |

<!-- model-fields:end -->
