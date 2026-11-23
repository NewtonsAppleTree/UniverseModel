# groups：rank放置与有序通信组

实现 [model.py](model.py)：RankPlacement、CommunicationGroup、validate_groups。唯一逻辑rank映射到node/endpoint，多个rank可共享端点，多端口可共享NIC约束。组内成员非空、有序且唯一，组间允许重叠。

身份无B/s单位，不复制资源，不隐含DP/TP/collective算法或工作量。字段由下表维护。参数序列转tuple；组内顺序保留，组合层资源集合按ID排序。

顺序：构造放置/组 → validate_groups(graph,placements,groups)。验证rank/group唯一、端点存在且归node、组引用rank存在。消息声明group时两端成员关系由analyze_traffic检查。

无执行、同步或barrier状态。敏感量为放置、成员和物理共享，修改组标签不增加带宽。验证重复/缺失成员、顺序、重叠组、端点所有权与多rank/NIC共享，见[集群测试](../../../tests/clustermodel/test_cluster.py)及[指南](../../docs/foundation_usage.md)。

<!-- model-fields:start -->

### [model.py](model.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `RankPlacement` | `rank_id` | `str` | 1（标识/枚举） | Unique logical participant identity; no implicit numeric ordering. |
| `RankPlacement` | `node_id` | `str` | 1（标识/枚举） | Owning node identity, checked against the endpoint snapshot. |
| `RankPlacement` | `endpoint_id` | `str` | 1（标识/枚举） | Existing external NIC boundary; may be shared by many ranks. |
| `CommunicationGroup` | `group_id` | `str` | 1（标识/枚举） | Logical group identity; not a physical resource or algorithm choice. |
| `CommunicationGroup` | `rank_ids` | `tuple[str, ...]` | 1（标识/枚举） | Nonempty ordered unique members; all must have placements. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `RankPlacement` | A rank references an existing node/NIC boundary; sharing this reference never creates bandwidth. |
| `CommunicationGroup` | Member order belongs to the application; overlap between distinct groups is permitted. |
| `validate_groups(graph: NetworkGraph, placements: tuple[RankPlacement, ...], groups: tuple[CommunicationGroup, ...])` | Independently verify placement ownership and ordered group references against an existing graph. |

<!-- model-fields:end -->
