# 实现状态

核对日期：2026-11-05。代码基线：551d3a8；工作区新增局部仿真、组件接口与指令精度规划，未新增可执行业务能力。

**项目处于架构规范与工程骨架阶段。** 13 个主模块已经确定目录和设计责任；配置解析、编译、软硬件执行、仿真、实验管理与图形界面尚未形成可运行业务链。chipmodel 的范围是软件架构模型，当前不包含 RTL。

## 能力与证据

| 能力 | 状态 | 验证或阅读入口 |
| --- | --- | --- |
| 模块目录与允许依赖 | 已有清单和结构检查 | [modules.json](architecture/modules.json)、[检查脚本](../tools/check_structure.py) |
| 架构及公共语义 | 已有设计文档，尚无可执行业务 schema | [架构设计](architecture/design.md)、[公共契约](interfaces/contracts.md) |
| 独立组件与局部仿真 | 已有方案、接口提案与 CIM 手算夹具；驱动器、组件 API 和相应 schema 未实现 | [局部仿真规划](architecture/composable_simulation.md)、[组件接口](interfaces/component_protocols.md)、[结构样例](../example/specs/component_bench.json) |
| 异构结构示例 | 可检查引用；不可作为执行配置 | [示例说明](../example/specs/README.md)、[结构 JSON](../example/specs/heterogeneous_topology.json) |
| 配置与 UI | 解析器、表单和运行入口未实现 | [配置设计](../configuration/docs/design.md)、[UI 设计](../ui/docs/design.md) |
| 编译与硬件模型 | 业务实现未完成；已有单元目录、类/参数/接口设计，目录表示职责预留 | [单元覆盖清单](../chipmodel/docs/component_inventory.md)、[Unit 类与参数设计](../chipmodel/docs/unit_model_design.md) |
| runtime 与 simulator | 无可运行的请求执行和事件引擎 | [运行时设计](../runtime/docs/design.md)、[仿真器设计](../simulator/docs/design.md) |
| 实验与产物 | 实验器、扫描器、运行写入器未实现 | [实验设计](../evaluation/docs/design.md)、[产物规范](interfaces/artifacts.md) |
| 文档构建 | 已有四个维护中的 Word 构建配置 | [构建清单](tools/documents.json)、[构建脚本](tools/build_docx.py) |
| 自动验证 | 结构与文档检查可执行；业务验证套件未实现 | [GitHub 工作流](../.github/workflows/structure.yml)、[验证门槛](architecture/validation.md) |

结构检查通过，只证明目录、依赖图、链接、示例引用和 Word 来源一致，不证明功能正确或性能可信。代码中没有统一仿真启动命令，文档中的 JSON/YAML、计划与事件格式仍是待实现约定。

## 现在能运行的命令

在仓库根目录运行：

```text
python tools/check_structure.py
python docs/tools/build_docx.py --document overview
```

第一条使用 Python 3.10 及以上的标准库；第二条需要 [文档依赖](tools/requirements.txt)。其他 Word 配置和阅读入口见 [文档索引](README.md)。

## 下一步和更新规则

首批按本轮研究选择实现 CIM array + DAC/ADC + 缓冲的局部 MatVec：明确差分/位串行数值规则 → 公共端口与直接激励 → 独立参考 → 采样保持、ADC 共享、累加和有限缓冲事件验证。无需先实现完整编译器、runtime 或数字 NPU；数字 GEMM 路径保留为可选对照。步骤与验收夹具见[局部仿真规划](architecture/composable_simulation.md)，总体仍按 [B/C 阶段门槛](architecture/validation.md)推进。

BenchSpec 等新对象与计划生产者字段目前属于提案，现行公共契约的修订清单见上述规划第 10 节。代码级功能/事件模型先行，周期、RTL 与电路校准按[精度选择](architecture/instruction_and_fidelity.md)的触发条件加入。

每次能力发生变化，更新对应行、核对日期、代码基线和证据入口；部分可用时写明支持范围及尚未通过的验证。新增模块或改变依赖还要更新 [modules.json](architecture/modules.json)，该清单只记录结构信息。其他文档引用本页，不另行维护完成状态；参考资料的“首版建议”不等于已实现功能。其他变更的维护位置见[文档维护规则](README.md)。
