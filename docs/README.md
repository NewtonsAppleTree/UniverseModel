# 文档维护

## 内容顺序

1. architecture/design.md：范围、目录职责、数据流和实现顺序。
2. interfaces/contracts.md：硬件、负载、执行计划及仿真输出的语义约定。
3. architecture/validation.md：模型精度、测试分工、指标和验收条件。

UniverseModel_Design.docx 由以上三个 Markdown 文件按顺序生成。修改源文件后重新构建，避免分别维护两套正文。

architecture/architecture_parameters.md 单独维护中英文术语、结构与参数、参数来源、CIM 与异构设计方法，以及参数管理约定。它生成 UniverseModel_Architecture_Parameters.docx，不并入工程设计文档。

architecture/heterogeneous_cluster_plan.md 扩展 CPU、GPU、NPU、CIM 与 3D CIM 异构，规定封装、HBF、节点、多卡与多机的模块边界、数据流和实施顺序。它生成 UniverseModel_Heterogeneous_Cluster_Plan.docx。文档中的新增代码模块属于后续规划。

## 构建

使用带有 python-docx 的 Python 环境，依赖范围见 tools/requirements.txt。在工程根目录执行：

```text
python docs/tools/build_docx.py
python docs/tools/build_docx.py --document parameters
python docs/tools/build_docx.py --document scaling
```

工具在执行时读取 Markdown，按所选文档输出 Word，并在文档属性中记录源文件内容哈希。默认构建工程设计文档；parameters 构建架构参数手册；scaling 构建异构与集群规划。工具只负责构建 Word，不运行模型或实验。

生成后渲染并检查每一页，重点检查中文字体、表格换行、标题位置和分页。渲染临时文件放在 .build/docs 中，不纳入版本控制。
