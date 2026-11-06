# 背景参考

这里保存术语、参数来源和架构方案的背景材料。它们帮助理解设计选择；模块边界以 [架构规范](../architecture/design.md)为准，数据对象以 [公共契约](../interfaces/contracts.md)为准，可执行能力以 [实现状态](../STATUS.md)为准。

| 文档 | 用途 |
| --- | --- |
| [结构参数手册](architecture_parameters.md) | 中英文名词、参数族、公开工具和来源 |
| [异构芯片封装与集群参考](heterogeneous_cluster_plan.md) | CPU/GPU/NPU/CIM、3D、HBF、双裸片和多机的设计情景 |
| [硬件组件目录](hardware_component_catalog.md) | 计算、CIM 外围、存储、搬运、控制、互连的输入输出、技术指标与建议归属 |
| [chipmodel 子系统与单元覆盖清单](../../chipmodel/docs/component_inventory.md) | 八个直接子目录下的候选单元、DDR 路径及状态归属 |

背景文档中的模型层级、参数集合和首版范围是设计建议。实现采用某项建议时，应在对应模块设计、公共契约和验证依据中落定；引用的外部规格要记录其实际版本和适用条件。
