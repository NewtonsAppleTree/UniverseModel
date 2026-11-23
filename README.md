# UniverseModel

chipmodel CH1–CH10基础与统一验收已完成，覆盖、调用入口和后续证据条件见[完成报告](chipmodel/docs/completion.md)。

**面向 AI 与软硬件协同设计的通用计算架构研究与实验平台。**

UniverseModel 以 AI 部署、训练与推理加速为核心研究主线，支撑体系结构、AI 与 EDA 领域的原创研究和顶级会议论文，并探索研究成果的工业应用。通过可组合的建模、仿真、系统执行与评估方法，检验软硬件方案的可行性，解释收益、瓶颈和适用条件。

**顶层要求：[项目使命](PROJECT_MISSION.md)。** 长期使命、研究范围、通用性和证据要求在该文件唯一维护；当前阶段不以芯片流片为交付目标。

架构建模范围从独立组件延伸到芯片与集群，支持规划 CPU、GPU、NPU、CIM、3D CIM、双裸片、HBM/HBF、异构节点和多机多卡。`chipmodel` 放软件模型，当前不包含 RTL。

实现进度、可运行入口与验证证据统一见[实现状态](docs/STATUS.md)。设计文档描述目标行为，不能作为能力已经实现的证明。

已完成 [clustermodel](clustermodel/README.md) 的基础开发、横向覆盖和收尾优化，范围与验证见[交接报告](clustermodel/docs/completion.md)。**当前chipmodel已完成CH1–CH4首包**：资源契约与精度修复、SRAM访问/容量、搬运路径账本、数字Tile同预算对照与敏感性，见[实现用法与证据](chipmodel/docs/foundation_usage.md)。**CH5完整CIM局部台架也已完成**：电导编码、DAC/阵列/TIA/ADC/累加、共享读出与有限保持、资源/精度对照，见[CIM指南](chipmodel/docs/cim_bench.md)。[CH6计算能力与瓶颈解释](chipmodel/docs/compute_capabilities.md)已落地CPU阶段、GPU驻留/启动、NPU格式/尾批与供数消融；[CH7外存与缓存接入](chipmodel/docs/memory_access.md)已完成DRAM地址/profile与搬运、缓存LRU轨迹及NAND页缓冲/输出对照；[CH8 Tile/Die/Package组合](chipmodel/docs/assembly.md)已完成共享清单、多job计量、跨Die路径和同指标摘要；[CH9物理条件与成本证据](chipmodel/docs/physical_evidence.md)已完成精确来源查询、资源/面积/能量账本和外部功率热轨迹；器件校准与联合物理可行性按[开发计划](chipmodel/docs/development_plan.md)继续补证据。

**设计查阅：[芯片架构与 AI 训练/推理参数清单](ARCHITECTURE_PARAMETERS.md)。** 按计算、存储、互连及物理条件筛选参数，列明中英文术语、单位、公式、模块归属和来源；包括 DDR/HBM/Flash、CIM 外围与训练/推理资源账本。

仓库开发约定见 [AGENTS.md](AGENTS.md)。chipmodel 的系统关系、各子模块 Unit 与参数入口见 [UNITS.md](chipmodel/UNITS.md)，包含第一性约束、专业术语、单位、公式和覆盖范围。

**通用工程入口：[ENGINEERING_FRAMEWORK.md](ENGINEERING_FRAMEWORK.md)。** 说明各模块的输入输出、状态归属与接入顺序；现在可选择独立模型，解析 JSON/显式覆盖，记录并保存一次运行。

## 先读哪些文档

先读[项目使命](PROJECT_MISSION.md)了解研究目标和顶层要求，再读[项目总览](docs/PROJECT_OVERVIEW.md)，了解各模块怎样服务研究、软件与物理层级、输入输出、数据格式和实验路径。具体规范按需查阅：

1. [顶层架构](docs/architecture/design.md)：模块边界、状态归属和完整信息链。
2. [第一性原理](docs/architecture/first_principles.md)：整个项目与各模块最核心的问题。
3. [分场景推演](docs/architecture/scenarios.md)：单芯片、CIM、3D、HBF、异构与集群。
4. [公共契约](docs/interfaces/contracts.md)与[产物规范](docs/interfaces/artifacts.md)：交换什么、如何保存和复现。
5. [参数与数学方法](docs/methods/parameters_and_math.md)、[工作流](docs/methods/workflows.md)、[优化方法](docs/methods/optimization.md)。
6. [完整文档索引](docs/README.md)：当前规范、专题参考、历史记录与 Word 阅读版。

参数如何修改和可视化，见 [configuration 设计](configuration/docs/design.md)与 [ui 设计](ui/docs/design.md)。先共享参数定义、派生与校验规则，再实现文本/CLI 和表单、拓扑、映射、时间线。

## 基础模块导航

| 模块 | 职责 | 设计入口 |
| --- | --- | --- |
| contracts | 公共对象、单位、版本、端口协议 | [设计](contracts/docs/design.md) |
| configuration | 参数定义、组合、派生、验证与冻结 | [设计](configuration/docs/design.md) |
| costmodel | 条件成本、特征化与不确定性 | [设计](costmodel/docs/design.md) |
| chipmodel | 计算/存储/NoC/D2D、Tile/Die/Package | [设计](chipmodel/docs/design.md) |
| systemmodel | 板卡/节点、主机/NUMA、PCIe/CXL/DMA/NIC | [设计](systemmodel/docs/design.md) |
| clustermodel | 节点间网络、交换机、路由与资源组 | [设计](clustermodel/docs/design.md)、[开发计划](clustermodel/docs/development_plan.md)、[参数](clustermodel/UNITS.md) |
| workloads | 任务语义、输入分布与独立参考 | [设计](workloads/docs/design.md) |
| compiler | IR、划分、切块、放置、内存规划与静态计划 | [设计](compiler/docs/design.md) |
| runtime | 软件派发、streams、动态策略与集合通信 | [设计](runtime/docs/design.md) |
| simulator | 时间、事件、统计、轨迹与终止 | [设计](simulator/docs/design.md) |
| artifacts | 序列化、清单、存储和来源 | [设计](artifacts/docs/design.md) |
| evaluation | 装配实验、校准、参数扫描与优化 | [设计](evaluation/docs/design.md) |
| ui | 同一参数定义上的表单和结果解释 | [设计](ui/docs/design.md) |

每个模块的 README 列出子目录，docs/design.md 说明职责、参数、依赖、输入输出、场景与验证。完整结构清单见 [modules.json](docs/architecture/modules.json)，关系图见[架构图](docs/architecture/diagrams.md)。目录是职责划分，实际硬件实例由未来配置决定。

训练与推理另有场景架构入口：[trainingArch](trainingArch/README.md) 聚焦训练阶段、显存、并行与通信，[inferArch](inferArch/README.md) 聚焦 prefill/decode、KV cache、延迟与吞吐。当前为文档入口，复用上述 13 个基础模块；各自的 UNITS.md 导航到相关参数，不另建重复的硬件模型。

## 支撑目录

```text
config/       硬件、成本、编译、运行、仿真与实验配置文件
data/         输入、校准来源和运行产物
tests/        契约、模型、系统与集成验证归属
example/      通用配置/运行示例、独立模型示例、结构示例
docs/         顶层架构、契约、方法、决策和 Word 文档
tools/        结构一致性等开发工具
```

## 当前可运行的示例与检查

在仓库根目录使用 Python 3.10 或更高版本，无需安装业务依赖：

```text
python tools/check_structure.py
python tools/check_model_rules.py
python -m unittest discover -s tests/chipmodel -p "test_*.py" -v
python -m unittest discover -s tests/workloads -p "test_*.py" -v
python -m unittest discover -s compiler/tests -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_*.py" -v
python -m example.adc_demo
python -m example.chipmodel_demo
python -m example.digital_tile_demo
python -m example.cim_demo
python -m example.memory_demo
python -m example.assembly_demo
python -m example.physical_demo
python -m example.universal_demo --case adc
python -m example.universal_demo --case dma --set inputs.payload_bytes=64
python -m example.linear_demo
python -m example.training_demo
```

结构检查覆盖目录、实际 Python 模块依赖、文档链接和 Word 源哈希；模型规则检查覆盖已实现模块的定义/字段注释与参数文档。测试和示例验证局部模型及工程约束，使用方法见 [Unit 总入口](chipmodel/UNITS.md)。分析下界不等于实际运行时间，这些检查也不证明电路可实现性或成本精度。

跨目录导入代码可选择 `python -m pip install -e .`；包定义见 [pyproject.toml](pyproject.toml)。示例与配置从仓库根目录运行；通用示例支持 `--config`、`--set`、`--output` 与显式 `--source-revision`。

[线性算子实验](evaluation/docs/linear_mapping.md)已贯通可复现输入、两种分块策略、容量/流量、功能参考、MAC/DMA 分析和产物回读。默认同一 GEMM 的两个方案分别搬运 314/954 B，校验均通过；超容量候选保留失败原因。资源时间只报告分析下界，能耗未知。实现批次与验收见[开发计划](docs/development/linear_experiment_plan.md)。

## 文档维护与后续开发

[训练 step 与短链](evaluation/docs/training_step.md)已支持 Linear/ReLU、mean MSE、全部 dW/dX 与 SGD，检查权重版本和张量生命周期，并用 PyTorch 2.5.1 CPU autograd/SGD 做独立功能对照。默认执行只需标准库；完整训练时间/能耗未知。本批验收见[训练开发计划](docs/development/training_step_plan.md)，项目模块顺序仍以路线当前安排为准。

Markdown 是正文维护源；Word 阅读版集中在 docs/exports，参数与异构手册在 docs/reference，历史审视在 docs/archive。阅读与构建入口统一见[文档索引](docs/README.md)。

近期工作按[研究开发路线](docs/RESEARCH_ROADMAP.md)推进：在小型 AI 线性算子实验基础上扩展训练最小语义，并完成外部基线复现与校准。[开源项目调研](docs/reference/open_source_landscape.md)记录引用与选型依据，[候选全量清单](docs/reference/open_source_comparison.md)按模块横向比较 GitHub 热度、维护状态与能力边界，收录与接入优先级分开；已实现能力和当前缺口见[实现状态](docs/STATUS.md)，模型阶段门槛见[验证规范](docs/architecture/validation.md)。
