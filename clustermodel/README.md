# 集群与网络

clustermodel 研究节点间网络、资源放置和共享通信路径如何限制 AI 训练/推理扩展。它组合节点能力与端口引用，维护跨节点链路、交换资源和路由；通信算法由 compiler/runtime 产生。

按[项目使命](../PROJECT_MISSION.md)，先交付可独立调用、可手算验证的资源图与通信分析，再按证据需要接入争用执行。当前开发设计已细化，下述接口/文件均为计划，尚无 Python 模型。实现进度统一见[实现状态](../docs/STATUS.md)。

## 阅读入口

- [模块设计](docs/design.md)：研究问题、所有权、接口、精度和集成边界
- [逐目录开发与验收](docs/development_plan.md)：首批范围、任务顺序、手算实验和退出条件
- [Unit 与参数导航](UNITS.md)：各目录职责、单位、公式与候选接口
- [顶层架构](../docs/architecture/design.md)、[公共契约](../docs/interfaces/contracts.md)
- [参数与数学方法](../docs/methods/parameters_and_math.md)、[第一性原理](../docs/architecture/first_principles.md)

## 子目录与顺序

| 目录 | 独立能力 | 阶段 |
| --- | --- | --- |
| [fabric/links](fabric/links/UNITS.md) | 单向容量、消息开销和孤立传输 | C1 |
| [topology](topology/UNITS.md) | 有向图、端口引用、可达性和指定割 | C1 |
| [fabric/switches](fabric/switches/UNITS.md) | 端口与共享交换容量约束 | C2 |
| [fabric/routing](fabric/routing/UNITS.md) | 显式路径与确定性最少跳路由 | C2 |
| [composition/groups](composition/groups/UNITS.md) | rank/端点放置与组引用 | C3 |
| [composition/cluster](composition/cluster/UNITS.md) | 装配、负载账本和条件下界 | C3 |
| [docs](docs/UNITS.md) | 设计、验收协议和证据导航 | 持续维护 |

组合层见 [composition](composition/UNITS.md)，网络层见 [fabric](fabric/UNITS.md)。C1–C3 构成首批分析闭环，C4 争用执行与 C5 AI 场景按需求进入。

依赖约束保持 contracts、systemmodel、costmodel。节点尚未实现时使用显式端点快照；不把 NIC、collective 算法和全局事件引擎移入集群模块。
