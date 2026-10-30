# 文档索引与维护

## 阅读与权威范围

| 层次 | 文档 | 回答的问题 |
| --- | --- | --- |
| 顶层 | [架构设计](architecture/design.md)、[关系图](architecture/diagrams.md) | 模块怎样分工和装配 |
| 语义 | [公共契约](interfaces/contracts.md)、[产物规范](interfaces/artifacts.md) | 信息交换、状态和复现 |
| 方法 | [参数与公式](methods/parameters_and_math.md)、[工作流](methods/workflows.md)、[优化](methods/optimization.md) | 怎样计算、比较和改进 |
| 场景 | [分场景推演](architecture/scenarios.md)、[异构规划](architecture/heterogeneous_cluster_plan.md) | CIM/3D/HBF/双 Die/异构/集群怎么组合 |
| 依据 | [结构参数手册](architecture/architecture_parameters.md) | 英文术语、参数族和来源 |
| 判断 | [第一性原理](architecture/first_principles.md)、[验证](architecture/validation.md) | 核心问题、可信度与阶段门槛 |
| 决策 | [架构决策](decisions/README.md) | 已选边界和选择理由 |

各主模块有自己的 README 与 docs/design.md，从[仓库导航](../README.md)进入。顶层架构规定边界，公共契约规定交换语义，模块设计细化本模块；参数手册和异构规划提供背景与方案。实现状态以仓库 README 和验证阶段为准，规划描述不代表模型已可执行。

结构清单 [modules.json](architecture/modules.json) 是模块目录与公开依赖的机器可读清单。改变边界时同步更新清单、顶层文档与模块设计；正文以 Markdown 为源，不单独改 Word。

## Word 来源

| 输出 | 维护源 |
| --- | --- |
| [UniverseModel_Design.docx](UniverseModel_Design.docx) | architecture/design.md、interfaces/contracts.md、architecture/validation.md |
| [UniverseModel_Architecture_Parameters.docx](UniverseModel_Architecture_Parameters.docx) | architecture/architecture_parameters.md |
| [UniverseModel_Heterogeneous_Cluster_Plan.docx](UniverseModel_Heterogeneous_Cluster_Plan.docx) | architecture/heterogeneous_cluster_plan.md |

模块细化、公式目录、场景推演与优化方法保留为独立 Markdown，避免一本 Word 不断膨胀。Word 输出是指定来源的阅读版本，不包含仓库全部正文。

## 构建与检查

使用含 python-docx 的环境，依赖范围见 [requirements.txt](tools/requirements.txt)。根目录执行：

```text
python docs/tools/build_docx.py --document design
python docs/tools/build_docx.py --document parameters
python docs/tools/build_docx.py --document scaling
python tools/check_structure.py
```

[documents.json](tools/documents.json) 统一声明输出、标题与来源。构建工具在文档属性记录按顺序拼接的 Markdown 源 SHA256；检查工具验证同步。哈希通过不代表排版合格，生成后仍需渲染并逐页检查字体、表格、分页与裁切。QA 文件放 .build，不纳入版本控制。

Markdown 链接检查针对本地文件目标，不验证外部网站可达性或标题锚点。Mermaid 图保留在独立 Markdown；当前 Word 构建器不渲染 Mermaid，也不汇编包含它们的文件。
