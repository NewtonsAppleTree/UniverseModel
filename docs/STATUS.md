# 实现状态

核对日期：2026-11-06。代码基线：6b36384；本轮工作区新增通用配置/运行/记录/产物接口与全项目接入设计，保留已有 chipmodel 基础模型。

**已具备 chipmodel 基础模型与可独立使用的通用工程短路径。** configuration、contracts、evaluation、artifacts 已有严格参数解析、公共运行记录、单次注入调用和本地保存/校验；其他主模块仍以架构规范和骨架为主。完整模板配置、编译、软硬件执行、事件仿真、扫描与 UI 尚未形成端到端业务链。当前不包含 RTL，也不将分析时间界当作实际仿真时间。

## 能力与证据

| 能力 | 状态 | 验证或阅读入口 |
| --- | --- | --- |
| 模块目录与允许依赖 | 13 模块清单、依赖 DAG 与实际 Python import 检查 | [modules.json](architecture/modules.json)、[检查脚本](../tools/check_structure.py) |
| 架构及公共语义 | 已有设计文档；ExperimentSpec/Metric/RunRecord 与 canonical JSON v1 可用，硬件/计划/事件 schema 仍为提案 | [工程框架](../ENGINEERING_FRAMEWORK.md)、[公共值入口](../contracts/UNITS.md)、[公共契约](interfaces/contracts.md) |
| 通用独立运行 | 同一 JSON/显式覆盖与注入接口可独立运行 ADC、DMA；记录模式、假设、单位、未知值、输入身份和失败诊断 | [运行入口](../evaluation/experiments/runner/single.py)、[通用示例](../example/universal_demo.py) |
| 独立组件与局部仿真 | 各子模块可独立查询；已有局部资源/操作组合示例；公共事件驱动器与 BenchSpec schema 尚未实现 | [系统级设计](../chipmodel/docs/system_model_design.md)、[局部示例](../example/chipmodel_demo.py)、[事件接口提案](interfaces/component_protocols.md) |
| ADC 功能与分析 | 显式参数/单位/公式校验、均匀 offset-binary 电压量化、越限标记、无争用批次时序；无背压或电路成本 | [模型说明](../chipmodel/docs/adc_model.md)、[Python 实现](../chipmodel/compute/cim/periphery/adc.py)、[运行示例](../example/adc_demo.py) |
| 计算与 CIM | CPU μop 能力、GPU 静态驻留、GEMM 工作/MAC 服务、位串行动作、电导阵列/TIA、DAC、保持限制、最终位权累加；无 ISA 或动态调度 | [compute 参数入口](../chipmodel/compute/UNITS.md) |
| 存储与搬运 | SRAM/buffer/cache 几何、DRAM 组织/接口、隔离行读、NAND 几何/串行时延、DMA 服务与 TMA 布局；无缓存命中、刷新、FTL 或队列状态 | [memory](../chipmodel/memory/UNITS.md)、[control](../chipmodel/control/UNITS.md) |
| 互连与物理条件 | 无争用 NoC 路径、D2D 分包/编码、同层矩形校验、一阶热 RC；不覆盖协议状态机、多节点热或电路校准 | [interconnect](../chipmodel/interconnect/UNITS.md)、[packaging](../chipmodel/packaging/UNITS.md) |
| 系统组合与创建 | 身份/归属/静态端口兼容检查、摘要/细节计量选择、操作 DAG 和资源供给包络下界、显式小型注册表 | [composition](../chipmodel/composition/UNITS.md)、[registry](../chipmodel/registry/UNITS.md) |
| 仓库开发规则与参数文档 | 根目录/模块 AGENTS.md；chipmodel 全部 27 个目录与其他实际实现目录/祖先，共 38 个 UNITS.md 检查范围；字段/接口表从代码生成 | [规则](development/model_rules.md)、[总入口](../chipmodel/UNITS.md)、[检查工具](../tools/check_model_rules.py) |
| 顶层设计参数查阅 | 已整理计算/存储/互连、物理条件与 AI 工作量的候选参数、单位、公式和来源边界；不新增模型能力 | [参数清单](../ARCHITECTURE_PARAMETERS.md)，含 DDR/HBM/Flash、CIM 与原材料修正 |
| 训练/推理场景架构 | trainingArch/inferArch 已有 README 与 UNITS 参数入口，复用 13 个基础模块；未实现独立分析器、调度器或执行器 | [训练](../trainingArch/README.md)、[推理](../inferArch/README.md) |
| 张量区域与编译规约设计 | 已有维度/ROI/存储/partial 契约提案、切块与归并推导、手册统计和修订例；未实现 ROI schema、tiling pass 或 attention kernel | [区域契约](interfaces/tensor_regions.md)、[编译设计](../compiler/docs/tiling_and_reduction.md)、[审阅统计](reference/layout_roi_review.md) |
| 异构结构示例 | 可检查引用；不可作为执行配置 | [示例说明](../example/specs/README.md)、[结构 JSON](../example/specs/heterogeneous_topology.json) |
| 配置与 UI | 严格 JSON → 冻结嵌套 dataclass、默认/文件/调用覆盖、producer 构造校验可用；无模板继承、公式解释器、YAML、迁移或 UI | [配置入口](../configuration/UNITS.md)、[配置设计](../configuration/docs/design.md)、[UI 设计](../ui/docs/design.md) |
| 编译与未实现硬件机制 | 编译器仍是骨架；全部候选 Unit 并未穷尽实现，细化 CPU/GPU、协议/一致性、PHY 等仍需按研究问题加入 | [单元覆盖清单](../chipmodel/docs/component_inventory.md)、[Unit 类与参数设计](../chipmodel/docs/unit_model_design.md) |
| runtime 与 simulator | 无可运行的请求执行和事件引擎 | [运行时设计](../runtime/docs/design.md)、[仿真器设计](../simulator/docs/design.md) |
| 实验与产物 | 单次调用与小数据本地 bundle 可用；run.json + 最终 manifest，拒绝覆盖，读取重做哈希/身份/结构校验；无扫描器、blob/轨迹、checkpoint 恢复 | [实验入口](../evaluation/UNITS.md)、[产物入口](../artifacts/UNITS.md)、[产物规范](interfaces/artifacts.md) |
| Python 工程打包 | pyproject 声明 Python 3.10+ 与 13 模块查找范围；wheel 构建通过，包含 5 个已有 Python 实现的主模块，运行代码无外部依赖 | [pyproject.toml](../pyproject.toml)、[工程使用](../ENGINEERING_FRAMEWORK.md) |
| 文档构建 | 已有四个维护中的 Word 构建配置 | [构建清单](tools/documents.json)、[构建脚本](tools/build_docx.py) |
| 自动验证 | 本地 Python 3.12.4 下 60 项测试通过：44 项模型测试 + 16 项工程边界测试；CI 配置规则/结构检查、两个测试集、模型/通用示例与 wheel 构建 | [基础模型测试](../tests/chipmodel/test_models.py)、[ADC 测试](../tests/chipmodel/test_adc.py)、[工程测试](../tests/integration/test_framework.py)、[GitHub 工作流](../.github/workflows/structure.yml) |

结构检查只证明目录、允许依赖/实际 import、链接、示例引用和 Word 来源一致；规则检查只证明注释结构和参数文档同步。业务测试验证已声明的功能/分析语义，不构成电路精度或性能校准。通用 runner 不推进目标时间；BenchSpec、计划与事件格式仍是待实现约定。source_revision 默认 unrecorded，输入快照/哈希不等于完整源码可复现。

## 现在能运行的命令

在仓库根目录运行：

```text
python tools/check_structure.py
python tools/check_model_rules.py
python -m unittest discover -s tests/chipmodel -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_*.py" -v
python -m example.adc_demo
python -m example.chipmodel_demo
python -m example.universal_demo --case adc
python -m example.universal_demo --case dma --set inputs.payload_bytes=64
python docs/tools/build_docx.py --document overview
```

业务检查/示例使用 Python 3.10 及以上的标准库；最后一条需要 [文档依赖](tools/requirements.txt)。修改字段或定义说明后，用 `python tools/check_model_rules.py --write-docs` 刷新 UNITS.md 生成区。示例中的频率/服务参数是显式假设；`example/specs` 下的 JSON 仍不是可执行配置。通用示例使用独立的 `config/experiments/universal_*.json` schema。

## 下一步和更新规则

按用户最新方向，先完善 universal 的通用工程：模块能力/字段导出 → 最小 workload/硬件能力/plan 边界 → 独立校验与实验比较 → 按实际争用需求接入 runtime/simulator。各模块的输入输出、状态归属与最小接入顺序见[工程框架](../ENGINEERING_FRAMEWORK.md)。不先实现完整处理器或复杂事件/插件框架。

CIM array + DAC/ADC + 缓冲仍是后续局部台架：先验收精确整数 MatVec、数值/静态时序/字节/动作账本，再做 GEMM ROI 和单层训练/推理资源账本。本轮未实现 run_cim_matvec，71-cycle 与 lane 扩展时间仍是台架验收方案；步骤见[局部仿真规划](architecture/composable_simulation.md)与 [B/C 门槛](architecture/validation.md)。

BenchSpec 等新对象与计划生产者字段目前属于提案，现行公共契约的修订清单见上述规划第 10 节。代码级功能/事件模型先行，周期、RTL 与电路校准按[精度选择](architecture/instruction_and_fidelity.md)的触发条件加入。

每次能力发生变化，更新对应行、核对日期、代码基线和证据入口；部分可用时写明支持范围及尚未通过的验证。新增模块或改变依赖还要更新 [modules.json](architecture/modules.json)，该清单只记录结构信息。其他文档引用本页，不另行维护完成状态；参考资料的“首版建议”不等于已实现功能。其他变更的维护位置见[文档维护规则](README.md)。
