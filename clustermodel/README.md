# 集群与网络

clustermodel 研究节点间网络、资源放置和共享通信路径如何限制 AI 训练/推理扩展。它组合节点能力与端口引用，维护跨节点链路、交换资源和路由；通信算法由 compiler/runtime 产生。

按[项目使命](../PROJECT_MISSION.md)，本轮已完成集群基础开发、横向覆盖复核和性能优化：端点、链路/交换图、确定性路由、rank/group、通信账本、条件下界，以及多层拓扑、路径候选、静态停用和需求总览。范围与验收见[完成报告及模块交接](docs/completion.md)，实现证据统一见[实现状态](../docs/STATUS.md)。**下一轮进入 chipmodel**；集群争用执行与物理校准按后续课题需要扩展。

可运行 `python -m example.cluster_demo --config config/experiments/cluster_leaf_spine.json --overview`，查看六节点多层网络和流量矩阵。

可运行 `python -m example.cluster_demo`：两种放置的资源界为21.47483648/5.36870912 ms，见[基础指南](docs/foundation_usage.md)。

可运行 `python -m example.network_demo`：默认1 MB消息的孤立链路估计为42 μs。参数、边界和保存/回读见[C1使用指南](docs/c1_usage.md)。

## 阅读入口

- [完成报告及模块交接](docs/completion.md)：逐目录完成范围、优化证据、复现命令与下一轮安排
- [能力覆盖矩阵](docs/coverage.md)：12个维度的研究需求、职责、当前范围和深化条件
- [横向能力指南](docs/breadth_usage.md)：leaf-spine、多路径、静态停用与集群流量总览
- [模块设计](docs/design.md)：研究问题、所有权、接口、精度和集成边界
- [C1–C3基础调用与验收](docs/foundation_usage.md)：四节点对照、账本、下界及保存回读
- [C1独立调用与验证](docs/c1_usage.md)：可运行入口、结果口径和测试
- [逐目录开发与验收](docs/development_plan.md)：首批范围、任务顺序、手算实验和退出条件
- [Unit 与参数导航](UNITS.md)：各目录职责、单位、公式与已实现接口
- [顶层架构](../docs/architecture/design.md)、[公共契约](../docs/interfaces/contracts.md)
- [参数与数学方法](../docs/methods/parameters_and_math.md)、[第一性原理](../docs/architecture/first_principles.md)

## 子目录与顺序

| 目录 | 独立能力 | 阶段 |
| --- | --- | --- |
| [fabric/links](fabric/links/UNITS.md) | 单向容量、消息开销和孤立传输 | C1 已完成 |
| [topology](topology/UNITS.md) | 直连/交换有向图、可达端点、指定节点/交换割及构图函数 | C1–C2 已完成 |
| [fabric/switches](fabric/switches/UNITS.md) | 端口与共享交换容量约束 | C2 已完成 |
| [fabric/routing](fabric/routing/UNITS.md) | 显式路径与确定性最少跳路由 | C2 已完成 |
| [composition/groups](composition/groups/UNITS.md) | rank/端点放置与组引用 | C3 已完成 |
| [composition/cluster](composition/cluster/UNITS.md) | 装配、负载账本和条件下界 | C3 已完成 |
| [docs](docs/UNITS.md) | 设计、验收协议和证据导航 | 持续维护 |

组合层见 [composition](composition/UNITS.md)，网络层见 [fabric](fabric/UNITS.md)。C1–C3 构成首批分析闭环，C4 争用执行与 C5 AI 场景按需求进入。

依赖约束保持 contracts、systemmodel、costmodel。节点尚未实现时使用显式端点快照；不把 NIC、collective 算法和全局事件引擎移入集群模块。
