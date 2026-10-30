# UniverseModel

芯片到集群的架构建模工程，覆盖架构定义、工作负载映射、功能验证、性能与成本评估。支持规划 CPU、GPU、NPU、CIM、3D CIM、双裸片、HBM/HBF、异构节点和多机多卡。`chipmodel` 放软件模型，当前不包含 RTL。

**当前状态：架构与工程骨架阶段。** 已建立 13 个主模块、子目录、模块设计、公共契约、方法文档和可运行的结构检查工具；编译、硬件执行、仿真、实验运行和图形界面尚未实现。结构示例不是可执行硬件配置。

## 先读哪些文档

1. [顶层架构](docs/architecture/design.md)：模块边界、状态归属和完整信息链。
2. [第一性原理](docs/architecture/first_principles.md)：整个项目与各模块最核心的问题。
3. [分场景推演](docs/architecture/scenarios.md)：单芯片、CIM、3D、HBF、异构与集群。
4. [公共契约](docs/interfaces/contracts.md)与[产物规范](docs/interfaces/artifacts.md)：交换什么、如何保存和复现。
5. [参数与数学方法](docs/methods/parameters_and_math.md)、[工作流](docs/methods/workflows.md)、[优化方法](docs/methods/optimization.md)。
6. [架构补充审视](docs/architecture/design_review.md)：17 项易遗漏问题、P0/P1/P2 优先级与六个专题。

参数如何修改和可视化，见 [configuration 设计](configuration/docs/design.md)与 [ui 设计](ui/docs/design.md)。先共享参数定义、派生与校验规则，再实现文本/CLI 和表单、拓扑、映射、时间线。

## 模块导航

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

## 支撑目录

```text
config/       硬件、成本、编译、运行、仿真与实验配置文件
data/         输入、校准来源和运行产物
tests/        契约、模型、系统与集成验证归属
example/      结构示例与未来完整工作流示例
docs/         顶层架构、契约、方法、决策和 Word 文档
tools/        结构一致性等开发工具
```

## 当前可运行的检查

在仓库根目录使用 Python 3.10 或更高版本，无需安装业务依赖：

```text
python tools/check_structure.py
```

检查目录/文档、模块依赖 DAG、Markdown 本地文件链接、结构示例引用和维护中的 DOCX 源哈希。它不执行芯片仿真、不证明硬件配置可实现，也不替代功能与性能验证。

## Word 与后续开发

- [工程设计 Word](docs/UniverseModel_Design.docx)：顶层架构、公共契约、验证门槛。
- [架构参数手册 Word](docs/UniverseModel_Architecture_Parameters.docx)：结构、英文术语与参数来源。
- [异构与集群规划 Word](docs/UniverseModel_Heterogeneous_Cluster_Plan.docx)：异构、封装、HBF 与集群。
- [架构补充审视 Word](docs/UniverseModel_Architecture_Review.docx)：跨模块细节、模型覆盖、实验条件与实施取舍。
- [完整文档索引与构建方法](docs/README.md)。

Markdown 是正文维护源。第一轮执行实现从一个 GEMM/MatVec、独立参考、小型数字引擎、SRAM 和显式搬运开始，再验证争用、重叠与参数变化；阶段门槛见[验证规范](docs/architecture/validation.md)。
