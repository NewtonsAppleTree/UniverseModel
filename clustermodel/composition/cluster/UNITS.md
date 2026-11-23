# cluster：资源装配与通信分析

候选实现 `model.py`、`analysis.py`；未实现，见 [STATUS](../../../docs/STATUS.md)。组合节点/端点快照、网络与逻辑组；网络资源仍由 fabric 定义。分析状态是每次调用的局部账本，不是硬件队列。

## 参数和接口

| 对象/字段 | 角色/单位 | 含义与约束 |
| --- | --- | --- |
| ClusterSpec.cluster_id / graph / placements / groups | 输入；标识与引用 | 全局唯一资源表；重复引用不复制物理实例 |
| TrafficInput.messages / requested_cuts | 每次输入；消息/割集合 | 首批同时就绪的固定 P2P 工作；无隐式依赖和动态到达 |
| message_id / src_rank / dst_rank / group_id | 每次输入；标识 | 消息唯一，rank 存在，声明组时核对成员 |
| payload_bytes / data_id / content_version | 每次输入；B、身份/版本 | 正整数B；内容可为元数据，不能据此声称数值验证 |
| explicit_route / route_policy | 每次输入；边引用/策略 | 二选一，策略和版本可追溯 |
| local_path_summary | 可选输入；节点边界摘要 | 同节点消息的显式服务需求/覆盖；首版无此摘要则拒绝，不填零 |
| per_link_bytes / per_resource_service_bytes | 派生；B | 实际链路量与约束需求分开；基准匹配才累计 |
| resource_time_lower_bound_s / cut_time_lower_bound_s | 结果；s | Q/C；下界不是预计完成时间 |
| bottleneck_resource_ids / coverage / diagnostics | 结果；标识/说明 | 所有达到最大界的约束及其消息来源，不预判唯一瓶颈 |
| total_energy_j | 结果；J或None | 首批无完整成本依据，None并说明原因；部分已知另报 |

调用 `analyze_traffic(cluster, traffic)`：校验资源/放置/消息 → 路由 → 分别累计源注入、目标接收、各链路和交换内部需求 → 指定割与资源界 → 返回 TrafficAnalysis。各下层能力可绕过 cluster 直接调用。

## 公式与边界

对相同资源/基准 `Q_r=Σ_i q_ir`，`T_resource_lb=max_r(Q_r/C_r)`；分析起点全部消息就绪。逐消息延迟的必要界与资源界只可安全取max，不擅自相加。无工作时界为0；不可达或资源不可满足报告不可行。

指定有向割按已选路径实际经过计算 `D_cut/B_cut`，多次过割分别计数。容量与流量不能混用 payload 和帧字节；未知线量不可填0。总网络链路字节是逐边之和，NIC/交换内部约束需求不能再加入该和。

多 rank 共享 NIC 的需求按同一约束累计。端点摘要与细 Node 互斥替换同一覆盖；整个网络外部后端与本地执行也互斥计费。不同约束可以同时限制同一物理工作，不能以“避免重复成本”为由丢掉有效带宽约束。

关键敏感量为消息矩阵/长度、放置、共享链路、NIC、交换容量与路由。首批不推导实际利用率、排队、目标可见性、训练step或推理请求时延；静态下界的减少不证明相同比例的执行加速。

验证[四节点夹具](../../docs/development_plan.md)、双工/共享NIC、消息守恒、资源身份、空工作/不可达、参数敏感性和记录回读。独立手算为正确性证据，C4/C5再加入执行、数值与物理校准。
