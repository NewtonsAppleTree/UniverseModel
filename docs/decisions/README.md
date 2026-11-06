# 已采用的架构决策

这里记录已选择的设计边界及理由；采用决策不代表对应功能已实现，完成情况见[实现状态](../STATUS.md)。ADR-010 记录初始交付范围。

| 编号 | 决策 | 理由与代价 |
| --- | --- | --- |
| ADR-001 | chipmodel 到 Package；systemmodel 到 Node；clustermodel 管 Fabric | 共享瓶颈与状态所有者明确；需公共组合协议 |
| ADR-002 | 将 contracts、configuration、costmodel、artifacts 独立 | 参数解释、条件成本、信息语义和证据不随引擎实现漂移 |
| ADR-003 | runtime 与 simulator 分开，evaluation 负责装配 | 策略可替换，时间语义稳定；接口需明确背压和完成 |
| ADR-004 | 物理包含、连接、地址/一致性、放置和热关系分开 | 同时表达双 Die、3D 与逻辑设备；增加关系校验工作 |
| ADR-005 | CIM 同时可作资源族和 NPU 内机制，3D 用组合关系表达 | 避免互斥枚举限制架构；字段需条件化 |
| ADR-006 | HBF 为独立 Flash 能力，不推定 CIM/HBM 语义 | 必须基于具体规格建模访问路径 |
| ADR-007 | 已冻结配置/计划/核心产物不可变，DataRef 显式位置与版本 | 保持复现和真实搬运；需要清单与版本管理 |
| ADR-008 | 先结构/功能/事件闭环，再按敏感性细化 | 控制复杂度；早期结论必须声明精度范围 |
| ADR-009 | UI 从配置定义生成，先 CLI/文本后图形 | 用户可灵活修改且只有一套语义；前期需参数元数据 |
| ADR-010 | 初始交付先提供骨架、规范和检查，不引入 RTL 与空壳业务 API | 为后续实现提供明确边界，避免把占位代码当能力 |
| ADR-011 | 接收、源消费、目标可见与取消终态分开 | 异步搬运和地址复用需要明确生命周期；见[生命周期规范](../interfaces/resource_lifecycle.md) |
| ADR-012 | 模型覆盖按维度声明，成本项指定唯一计入方 | 摘要与细模型可组合且不重复收费；见[组合规则](../architecture/model_composition.md) |
| ADR-013 | 运行状态、功能验证与估计覆盖分开 | 性能元数据执行不自动证明数值正确；见[实验有效性](../methods/experiment_validity.md) |
| ADR-014 | 使用 P0/P1/P2 管理补充细节，保留现有主模块 | 根据接口影响和研究场景增加能力；规则见[验证规范](../architecture/validation.md)，讨论来源见[历史审视](../archive/2026-10-30_architecture_review.md) |
| ADR-015 | 独立组件与局部子图作为正式使用方式，完整实验链按需装配 | 允许直接激励、已有计划和轨迹输入；切口需显式边界模型，见[局部仿真规划](../architecture/composable_simulation.md)；字段仍待最小用例验证 |
| ADR-016 | 首批研究选择 CIM array、DAC/ADC 与缓冲，数字路径作为可选对照 | 先验证数值与共享资源，不把完整编译器、整机或 RTL 作为前置条件；见[指令与精度规划](../architecture/instruction_and_fidelity.md) |

改变决策时新增记录，说明问题、备选、影响的契约/参数、迁移与验证要求。旧记录保留为被替代状态，不直接抹掉原因。
