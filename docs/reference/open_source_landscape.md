# 开源项目调研与模块选型

调研日期：**2026-11-20**。服务于[项目使命](../../PROJECT_MISSION.md)与[研究开发路线](../RESEARCH_ROADMAP.md)。本轮收录 **102 个候选项目、44 篇代表论文的引用记录**，覆盖 13 个基础模块及训练、推理、EDA 场景。其中 101 个仓库已取得 GitHub 元数据并阅读官方 README；ONNX Runtime 已核对官网，仓库数据待复核。

本轮完成公开资料与仓库说明核对，尚未安装、运行或复现这些外部项目。下文的能力描述来自维护方资料，接入建议是针对 UniverseModel 的判断；实验有效性仍需通过复现和校准验证。已实现能力以 [STATUS](../STATUS.md)为准。

**收录原则：GitHub 热度与学术影响并列，同模块横向比较多个候选，收录与接入优先级分开。** 所有本轮候选均保留在[全量清单与横向对照](open_source_comparison.md)，包括低热度后继工具、历史项目和待核候选。

## 1 选型结论

当前最有价值的工作是打通一个可解释、可比较的 AI 算子研究实验，再按实验需要扩展模块。优先研究以下三组工具：

1. **映射与成本：Timeloop、Accelergy、ZigZag，以及 AccelForge / HWComponents。** 前三者提供成熟研究方法和历史论文基线；后两者是 CiMLoop 维护方明确指向的新开发入口，需要先评估兼容性与成熟度。
2. **AI 工作负载与实机参照：PyTorch、Triton、LLMCompass。** 分别支撑功能参考、GPU 内核实验，以及 LLM 工作量到硬件性能的分层建模。先选小型 GEMM/MatVec 实验，逐步扩展到层级账本。
3. **根据课题选择执行层：推理用 vLLM / Vidur，分布式训练用 Megatron / DeepSpeed / ASTRA-sim，存储细节用 Ramulator。** 它们对应不同问题，不需要在第一阶段全部接入。

UniverseModel 应优先维护研究变量、任务与资源语义、方案变换、跨工具转换、实验比较和证据记录。成熟执行器、编译基础设施、存储/网络模拟器和 EDA 工具优先作为外部后端或基线。自研范围由现有工具无法表达的研究机制决定。

## 2 数据口径与证据层级

| 项目 | 本轮口径 |
| --- | --- |
| 社区认可度 | GitHub REST API 的 `stargazers_count`；stars 是关注信号，不代表精度或实验有效性 |
| 学术影响力 | OpenAlex 的单篇 `cited_by_count`；每条记录给出标题、版本、DOI 和 OpenAlex ID；不是 Google Scholar 数值 |
| 版本去重 | 不累加同一工作的预印本与会议版本；部分工具用明确标注的 arXiv 条目；早期框架论文不等于当前代码版本的验证 |
| 活跃度 | 保存默认分支、最近推送、是否归档，并阅读维护声明；最近推送也可能只是文档或自动更新 |
| 许可 | 保存 GitHub 自动识别结果；`null` / `NOASSERTION` 表示需要读实际许可文件，不能解释为允许任意复用 |
| 选入原则 | 学术引用与 GitHub 热度并列；同模块多候选全收录，包含维护中的后继项目；不是穷尽排行榜 |
| 复现证据 | 资料核对 → 固定版本运行 → 复现论文结果 → 与独立数据校准；本轮仅完成第一层 |

完整元数据保存在[日期快照](data/open_source_snapshot_2026-11-20.json)，包含 GitHub 请求地址、UTC 获取时间、README 地址及内容哈希、论文查询与所选记录。README 地址指向当时默认分支，可能变化；哈希用于标识本轮读取内容，不代替后续实验必须固定的 commit、依赖和输入。

论文引用存在收录延迟与版本拆分，不能直接横向比较不同年龄、领域的项目。大型 monorepo 的 stars 也不等于其子模块的认可度，例如 LLVM 的 stars 不能全部归于 MLIR。未列引用数表示本轮未核对对应论文，不表示零引用。

## 3 与 UniverseModel 各模块的对应关系

优先级含义：**P0** 为首个实验所需，**P1** 在扩大任务/精度时接入，**P2** 由具体课题触发。某模块列为 P0 只表示其必要接口需要落地，不要求完成整个目录。

| 模块 | 外部候选举例（完整对照见清单） | 从中提取或接入什么 | 建议次序 |
| --- | --- | --- | --- |
| contracts | Chakra、ONNX、StableHLO、MLIR | 操作/数据依赖、资源身份、版本和 trace 交换；外部 schema 经 adapter 转换 | P0：最小任务/计划；trace 为 P1 |
| configuration | Hydra、OmegaConf、Pydantic | 配置组合、覆盖和扫描的使用方式；保留现有严格参数解析与标准库核心 | P0：复用现有实现 |
| workloads | PyTorch、TensorFlow、JAX、Transformers、MLPerf、Chakra | 数值参考、输入分布、质量门槛、可回放工作量 | P0 |
| compiler | Timeloop、ZigZag、AccelForge；TVM、MLIR、Triton、IREE | 分块、映射、容量合法性、代码生成；首版只做实验需要的映射边界 | P0：静态映射；完整编译栈为 P1/P2 |
| costmodel | Accelergy、HWComponents、CACTI、NeuroSim | 动作成本、PVT 条件、来源与适用域；缺失项保留未知 | P0：条件查询；物理校准为 P1 |
| chipmodel | SCALE-Sim、CiMLoop、AIHWKit、Ramulator、BookSim；gem5、Accel-Sim | 组件行为、数据通路、内存/网络争用或详细处理器后端 | P0：复用相关单元；细模型为 P1/P2 |
| systemmodel | LLMCompass、SST、NCCL | 单节点资源、主机/设备路径、容量与带宽边界 | P1 |
| clustermodel | ASTRA-sim、SimAI、SST | 集群拓扑、链路、通信与计算重叠的外部仿真 | P2，分布式课题可提前 |
| runtime | vLLM、SGLang、TensorRT-LLM、llama.cpp；Megatron、DeepSpeed、ColossalAI、TorchTitan、NCCL | 批处理、内存管理、并行与派发策略；依据研究问题选择一种 | P1/P2 |
| simulator | Vidur、ASTRA-sim、SST、gem5、Accel-Sim | 时间推进、事件归属、外部仿真驱动与结果转换 | P1/P2；首版分析实验可独立运行 |
| evaluation | MLPerf、Optuna、Ray、Ax、BoTorch、Nevergrad、LLMCompass AE | 比较协议、校准、有限扫描、搜索预算、论文图表复现 | P0 |
| artifacts | MLflow、DVC、W&B；Chakra trace | 输入/版本/结果记录、trace 导出；复用现有本地 bundle | P0：本地产物；服务化为 P2 |
| ui | Streamlit、Gradio、Dash、Perfetto | 已有结果与时间线的浏览、分析 | P2；先输出可读表格和标准 trace |

`trainingArch` 和 `inferArch` 继续作为场景入口。训练方向重点连接 PyTorch、Megatron、DeepSpeed、NCCL、ASTRA-sim；推理方向连接 LLMCompass、vLLM、SGLang、Vidur、FlashInfer。EDA 方向通过 evaluation/costmodel/chipmodel 接入 Yosys、OpenROAD、Verilator，按需要补充 RTL、综合或物理实现证据。

## 4 全量清单与横向比较结论

完整名单与 GitHub 热度统一见[102 个候选的全量对照](open_source_comparison.md)。它按 22 个实际选型问题分组，逐项列出 stars、最近推送、功能侧重和接入边界；组内按 stars 降序展示，论文证据另见本报告。候选总表持续扩充，首批接入清单只决定近期工作顺序。

| 选型问题 | 必须保留的横向对照 | 当前判断 |
| --- | --- | --- |
| 加速器架构与映射 | Timeloop、ZigZag、SCALE-Sim、MAESTRO、AccelForge | 先对齐工作量、映射合法性、存储预算与模型精度，再比较结果；新旧工具都保留 |
| GPU 编译与 kernel | Triton、CUTLASS、TileLang、TVM、IREE、XLA、tinygrad；FlashAttention/FlashInfer | 区分模型编译、kernel 编程和专用内核库；按目标硬件与改动层级选基线 |
| LLM 推理与部署 | llama.cpp、vLLM、SGLang、TensorRT-LLM；MNN、ncnn、ONNX Runtime | 热度高的主流工程框架都收录；先区分服务器、端侧和异构部署，再横向测量 |
| AI 任务与训练 | PyTorch、TensorFlow、JAX、Transformers；DeepSpeed、ColossalAI、Megatron、TorchTitan | 任务/数值框架与分布式执行框架分层比较，覆盖多个软件生态 |
| 组件成本与 CIM | CACTI、McPAT、Accelergy、HWComponents、NeuroSim、CiMLoop、AIHWKit/Lightning | 成本、物理参数与 AI 质量分别对照，辨认共享模型和维护迁移 |
| 系统与集群仿真 | LLMCompass、Vidur、SST Core/Elements、ASTRA-sim、SimAI、ns-3 | 区分层级分析、服务请求、组件事件和网络仿真；选择需要的精度 |
| 实验工程 | Hydra/OmegaConf/Pydantic；Optuna/Ray/Ax/BoTorch/Nevergrad；MLflow/DVC/W&B | 配置、校验、搜索、执行和产物追踪具有不同责任；不把互补组件当完全替代品 |
| UI 与 EDA | Streamlit/Gradio/Dash/Perfetto；Yosys/OpenROAD/Verilator | UI 按表单、图表与 trace 需要比较；EDA 按功能、综合、物理设计组成证据链 |

GitHub stars 会影响生态、示例、潜在使用者和工业接入价值的评估，因此进入正式选型的模块必须核对主流高热度候选。学术影响、技术匹配与复现证据仍独立记录；当前没有同条件性能数据，不给出综合性能名次或人为加权的总分。

本轮语料扩充了 NPU 编译、端侧部署、量化、训练自动并行、多作业调度和 KV 管理。纠错、训练层次和研究问题见[语料审阅](ai_software_corpus_review.md)。Optimus 两个同名项目仅保留背景用途。

## 5 会影响当前决策的版本与许可发现

- **CiMLoop 的维护迁移是真正的选型信号。** [当前 README](https://github.com/mit-emze/cimloop)明确写明停止维护并推荐 AccelForge / HWComponents。GitHub 的 `archived=false` 无法反映这件事。历史论文复现固定旧版本；新接口同时评估后继项目，不能只按 stars 排序。
- **维护版本和论文版本分别记录。** SCALE-Sim 当前仓库说明 v3；Ramulator 仓库名仍为 ramulator2，但说明已为 2.1；Accel-Sim 当前说明为 2.0。表中早期论文引用数不证明这些新版本的所有能力。LLVM stars、NeuroSim 框架论文与某一版本也不能混用。
- **许可核查会影响工业探索。** [NeuroSim V1.4 README](https://github.com/neurosim/DNN_NeuroSim_V1.4)声明非商业使用与 CC BY-NC 4.0，应归为公开源码参考，工业集成另评估授权。不能因为 HWComponents 本体为 MIT 就推断其所有可选模型包和上游模型也具有同样许可。
- **实际文件优先于徽章。** SimAI README 的徽章显示 MIT，但本轮读取的[根 LICENSE](https://github.com/aliyun/SimAI/blob/master/LICENSE)为 Apache-2.0。其子模块仍需分别核对。其他仓库的 `NOASSERTION` / `null` 暂保留待核状态。
- **依赖需要隔离。** HWComponents 当前 README 标明 Python 3.12+，本项目支持 Python 3.10+；重型 GPU、EDA、仿真依赖放独立环境/进程，通过显式文件或调用边界交换结果，公共 contracts 保持标准库。
- **基准实现不自动等于强基线。** MLPerf Training 自身明确指出 reference implementations 不是充分优化的真实性能测量对象；研究比较应选匹配的优化实现，并记录版本和调优预算。

## 6 代表论文引用记录

以下数字只用于理解影响力。工具的当前能力以前述仓库和版本核对为准；正式研究引用还须按照实际使用版本的说明补充对应论文。SimAI 的一次标题查询未返回可确认的目标记录，本轮不报告其引用量。

| 编号 / 项目 | 代表论文（所选版本） | OpenAlex 引用 |
| --- | --- | ---: |
| P01 · gem5 | [The gem5 simulator](https://doi.org/10.1145/2024716.2024718)；2011 原始论文 | [5,868](https://openalex.org/W2147657366) |
| P02 · Timeloop | [Timeloop: A Systematic Approach to DNN Accelerator Evaluation](https://doi.org/10.1109/ispass.2019.00042)；ISPASS 2019 | [839](https://openalex.org/W2940862705) |
| P03 · Accel-Sim | [Accel-Sim: An Extensible Simulation Framework for Validated GPU Modeling](https://doi.org/10.1109/isca45697.2020.00047)；ISCA 2020 | [531](https://openalex.org/W3102510044) |
| P04 · LLMCompass | [LLMCompass: Enabling Efficient Hardware Design for Large Language Model Inference](https://doi.org/10.1109/isca59077.2024.00082)；ISCA 2024 | [161](https://openalex.org/W4401211642) |
| P05 · Accelergy | [Accelergy: An Architecture-Level Energy Estimation Methodology for Accelerator Designs](https://doi.org/10.1109/iccad45719.2019.8942149)；ICCAD 2019 | [341](https://openalex.org/W2998732502) |
| P06 · SCALE-Sim | [SCALE-Sim: Systolic CNN Accelerator Simulator](https://doi.org/10.48550/arxiv.1811.02883)；2018 arXiv 条目；非当前 v3 论文 | [428](https://openalex.org/W2911491685) |
| P07 · ZigZag | [ZigZag: Enlarging Joint Architecture-Mapping Design Space Exploration for DNN Accelerators](https://doi.org/10.1109/tc.2021.3059962)；IEEE TC 2021 | [247](https://openalex.org/W3132942233) |
| P08 · DNN+NeuroSim | [DNN+NeuroSim: An End-to-End Benchmarking Framework for Compute-in-Memory Accelerators with Versatile Device Technologies](https://doi.org/10.1109/iedm19573.2019.8993491)；IEDM 2019 框架论文；非 V1.4 专属论文 | [449](https://openalex.org/W3005619596) |
| P09 · ASTRA-sim 2.0 | [ASTRA-sim2.0: Modeling Hierarchical Networks and Disaggregated Systems for Large-model Training at Scale](https://doi.org/10.1109/ispass57527.2023.00035)；ISPASS 2023 | [211](https://openalex.org/W4381886086) |
| P10 · Vidur | [Vidur: A Large-Scale Simulation Framework For LLM Inference](https://doi.org/10.48550/arxiv.2405.05465)；2024 arXiv 条目；仓库指向 MLSys 2024 工作 | [206](https://openalex.org/W4396822035) |
| P11 · TVM | [TVM: An Automated End-to-End Optimizing Compiler for Deep Learning](https://doi.org/10.48550/arxiv.1802.04799)；2018 arXiv 条目；OSDI 工作的预印本记录 | [2,919](https://openalex.org/W2804032941) |
| P12 · MLIR | [MLIR: Scaling Compiler Infrastructure for Domain Specific Computation](https://doi.org/10.1109/cgo51591.2021.9370308)；CGO 2021 | [957](https://openalex.org/W3122286897) |
| P13 · Triton | [Triton: an intermediate language and compiler for tiled neural network computations](https://doi.org/10.1145/3315508.3329973)；MAPL 2019 | [1,161](https://openalex.org/W2954698171) |
| P14 · vLLM / PagedAttention | [Efficient Memory Management for Large Language Model Serving with PagedAttention](https://doi.org/10.1145/3600006.3613165)；SOSP 2023 | [10,891](https://openalex.org/W4387321091) |
| P15 · SGLang | [SGLang: Efficient Execution of Structured Language Model Programs](https://doi.org/10.52202/079017-2000)；NeurIPS 2024 | [2,212](https://openalex.org/W4415797413) |
| P16 · DeepSpeed / ZeRO | [ZeRO: Memory optimizations Toward Training Trillion Parameter Models](https://doi.org/10.1109/sc41405.2020.00024)；SC 2020 | [2,927](https://openalex.org/W3129831491) |
| P17 · Megatron-LM | [Megatron-LM: Training Multi-Billion Parameter Language Models Using Model Parallelism](https://doi.org/10.48550/arxiv.1909.08053)；2019 arXiv 条目 | [3,990](https://openalex.org/W2973727699) |
| P18 · FlashAttention | [FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness](https://doi.org/10.52202/068431-1189)；NeurIPS 2022 | [5,917](https://openalex.org/W7133227460) |
| P19 · OpenROAD | [Toward an Open-Source Digital Flow: First Learnings from the OpenROAD Project](https://doi.org/10.1145/3316781.3326334)；DAC 2019 | [365](https://openalex.org/W2946332877) |
| P20 · PyTorch | [PyTorch: An Imperative Style, High-Performance Deep Learning Library](https://doi.org/10.48550/arxiv.1912.01703)；2019 arXiv 条目 | [65,746](https://openalex.org/W2970971581) |
| P21 · Optuna | [Optuna: A Next-generation Hyperparameter Optimization Framework](https://doi.org/10.1145/3292500.3330701)；KDD 2019；未叠加另一个 arXiv 条目的引用 | [13,473](https://openalex.org/W2949676527) |
| P22 · CiMLoop | [CiMLoop: A Flexible, Accurate, and Fast Compute-In-Memory Modeling Tool](https://doi.org/10.1109/ispass61541.2024.00012)；ISPASS 2024 | [60](https://openalex.org/W4400681289) |
| P23 · MAESTRO | [Understanding Reuse, Performance, and Hardware Cost of DNN Dataflow: A Data-Centric Approach](https://doi.org/10.1145/3352460.3358252)；MICRO 2019 | [390](https://openalex.org/W2980200167) |
| P24 · McPAT | [McPAT: an integrated power, area, and timing modeling framework for multicore and manycore architectures](https://doi.org/10.1145/1669112.1669172)；MICRO 2009 | [2,972](https://openalex.org/W2170382128) |
| P25 · GPGPU-Sim | [Analyzing CUDA workloads using a detailed GPU simulator](https://doi.org/10.1109/ispass.2009.4919648)；ISPASS 2009 | [1,894](https://openalex.org/W1979527452) |
| P26 · TensorFlow | [TensorFlow: A system for large-scale machine learning](https://doi.org/10.48550/arxiv.1605.08695)；2016 arXiv 条目；OSDI 工作的预印本记录 | [22,876](https://openalex.org/W2402144811) |
| P27 · Transformers | [Transformers: State-of-the-Art Natural Language Processing](https://doi.org/10.18653/v1/2020.emnlp-demos.6)；EMNLP Demos 2020 | [17,450](https://openalex.org/W2979826702) |
| P28 · Ray | [Ray: A Distributed Framework for Emerging AI Applications](https://doi.org/10.48550/arxiv.1712.05889)；2017 arXiv 条目 | [1,920](https://openalex.org/W2780624097) |
| P29 · BoTorch | [BoTorch: A Framework for Efficient Monte-Carlo Bayesian Optimization](https://doi.org/10.48550/arxiv.1910.06403)；2019 arXiv 条目 | [1,235](https://openalex.org/W3105441357) |
| P30 · FlashInfer | [FlashInfer: Efficient and Customizable Attention Engine for LLM Inference Serving](https://doi.org/10.48550/arxiv.2501.01005)；2025 arXiv 条目 | [454](https://openalex.org/W4406032994) |
| P31 · TPU-MLIR | [TPU-MLIR: A Compiler For TPU Using MLIR](https://doi.org/10.48550/arxiv.2210.15016)；2022 arXiv 条目 | [16](https://openalex.org/W4307535028) |
| P32 · AWQ | [AWQ: Activation-aware Weight Quantization for LLM Compression and Acceleration](https://doi.org/10.48550/arxiv.2306.00978)；2023 arXiv 条目；不叠加同名其他版本 | [1,058](https://openalex.org/W4379260375) |
| P33 · GPTQ | [GPTQ: Accurate Post-Training Quantization for Generative Pre-trained Transformers](https://doi.org/10.48550/arxiv.2210.17323)；2022 arXiv 条目；仓库关联 ICLR 2023 工作 | [3,089](https://openalex.org/W4307934016) |
| P34 · SmoothQuant | [SmoothQuant: Accurate and Efficient Post-Training Quantization for Large Language Models](https://doi.org/10.48550/arxiv.2211.10438)；2022 arXiv 条目 | [839](https://openalex.org/W4309591680) |
| P35 · Hybe | [Hybe: GPU-NPU Hybrid System for Efficient LLM Inference with Million-Token Context Window](https://doi.org/10.1145/3695053.3731051)；ISCA 2025；论文已核对，开源代码本轮未确认 | [21](https://openalex.org/W4411486169) |
| P36 · Kelle | [Kelle: Co-design KV Caching and eDRAM for Efficient LLM Serving in Edge Computing](https://doi.org/10.1145/3725843.3756071)；MICRO 2025；论文已核对，开源代码本轮未确认 | [15](https://openalex.org/W4415309218) |
| P37 · Alpa | [Alpa: Automating Inter- and Intra-Operator Parallelism for Distributed Deep Learning](https://doi.org/10.48550/arxiv.2201.12023)；2022 arXiv 条目；OSDI 工作的预印本记录 | [559](https://openalex.org/W4226479682) |
| P38 · FlexFlow | [Beyond Data and Model Parallelism for Deep Neural Networks](https://doi.org/10.48550/arxiv.1807.05358)；2018 arXiv 条目；仓库关联 MLSys 2019 工作 | [406](https://openalex.org/W2884700152) |
| P39 · Optimus 二维并行 | [An Efficient 2D Method for Training Super-Large Deep Learning Models](https://doi.org/10.1109/ipdps54959.2023.00031)；IPDPS 2023 正式条目；历史参考 | [76](https://openalex.org/W3159351344) |
| P40 · Optimus 集群调度 | [Optimus: an efficient dynamic resource scheduler for deep learning clusters](https://doi.org/10.1145/3190508.3190517)；EuroSys 2018；历史参考 | [558](https://openalex.org/W2798515322) |
| P41 · Gavel | [Heterogeneity-Aware Cluster Scheduling Policies for Deep Learning Workloads](https://doi.org/10.48550/arxiv.2008.09213)；2020 arXiv 条目；OSDI 工作的预印本记录 | [243](https://openalex.org/W3096583839) |
| P42 · Pollux / AdaptDL | [Pollux: Co-adaptive Cluster Scheduling for Goodput-Optimized Deep Learning](https://doi.org/10.48550/arxiv.2008.12260)；2020 arXiv 条目；OSDI 2021 工作的预印本记录 | [99](https://openalex.org/W3080451848) |
| P43 · Tiresias | [Tiresias: A GPU Cluster Manager for Distributed Deep Learning](https://scholarworks.unist.ac.kr/handle/201301/32653)；NSDI 2019 会议条目 | [529](https://openalex.org/W2919594608) |
| P44 · Mooncake | [Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving](https://doi.org/10.1145/3773772)；ACM Transactions on Storage 条目；不与 FAST 2025 版本合并 | [346](https://openalex.org/W4416249188) |

## 7 下一轮精读与复现任务

候选全量保留；下一轮以同模块横向比较来确定接入子集。下一轮优先完成下面的调查卡，每组先做一个最小案例；通过后再决定是否接入生产模块。每个进入正式选型的模块至少核对三个相关候选；实际运行范围按当前问题确定。

| 顺序 | 对象 | 要回答的问题 | 最小复现/对照产物 |
| --- | --- | --- | --- |
| 1 | Timeloop + Accelergy；AccelForge + HWComponents | workload / mapping / action / cost 如何分离？新旧接口和模型覆盖有哪些差异？ | 固定版本的单 GEMM，分层动作/字节/容量与成本表；成本来源和未知项清单 |
| 2 | ZigZag、SCALE-Sim、MAESTRO | 同样工作量、映射和硬件预算下，结果在哪些机制上有差异？ | 一个可手算形状与一个边界形状；解释差异，不能只比较最终总值 |
| 3 | PyTorch + Triton + LLMCompass | 算子到层级的工作量与真实性能如何对应？哪些抽象会失效？ | 功能参考；有 GPU 时采集 kernel 时延；选择一个 AE 图或子实验复现 |
| 4 | vLLM + Vidur | 服务负载怎样暴露 batch、KV 容量和调度瓶颈？ | 使用已有 profile 的小仿真；有匹配硬件后复核 TTFT/TPOT/吞吐及未完成请求 |
| 条件触发 | AIHWKit / NeuroSim；Ramulator / BookSim；ASTRA-sim / SimAI；EDA 工具 | 结论是否依赖噪声、存储/网络争用、多机或物理实现？ | 只对相应缺口增加质量、细时序、集群或 PPA 证据 |

每张调查卡至少记录：研究问题、精度层级、输入输出、资源与状态所有权、算法/模型假设、已知不支持项、校准来源、构建条件、许可证、固定 commit/依赖、最小运行命令、原始结果、复现偏差、建议角色（参考/基线/adapter/暂缓）。只有跑通的项目才能标记“可运行”；只有完成独立对照的范围才能标记“已验证”。

复现前阅读论文的验证章节与 artifact 说明，并检查相关 issue、release 和对应源代码；本轮并未做逐文件实现审计。进一步围绕选定问题追踪最近三年的体系结构、MLSys、AI 与 EDA 工作和前向引用，补充低引用的新成果。优先级和验收门槛由[研究开发路线](../RESEARCH_ROADMAP.md)维护。
