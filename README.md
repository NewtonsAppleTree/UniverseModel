# UniverseModel

芯片到集群的架构建模工程，覆盖架构定义、工作负载映射、功能验证、性能与成本评估。支持规划 CPU、GPU、NPU、CIM、3D CIM、双裸片、HBM/HBF、异构节点和多机多卡。`chipmodel` 放软件模型，当前不包含 RTL。

实现进度、可运行入口与验证证据统一见[实现状态](docs/STATUS.md)。设计文档描述目标行为，不能作为能力已经实现的证明。

**设计查阅：[芯片架构与 AI 训练/推理参数清单](ARCHITECTURE_PARAMETERS.md)。** 按计算、存储、互连及物理条件筛选参数，列明中英文术语、单位、公式、模块归属和来源；包括 DDR/HBM/Flash、CIM 外围与训练/推理资源账本。

仓库开发约定见 [AGENTS.md](AGENTS.md)。chipmodel 的系统关系、各子模块 Unit 与参数入口见 [UNITS.md](chipmodel/UNITS.md)，包含第一性约束、专业术语、单位、公式和覆盖范围。

**通用工程入口：[ENGINEERING_FRAMEWORK.md](ENGINEERING_FRAMEWORK.md)。** 说明各模块的输入输出、状态归属与接入顺序；现在可选择独立模型，解析 JSON/显式覆盖，记录并保存一次运行。

## 先读哪些文档

**总入口：[项目总览](docs/PROJECT_OVERVIEW.md)。** 按软件与物理层级说明全部目录、13 个模块的输入处理输出、数据格式、完整实验链，以及不同工作应调用哪些模块。先读这份，再按需要查下面的规范。

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
| clustermodel | 节点间网络、交换机、路由与资源组 | [设计](clustermodel/docs/design.md) |
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
python -m unittest discover -s tests/integration -p "test_*.py" -v
python -m example.adc_demo
python -m example.chipmodel_demo
python -m example.universal_demo --case adc
python -m example.universal_demo --case dma --set inputs.payload_bytes=64
```

结构检查覆盖目录、实际 Python 模块依赖、文档链接和 Word 源哈希；模型规则检查覆盖已实现模块的定义/字段注释与参数文档。测试和示例验证局部模型及工程约束，使用方法见 [Unit 总入口](chipmodel/UNITS.md)。分析下界不等于实际运行时间，这些检查也不证明电路可实现性或成本精度。

跨目录导入代码可选择 `python -m pip install -e .`；包定义见 [pyproject.toml](pyproject.toml)。示例与配置从仓库根目录运行；通用示例支持 `--config`、`--set`、`--output` 与显式 `--source-revision`。

## 文档维护与后续开发

Markdown 是正文维护源；Word 阅读版集中在 docs/exports，参数与异构手册在 docs/reference，历史审视在 docs/archive。阅读与构建入口统一见[文档索引](docs/README.md)。

开发顺序与当前缺口见[实现状态](docs/STATUS.md)，阶段门槛见[验证规范](docs/architecture/validation.md)。
