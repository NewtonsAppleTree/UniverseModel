# 背景参考

这里保存术语、参数来源和架构方案的背景材料。它们帮助理解设计选择；模块边界以 [架构规范](../architecture/design.md)为准，数据对象以 [公共契约](../interfaces/contracts.md)为准，可执行能力以 [实现状态](../STATUS.md)为准。

| 文档 | 用途 |
| --- | --- |
| [开源项目调研与模块选型](open_source_landscape.md) | 102 个候选与 44 篇代表论文的首轮核对、模块对应、复用边界与精读计划 |
| [开源候选全量清单与横向对照](open_source_comparison.md) | 13 个模块、22 个选型问题；同模块多候选，GitHub stars、维护信息、功能差异和共同验证问题 |
| [2026-11-20 调研数据快照](data/open_source_snapshot_2026-11-20.json) | GitHub stars/维护信息、OpenAlex 引用记录、来源与版本/许可发现 |
| [AI 软件语料审阅](ai_software_corpus_review.md) | 课程文本与端侧截图核查；编译、部署、量化、KV 和训练分层；新增候选与近期研究任务 |
| [2026-11-20 语料来源记录](data/ai_software_sources_2026-11-20.json) | 用户文本身份、截图来源边界、技术纠错的官方来源与内容哈希 |
| [顶层架构参数清单](../../ARCHITECTURE_PARAMETERS.md) | 新设计的参数筛选入口：术语、单位、关系、适用条件、来源与纠错 |
| [layout_roi 手册审阅](layout_roi_review.md) | 原文统计、15 项审阅结论、7 个例子及完整走查修订、内容归属与源码核查边界 |
| [结构参数手册](architecture_parameters.md) | 中英文名词、参数族、公开工具和来源 |
| [异构芯片封装与集群参考](heterogeneous_cluster_plan.md) | CPU/GPU/NPU/CIM、3D、HBF、双裸片和多机的设计情景 |
| [硬件组件目录](hardware_component_catalog.md) | 计算、CIM 外围、存储、搬运、控制、互连的输入输出、技术指标与建议归属 |
| [chipmodel 子系统与单元覆盖清单](../../chipmodel/docs/component_inventory.md) | 八个直接子目录下的候选单元、DDR 路径及状态归属 |

背景文档中的模型层级、参数集合和首版范围是设计建议。实现采用某项建议时，应在对应模块设计、公共契约和验证依据中落定；引用的外部规格要记录其实际版本和适用条件。
