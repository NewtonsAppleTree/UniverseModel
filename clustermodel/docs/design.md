# clustermodel：集群、交换网络与资源组

## 核心与边界

最重要的是跨节点工作必须穿过有限的通信割集。clustermodel 依赖 contracts、systemmodel、costmodel，组合 Node，并拥有节点间 link/switch/router 的网络状态。NIC 仍属于各 Node；DP/TP 等算法和集合通信调度属于 compiler/runtime。

`composition/cluster` 组织节点，`groups` 表达资源组与参与者引用，`fabric` 管 links/switches/routing，`topology` 管网络连接。资源组不创建物理副本；不同通信组可竞争同一链路。

## 接口与参数

输入为节点引用、网络配置和网络传输请求；输出为路径能力、接收/背压、交付、流量和争用观测。数据内容可抽象为带版本与长度的 payload；功能模式仍需规约结果可验证。

| 参数 | 英文名 | 主要约束 |
| --- | --- | --- |
| 节点/端口数量 | Node/Port Count | 实例唯一与端点存在 |
| 拓扑与路由 | Topology / Routing | 连通性、允许路径与方向 |
| 链路速率/延迟 | Link Rate / Latency | 有效带宽、协议开销与双工语义 |
| 交换能力/缓冲 | Switching Capacity / Buffer | 不能假定所有端口同时满速交换 |
| 超售与割集 | Oversubscription / Cut Capacity | 流量需求与共享瓶颈 |
| 拥塞/流控 | Congestion / Flow Control | 采用流级还是包级模型须说明 |

不能仅用 node_count × card_count 描述集群。规模相同但交换层级、注入能力、路由及 rank 放置不同，扩展效率可能不同。首次实现优先流级有限带宽模型，包级重传/拥塞控制在研究需要时增加。

## 计算链与工作流

compiler 划分任务及张量 → runtime 选择或落实 collective 算法 → 生成 P2P 分段 → 本地 NIC 注入 → fabric 路由与竞争 → 远端交付 → runtime 更新同步。collective 语义必须独立于网络估计。

M06 给出割集负载下界，M13 给出特定 ring AllReduce 理想基线，M15 区分强弱扩展。大消息偏带宽受限，小消息偏启动与同步受限；不平衡计算会把网络空闲与尾部等待放大。

## 情况与优化

同机多卡通常由 systemmodel 表达；跨机才使用 fabric。DP 主要规约梯度，TP 频繁交换激活，PP 传阶段边界数据，EP 有路由与不均衡，CP 依具体注意力算法交换上下文。应由实际图和算法导出通信，不以名称套用一个固定通信量。

优化维度包括 rank 放置、分层 collective、分块大小、通信融合、拓扑感知路径与计算重叠。改变 group 的通信算法可能降低总步数却增加热点；必须比较链路负载与临界路径。

## 验证与保存

验证两点传输、共享链路、双工、incast、多组并发、缺失参与者和路径不可达；检查总注入量、每链路字节与到达量的口径。保存拓扑、路由规则、rank/group 映射、链路计数和 collective 计划，才能解释扩展曲线。

## 完成与负载补充

本地 send 完成不能代替远端可见或 collective 完成；缺失参与者与暂时拥塞分别诊断，见[生命周期规范](../../docs/interfaces/resource_lifecycle.md)。固定通信轨迹只支持相应条件下的比较，动态策略改变负载时需闭环生成；故障域与共享设施的相关失效仅在可靠性研究时启用，见[实验有效性](../../docs/methods/experiment_validity.md)与[物理可行性](../../docs/architecture/physical_feasibility.md)。
