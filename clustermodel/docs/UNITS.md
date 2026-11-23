# docs：集群模型设计与验证导航

本轮基础开发、覆盖复核与收尾优化已完成，下一轮进入chipmodel；见[完成报告及交接](completion.md)。

本目录为文档基础设施，没有 Python Unit、物理状态、参数单位或独立成本。实现状态统一见 [STATUS](../../docs/STATUS.md)。

| 文件 | 维护职责 |
| --- | --- |
| [coverage.md](coverage.md) | 整体覆盖、责任边界、广度优先及深化触发条件 |
| [breadth_usage.md](breadth_usage.md) | 多层拓扑、多路径、静态停用与需求总览的独立调用/验收 |
| [design.md](design.md) | 研究问题、系统边界、所有权、接口、计量与精度选择 |
| [development_plan.md](development_plan.md) | 逐目录任务、手算输入/预期、验证矩阵与退出条件 |
| [foundation_usage.md](foundation_usage.md) | C1–C3基础调用、四节点结果、计量范围与保存回读 |
| [c1_usage.md](c1_usage.md) | C1已实现接口、示例、独立调用、计量边界与测试命令 |
| [模块 UNITS](../UNITS.md) | 已实现对象与参数导航；字段以代码为源 |

阅读顺序：项目使命 → 设计 → 对应目录 UNITS → 开发计划的独立验收 → STATUS 证据。修改参数关系时同步根目录参数清单；修改近期优先级时同步路线和 STATUS，使命正文仍只在 PROJECT_MISSION.md 维护。

本目录无数值模型，不设置虚构敏感参数。文档验证检查链接/结构和公式口径；设计中的预期数值不能标记为程序结果。业务实现时补相应独立测试。
