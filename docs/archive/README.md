# 历史记录

归档保存当时的讨论和推理，不承担当前规范或进度说明。原文及 Word 保留原样，后续开发不再要求同步重建。

| 记录 | 来源 |
| --- | --- |
| [2026 年 10 月架构审视](2026-10-30_architecture_review.md)及[当时的 Word](UniverseModel_Architecture_Review.docx) | 763b83d 中的审视记录；2026-11-05 归档 |

继续开发时，按专题查阅现行文档：

| 专题 | 现行文档 |
| --- | --- |
| 请求、数据版本与缓冲复用 | [生命周期](../interfaces/resource_lifecycle.md) |
| 模型覆盖、混合精度与成本归属 | [模型组合](../architecture/model_composition.md) |
| 工作量、持久状态与数值误差 | [完整工作与数值](../methods/workload_and_numeric_semantics.md) |
| 初态、到达过程、指标与校准 | [实验有效性](../methods/experiment_validity.md) |
| 端点、堆叠、热、良率与寿命 | [物理可行性](../architecture/physical_feasibility.md) |
| 可手算的边界案例 | [设计取舍示例](../methods/design_tradeoff_examples.md) |
| 实施优先级与验收条件 | [验证门槛](../architecture/validation.md) |

R01–R17 是当时识别的问题，不是已经逐项验收的任务清单。记录中的“本轮”“下一步”和原路径保留历史含义；当前状态见 [STATUS](../STATUS.md)，阅读入口见 [项目总览](../PROJECT_OVERVIEW.md)。
