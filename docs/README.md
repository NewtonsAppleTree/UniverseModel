# 文档入口

先读 [项目总览](PROJECT_OVERVIEW.md)了解模块、输入输出和任务路线；查看 [实现状态](STATUS.md)确认哪些能力已经可用。设计文档说明应当怎样工作，STATUS 记录实际完成情况。

通用工程接口、各模块接入与实现顺序从[ENGINEERING_FRAMEWORK.md](../ENGINEERING_FRAMEWORK.md)进入。当前先完善可独立使用的工程框架；CIM array + DAC/ADC + 缓冲台架保留为后续验收。

搭建组件台架或设计硬件接口时，再查[可组合组件与局部仿真规划](architecture/composable_simulation.md)；其公共事件接口与 BenchSpec 样例仍为设计提案。独立 ADC 的代码与运行方法见[模型说明](../chipmodel/docs/adc_model.md)。

## 目录分工

```text
docs/
  README.md              文档入口与维护规则
  PROJECT_OVERVIEW.md     整体逻辑 模块输入输出 任务路线
  STATUS.md              当前实现状态 验证依据 下一步
  architecture/          架构规范 关系图 场景 验证门槛
  interfaces/            公共对象 生命周期 产物协议
  methods/               参数公式 实验方法 优化与手算案例
  reference/             参数手册与异构背景参考
  decisions/             架构决策及选择理由
  exports/               由维护源生成的 Word 阅读版
  archive/               历史审视记录 不作为当前进度依据
  tools/                 Word 构建脚本与来源清单
```

## 按问题阅读

| 想确认什么 | 阅读入口 |
| --- | --- |
| 项目整体怎样运转 | [项目总览](PROJECT_OVERVIEW.md) |
| 现在能运行什么 | [实现状态](STATUS.md) |
| 设计时该选哪些参数、单位与公式 | 根目录[芯片架构与 AI 参数清单](../ARCHITECTURE_PARAMETERS.md)：计算、存储、互连、物理条件与训练/推理资源账本 |
| 训练与推理场景从哪里进入 | [trainingArch](../trainingArch/README.md)、[inferArch](../inferArch/README.md)：各自的阶段、资源账本与参数入口 |
| 怎样跳过完整链条只运行局部组件 | [可组合仿真规划](architecture/composable_simulation.md) |
| 组件输入输出和端口怎样配置 | [组件接口提案](interfaces/component_protocols.md) |
| ADC、DMA、缓存、存储与互连放在哪里 | [硬件组件目录](reference/hardware_component_catalog.md) |
| chipmodel 每个目录还应包含哪些单元 | [逐目录覆盖清单](../chipmodel/docs/component_inventory.md)，包括 DDR/LPDDR/GDDR、控制器/PHY 与处理器内部单元 |
| Unit 用什么语言 怎样写类和参数 | [Unit 类与参数设计](../chipmodel/docs/unit_model_design.md)：参数、派生值、状态、单位、接口与使用顺序 |
| 所有模块的代码/注释/文档规则 | [统一模型规则](development/model_rules.md)、[仓库 AGENTS.md](../AGENTS.md) |
| 芯片和 AI 训练/推理怎样系统化建模 | [chipmodel 系统级设计](../chipmodel/docs/system_model_design.md)、[各子模块参数入口](../chipmodel/UNITS.md) |
| 怎样只运行 ADC 并修改参数 | [ADC 模型与用法](../chipmodel/docs/adc_model.md)：字段注释、公式、输入输出、理想时序与数值边界 |
| 怎样设计指令 是否需要 RTL | [指令与仿真精度](architecture/instruction_and_fidelity.md) |
| 模块边界和代码依赖 | [架构设计](architecture/design.md)、[关系图](architecture/diagrams.md)、[模块清单](architecture/modules.json) |
| 模块交换什么信息 | [公共契约](interfaces/contracts.md)、[数据生命周期](interfaces/resource_lifecycle.md) |
| 张量维度、ROI、切块与规约如何设计 | [张量区域契约](interfaces/tensor_regions.md)、[编译器切块设计](../compiler/docs/tiling_and_reduction.md)、[layout_roi 审阅统计](reference/layout_roi_review.md) |
| 数据如何保存与复现 | [产物规范](interfaces/artifacts.md) |
| 参数怎样计算和修改 | [参数与公式](methods/parameters_and_math.md)、[工作流](methods/workflows.md) |
| 模型怎样组合及验证 | [模型组合](architecture/model_composition.md)、[验证门槛](architecture/validation.md)、[手算案例](methods/design_tradeoff_examples.md) |
| 端到端比较是否可信 | [完整工作与数值](methods/workload_and_numeric_semantics.md)、[实验有效性](methods/experiment_validity.md)、[优化方法](methods/optimization.md) |
| CIM 或多芯片多机怎样组织 | [场景推演](architecture/scenarios.md)、[物理可行性](architecture/physical_feasibility.md) |
| 英文术语与公开资料 | [参考资料索引](reference/README.md) |
| 核心判断和决策理由 | [第一性原理](architecture/first_principles.md)、[架构决策](decisions/README.md) |
| 过去讨论过哪些问题 | [归档索引](archive/README.md) |

各模块的细化设计仍保留在对应模块的 docs/design.md，总览中有完整导航。

## 怎样避免再次过时

按本次改动选择维护位置，避免在多份文档中复制进度或接口定义：

| 发生的变化 | 更新位置 |
| --- | --- |
| 功能新增、部分可用或验证结果变化 | [STATUS.md](STATUS.md)：支持范围、核对日期、代码基线和验证入口；总览与模块 README 引用它 |
| 模块职责、目录或允许依赖变化 | [架构设计](architecture/design.md)、[模块清单](architecture/modules.json)、[依赖图](architecture/diagrams.md)及受影响的模块设计；总览同步导航 |
| 公共字段、单位或生命周期变化 | [公共契约](interfaces/contracts.md)及对应接口专题；模块设计引用共同定义 |
| 候选参数、物理关系或来源解释变化 | 根目录[参数清单](../ARCHITECTURE_PARAMETERS.md)；实际字段仍由代码和各目录 UNITS.md 维护，不在清单复制配置 schema |
| 算法、成本或实验条件变化 | 对应 methods 文档及模块设计；改变已有决策时在 [decisions](decisions/README.md)记录替代关系 |
| 文档移动、改名或归档 | 本索引、所有引用及 [Word 构建清单](tools/documents.json)；归档索引注明来源与现行规范入口 |

modules.json 只维护目录与依赖等结构信息，实现状态集中在 STATUS.md。参考手册说明候选结构与依据；历史审视归档后保留原样，其中的“当前”“下一步”仅指记录形成时。

Markdown 是维护源，exports 中的 Word 通过构建生成。开发中先改源文件，提交前更新受影响 Word 并检查排版。

发现冲突时按问题定位：实现能力查 STATUS 和代码证据；接口语义查 interfaces；模块归属查 architecture 和模块设计。参考资料和历史记录不能覆盖这些约定。检查工具能发现路径和源哈希问题，内容是否与实现一致仍需变更时核对。

## Word 阅读版与构建

| 构建名称（--document） | 阅读版 | 维护源 |
| --- | --- | --- |
| overview | [项目总览](exports/UniverseModel_Project_Overview.docx) | [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) |
| design | [工程设计](exports/UniverseModel_Design.docx) | [架构设计](architecture/design.md)、[公共契约](interfaces/contracts.md)、[验证门槛](architecture/validation.md) |
| parameters | [结构参数手册](exports/UniverseModel_Architecture_Parameters.docx) | [结构参数参考](reference/architecture_parameters.md) |
| scaling | [异构与集群参考](exports/UniverseModel_Heterogeneous_Cluster_Plan.docx) | [异构扩展参考](reference/heterogeneous_cluster_plan.md) |

构建配置见 [documents.json](tools/documents.json)，依赖见 [requirements.txt](tools/requirements.txt)。使用 Python 3.10 及以上版本，在仓库根目录首次安装文档依赖：

```text
python -m pip install -r docs/tools/requirements.txt
```

按上表选择受影响的构建名称，例如修改总览后运行：

```text
python docs/tools/build_docx.py --document overview
python tools/check_structure.py
```

只改索引、STATUS 或其他未列入维护源的文档时，运行结构检查即可，无需重建 Word。移动维护源、阅读版或它们引用的文件时，也应重建受影响的阅读版，以更新相对链接。归档阅读版不参与日常构建。

构建器写入 Markdown 来源哈希，检查工具核对同步；该哈希不校验 Word 排版或其中的链接。Markdown 检查只覆盖本地文件链接，不验证标题锚点和外部网站。生成 Word 后仍需渲染并逐页检查字体、表格与分页，图片和 PDF 放入 .build。Mermaid 图保留在 Markdown，现有 Word 构建器不渲染它们。
