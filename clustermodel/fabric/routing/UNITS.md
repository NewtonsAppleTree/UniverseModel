# routing：路径选择与合法性

候选实现 `paths.py`；未实现，见 [STATUS](../../../docs/STATUS.md)。本目录只读取拓扑，不拥有链路或队列。路径选择是可替换的网络策略，collective 算法不在此处。

| 字段/量 | 角色/单位 | 约束与关系 |
| --- | --- | --- |
| src_endpoint_id / dst_endpoint_id | 输入；标识 | 必须存在；同节点路径由 systemmodel 边界处理 |
| policy_id / policy_version | 输入；枚举/版本 | explicit 或 shortest_hop；未知策略拒绝，不动态 import |
| explicit_link_ids | 输入；有序 tuple | 每条边方向连续，起止匹配；首批不允许路径重复顶点 |
| route_link_ids / constraint_ids | 派生；有序引用 | 最终路径及端点/交换/链路共享约束；不复制容量 |
| hop_count | 派生；hop | 外部有向链路数量，不等于算法轮数 |

`resolve_route(graph, request)`：端点校验 → 显式路径检查或 BFS 最少跳 → 收集经过约束。交换机的内部转发连接显式可查；NIC/终端不能成为任意中转路由器。等长候选按规范化 link ID 的稳定顺序选择，不依赖输入列表顺序。

拓扑允许环，但首批输出简单路径；不连通报告 unreachable。BFS 不使用带宽/未来拥塞，不能称作最优时延路由。未来 ECMP/多路径须记录哈希/种子、拆分粒度与实际分流，不能默认为流均分带宽。

关键敏感量为流量与路径的对应、共享资源重合程度及 tie-break。验证显式错向/断边、终端中转、合法环上的路径、平行物理端口、稳定选择与不可达；依据[资源图](../../topology/UNITS.md)和[开发计划](../../docs/development_plan.md)。无独立物理成本。
