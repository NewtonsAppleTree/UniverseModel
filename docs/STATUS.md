# 实现状态

核对日期：2026-11-06。代码基线：0fe8cc1；工作区新增 chipmodel 各子模块的基础参数/公式模型、系统关系检查、仓库规则与逐目录文档。

**chipmodel 已进入基础模型实现阶段，其余主模块仍以架构规范和骨架为主。** 参数/公式、必要功能参考与局部组合可独立调用；完整配置解析、编译、软硬件执行、事件仿真、实验管理与图形界面尚未形成端到端业务链。当前不包含 RTL，也不将分析时间界当作实际仿真时间。

## 能力与证据

| 能力 | 状态 | 验证或阅读入口 |
| --- | --- | --- |
| 模块目录与允许依赖 | 已有清单和结构检查 | [modules.json](architecture/modules.json)、[检查脚本](../tools/check_structure.py) |
| 架构及公共语义 | 已有设计文档，尚无可执行业务 schema | [架构设计](architecture/design.md)、[公共契约](interfaces/contracts.md) |
| 独立组件与局部仿真 | 各子模块可独立查询；已有局部资源/操作组合示例；公共事件驱动器与 BenchSpec schema 尚未实现 | [系统级设计](../chipmodel/docs/system_model_design.md)、[局部示例](../example/chipmodel_demo.py)、[事件接口提案](interfaces/component_protocols.md) |
| ADC 功能与分析 | 显式参数/单位/公式校验、均匀 offset-binary 电压量化、越限标记、无争用批次时序；无背压或电路成本 | [模型说明](../chipmodel/docs/adc_model.md)、[Python 实现](../chipmodel/compute/cim/periphery/adc.py)、[运行示例](../example/adc_demo.py) |
| 计算与 CIM | CPU μop 能力、GPU 静态驻留、GEMM 工作/MAC 服务、位串行动作、电导阵列/TIA、DAC、保持限制、最终位权累加；无 ISA 或动态调度 | [compute 参数入口](../chipmodel/compute/UNITS.md) |
| 存储与搬运 | SRAM/buffer/cache 几何、DRAM 组织/接口、隔离行读、NAND 几何/串行时延、DMA 服务与 TMA 布局；无缓存命中、刷新、FTL 或队列状态 | [memory](../chipmodel/memory/UNITS.md)、[control](../chipmodel/control/UNITS.md) |
| 互连与物理条件 | 无争用 NoC 路径、D2D 分包/编码、同层矩形校验、一阶热 RC；不覆盖协议状态机、多节点热或电路校准 | [interconnect](../chipmodel/interconnect/UNITS.md)、[packaging](../chipmodel/packaging/UNITS.md) |
| 系统组合与创建 | 身份/归属/静态端口兼容检查、摘要/细节计量选择、操作 DAG 和资源供给包络下界、显式小型注册表 | [composition](../chipmodel/composition/UNITS.md)、[registry](../chipmodel/registry/UNITS.md) |
| 仓库开发规则与参数文档 | 根目录/模块 AGENTS.md、统一规则、chipmodel 全部 27 个目录的 UNITS.md；字段/接口表从代码生成并检查同步 | [规则](development/model_rules.md)、[总入口](../chipmodel/UNITS.md)、[检查工具](../tools/check_model_rules.py) |
| 顶层设计参数查阅 | 已整理计算/存储/互连、物理条件与 AI 工作量的候选参数、单位、公式和来源边界；不新增模型能力 | [参数清单](../ARCHITECTURE_PARAMETERS.md)，含 DDR/HBM/Flash、CIM 与原材料修正 |
| 训练/推理场景架构 | trainingArch/inferArch 已有 README 与 UNITS 参数入口，复用 13 个基础模块；未实现独立分析器、调度器或执行器 | [训练](../trainingArch/README.md)、[推理](../inferArch/README.md) |
| 异构结构示例 | 可检查引用；不可作为执行配置 | [示例说明](../example/specs/README.md)、[结构 JSON](../example/specs/heterogeneous_topology.json) |
| 配置与 UI | 解析器、表单和运行入口未实现 | [配置设计](../configuration/docs/design.md)、[UI 设计](../ui/docs/design.md) |
| 编译与未实现硬件机制 | 编译器仍是骨架；全部候选 Unit 并未穷尽实现，细化 CPU/GPU、协议/一致性、PHY 等仍需按研究问题加入 | [单元覆盖清单](../chipmodel/docs/component_inventory.md)、[Unit 类与参数设计](../chipmodel/docs/unit_model_design.md) |
| runtime 与 simulator | 无可运行的请求执行和事件引擎 | [运行时设计](../runtime/docs/design.md)、[仿真器设计](../simulator/docs/design.md) |
| 实验与产物 | 实验器、扫描器、运行写入器未实现 | [实验设计](../evaluation/docs/design.md)、[产物规范](interfaces/artifacts.md) |
| 文档构建 | 已有四个维护中的 Word 构建配置 | [构建清单](tools/documents.json)、[构建脚本](tools/build_docx.py) |
| 自动验证 | 本地 Python 3.12.4 下 44 项测试通过，覆盖独立数值参考、手算、容量/单位/依赖/计量反例；CI 已配置规则/结构检查、测试和两个示例 | [基础模型测试](../tests/chipmodel/test_models.py)、[ADC 测试](../tests/chipmodel/test_adc.py)、[GitHub 工作流](../.github/workflows/structure.yml) |

结构检查只证明目录、依赖图、链接、示例引用和 Word 来源一致；规则检查只证明注释结构和参数文档同步。业务测试验证已声明的功能/分析语义，不构成电路精度或性能校准。代码中没有统一事件仿真启动命令，BenchSpec、计划与事件格式仍是待实现约定。

## 现在能运行的命令

在仓库根目录运行：

```text
python tools/check_structure.py
python tools/check_model_rules.py
python -m unittest discover -s tests/chipmodel -p "test_*.py" -v
python -m example.adc_demo
python -m example.chipmodel_demo
python docs/tools/build_docx.py --document overview
```

前五条使用 Python 3.10 及以上的标准库；最后一条需要 [文档依赖](tools/requirements.txt)。修改字段或定义说明后，用 `python tools/check_model_rules.py --write-docs` 刷新 UNITS.md 生成区。示例中的频率/服务参数是显式假设；`example/specs` 下的 JSON 仍不是可执行配置。

## 下一步和更新规则

接下来按研究敏感性细化，优先保留 CIM array + DAC/ADC + 缓冲路径：明确具体工作负载和精度目标 → 对齐等效列和/电压两类数值配置 → 在确实影响结论时加入采样保持、有限在途/输出、源租约和背压 → 对齐已有 MatVec 手算夹具。避免先实现完整处理器或通用事件框架；步骤与验收见[局部仿真规划](architecture/composable_simulation.md)和 [B/C 门槛](architecture/validation.md)。

BenchSpec 等新对象与计划生产者字段目前属于提案，现行公共契约的修订清单见上述规划第 10 节。代码级功能/事件模型先行，周期、RTL 与电路校准按[精度选择](architecture/instruction_and_fidelity.md)的触发条件加入。

每次能力发生变化，更新对应行、核对日期、代码基线和证据入口；部分可用时写明支持范围及尚未通过的验证。新增模块或改变依赖还要更新 [modules.json](architecture/modules.json)，该清单只记录结构信息。其他文档引用本页，不另行维护完成状态；参考资料的“首版建议”不等于已实现功能。其他变更的维护位置见[文档维护规则](README.md)。
