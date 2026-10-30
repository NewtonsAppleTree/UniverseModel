# UniverseModel

芯片架构建模工程，覆盖架构定义、工作负载映射、功能验证和性能评估。`chipmodel` 实现软件模型；RTL 在后续阶段独立组织。

当前已建立目录骨架和设计约定，尚未实现编译、芯片模型或仿真功能。

## 目录

```text
UniverseModel/
├── chipmodel/                 # 硬件资源、状态、行为和成本模型
│   ├── compute/
│   ├── memory/
│   ├── interconnect/
│   └── control/
├── compiler/                  # 保留既有编译器结构
│   ├── src/                   # IR、划分、切块、存储规划、调度等
│   ├── include/
│   ├── python/
│   ├── tests/
│   ├── tools/
│   ├── scripts/
│   ├── docs/
│   ├── 3rdparty/
│   └── temp/                  # 临时产物，不纳入版本控制
├── simulator/
│   ├── engine/                # 事件与时间推进
│   ├── stats/                 # 指标采集
│   └── trace/                 # 执行轨迹
├── workloads/
│   ├── kernels/               # 单任务与算子负载
│   ├── graphs/                # 多任务计算图
│   └── reference/             # 独立功能参考
├── evaluation/
│   ├── experiments/           # 实验组织与参数扫描
│   └── analysis/              # 指标分析与绘图
├── tests/
│   ├── chipmodel/
│   ├── simulator/
│   ├── contracts/
│   └── integration/
├── config/
│   ├── hardware/
│   ├── compiler/
│   ├── simulation/
│   └── experiments/
├── docs/
│   ├── architecture/         # 工程设计和验证方法
│   ├── interfaces/           # 跨模块契约
│   ├── tools/                # 文档构建工具
│   └── UniverseModel_Design.docx
├── data/
│   ├── inputs/               # 输入数据
│   └── runs/                 # 运行结果，不纳入版本控制
└── example/                  # 最小使用示例
```

## 文档

- [工程结构与模块职责](docs/architecture/design.md)
- [模块接口与执行约定](docs/interfaces/contracts.md)
- [验证方法与性能评估](docs/architecture/validation.md)
- [Word 设计文档](docs/UniverseModel_Design.docx)
- [芯片结构参数与设计方法](docs/architecture/architecture_parameters.md)
- [Word 架构参数手册](docs/UniverseModel_Architecture_Parameters.docx)
- [异构芯片封装与集群建模规划](docs/architecture/heterogeneous_cluster_plan.md)
- [Word 异构与集群规划](docs/UniverseModel_Heterogeneous_Cluster_Plan.docx)
- [文档构建说明](docs/README.md)

Markdown 是维护源。工程设计 Word 汇编前三份文档，架构参数手册和异构与集群规划分别生成。修改 Markdown 后重新生成对应 Word。

异构与集群规划覆盖 CPU、GPU、NPU、CIM、3D CIM、双裸片、HBM/HBF 和多机多卡；拟增加的 systemmodel、clustermodel 等模块尚未实现，当前目录树仍反映已有骨架。

## 第一阶段验收

固定一个代表性任务和一套硬件配置，完成映射、功能比对与性能统计。改变一项硬件参数，说明性能变化的原因，并保存可复现的配置与结果。具体要求见验证文档。
