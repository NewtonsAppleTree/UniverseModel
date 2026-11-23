# clustermodel Unit 与参数入口

本轮基础开发、覆盖复核与收尾优化已完成，下一轮进入chipmodel；见[完成报告及交接](docs/completion.md)。

跨节点网络基础分析已完成 C1–C3：端点/链路、交换转发、固定路由、rank/group、通信账本、条件下界与记录回读。依据[项目使命](../PROJECT_MISSION.md)和[参数清单](../ARCHITECTURE_PARAMETERS.md)第6节，证据见[基础指南](docs/foundation_usage.md)及[STATUS](../docs/STATUS.md)。本轮已完成[覆盖矩阵](docs/coverage.md)的基础复核与收尾优化。

| 子目录 | 职责与覆盖 |
| --- | --- |
| [fabric](fabric/UNITS.md) | 单向链路服务、显式交换能力和固定路由 |
| [topology](topology/UNITS.md) | 端口图、所有权/方向校验、可达性、指定割和构图函数 |
| [composition](composition/UNITS.md) | rank/group、集群装配、逐消息/资源需求及条件下界 |
| [docs](docs/UNITS.md) | 设计、独立验收、运行方法与证据导航 |

公共 NIC 快照/容量由 [contracts/hardware](../contracts/hardware/UNITS.md)维护。NIC 属节点，交换/共享介质归其明确 owner；多个 rank、端口、组引用同一容量时按同一资源累计。

顺序：端点/容量与链路/交换参数 → NetworkGraph → 放置/组与 ClusterSpec → TrafficInput → analyze_traffic。任一下层可独立调用。配置/输入冻结，派生量只读，账本为函数局部变量，没有硬件队列或全局时钟。

单位：消息/帧 B、容量 B/s、线路 bit/s、延迟 s。wire_bytes 是 PHY 编码前帧字节。敏感量为消息矩阵/长度、放置/路由、共享 NIC/交换/上行容量、分包对齐。Q_r=Σq_ir，T_resource=max(Q_r/C_r)，再与必要路径延迟和指定割界取 max。

未知帧量/能量为 None+原因；没有实际完成时间、AI质量或物理校准。同节点服务摘要尚未接入，正需求明确拒绝。collective 属 runtime，全局事件属 simulator。独立手算、守恒、共享反例、敏感性与回读验证当前范围。

横向扩展现有接口：topology补leaf-spine、安装资源/方向可达性、静态停用视图；routing补最短路径总数与有界候选；composition补rank/节点/端点/声明组和稀疏节点流量矩阵。调用入口及边界见[横向指南](docs/breadth_usage.md)。这些观测不增加物理资源，也不推导动态故障恢复或collective行为。

<!-- model-fields:start -->



<!-- model-fields:end -->
