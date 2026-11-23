# 开源候选全量清单与横向对照

核对日期：**2026-11-20**。本页收录本轮识别的 **102 个候选项目**：101 个仓库已取得 GitHub 元数据并阅读官方 README；ONNX Runtime 已核对官网，仓库元数据本轮未取得，保留待核。覆盖 13 个基础模块，按 22 个实际选型问题分组。这里的“全量”指本轮候选集合，不宣称穷尽所有公开软件。

**GitHub 热度与学术引用是并列的收录依据。** 同模块保留多个候选，历史高引项目、高热度工程项目、新后继项目和互补组件均收录。是否收录与何时接入分别决定；进入首批实验的项目不会取代候选总表。

组内按 **stars 降序**展示，未知值置后；这个排序表示累计社区关注，不代表技术适合度或近期增长率。每行同时给出最近推送与能力边界；fork、许可、来源/README 哈希和代表论文引用见[数据快照](data/open_source_snapshot_2026-11-20.json)及[调研报告](open_source_landscape.md)。尚无历史 stars 快照，暂不报告增速。

所有技术范围均来自维护方说明，横向取舍和建议是针对本项目的分析，**本轮没有运行外部工具或做性能排名**。列在同组的工具可能是竞争方案、不同精度后端或依赖组件，下文分别说明。共同验证问题用于后续实验，不表示已经通过。

课程语料、端侧对照截图与训练项目的核查及分层建议见[补充审阅](ai_software_corpus_review.md)。新增 25 个候选；两个 Optimus 均保留为历史参考，按用户方向不进入首批精读/复现。

## 模块覆盖与选型问题

| 模块 | 对照组 |
| --- | --- |
| contracts | 交换格式与公共语义 |
| configuration | 配置与参数校验 |
| workloads | 任务来源、CIM 数值、训练任务 |
| compiler | 编译器、Attention 内核、架构映射 |
| costmodel | 组件成本、CIM、EDA |
| chipmodel | 架构映射、处理器/GPU、存储/NoC、CIM、EDA |
| systemmodel | 节点/服务、推理部署、训练与通信 |
| clustermodel | 集群与网络仿真、自动并行、训练作业调度、KV 传输 |
| runtime | 推理、训练、内核与集群通信 |
| simulator | 细模型、存储、节点/服务、事件框架、集群网络 |
| evaluation | 任务协议、映射/DSE、实验调度、产物与 EDA 验证 |
| artifacts | 实验记录与产物管理 |
| ui | 结果 UI 与 trace 可视化 |


## 1. 交换格式与公共语义

对应模块：`contracts`。

同一个小图分别表达计算语义、张量类型和执行依赖，记录无法转换的字段。它们位于不同抽象层，允许组合使用。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [llvm/llvm-project](https://github.com/llvm/llvm-project) | 41,529 | 2026-11-20 | MLIR 的可扩展 IR、dialect 和 lowering 基础 | stars 属于整个 LLVM；引入自定义 dialect 需承担工具链维护 |
| [onnx/onnx](https://github.com/onnx/onnx) | 21,724 | 2026-11-18 | 模型图、算子和 dtype 交换 | 适合模型导入；不包含完整硬件资源、调度和事件语义 |
| [openxla/stablehlo](https://github.com/openxla/stablehlo) | 730 | 2026-11-20 | 框架与编译器间稳定的高层算子集合 | 关注序列化、版本兼容；硬件执行计划另行表达 |
| [mlcommons/chakra](https://github.com/mlcommons/chakra) | 211 | 2026-11-19 | 计算/存储/通信与依赖的 execution trace | 适合回放与仿真输入；trace 不自动等于算法级功能参考 |

## 2. 配置与参数校验

对应模块：`configuration`。

用相同嵌套配置测试默认值、覆盖、错误字段、类型与来源记录。Hydra 使用 OmegaConf，两者不是独立的完整替代品；Pydantic 更侧重数据校验。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [pydantic/pydantic](https://github.com/pydantic/pydantic) | 29,588 | 2026-11-19 | 类型驱动的数据校验与 schema | 外部接口可选；公共 contracts 当前仍只依赖标准库 |
| [hydra-ecosystem/hydra](https://github.com/hydra-ecosystem/hydra) | 10,757 | 2026-11-20 | 应用配置组合、CLI 覆盖和实验组织 | 借鉴使用方式；执行对象构造等机制不直接进入本仓库配置 |
| [hydra-ecosystem/omegaconf](https://github.com/hydra-ecosystem/omegaconf) | 2,443 | 2026-11-19 | 层次配置、合并、结构化配置容器 | 需明确插值/解析规则；保留本仓库显式派生与冻结边界 |

## 3. 任务来源与功能参考

对应模块：`workloads` / `evaluation`。

比较同一算子的输出、梯度、dtype 和模型导出；采用相同数据与质量标准。框架执行、模型定义和 benchmark 协议分别评价。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [tensorflow/tensorflow](https://github.com/tensorflow/tensorflow) | 201,659 | 2026-11-20 | 训练/部署生态与图执行 | 适合覆盖另一套软件栈；图优化和模型导出语义需核对 |
| [huggingface/transformers](https://github.com/huggingface/transformers) | 169,308 | 2026-11-20 | 模型定义、训练/推理任务来源 | 模型仓库、权重、tokenizer 和数据许可需独立固定 |
| [pytorch/pytorch](https://github.com/pytorch/pytorch) | 105,734 | 2026-11-20 | 张量、autograd、真实任务和实机参考 | 算子/编译模式与版本要固定；正确性与性能测量分开 |
| [ultralytics/ultralytics](https://github.com/ultralytics/ultralytics) | 63,622 | 2026-11-20 | YOLO 模型训练、验证、导出与端侧任务 | 保留模型/数据/前后处理版本；AGPL-3.0 与商业授权路径分别核对 |
| [jax-ml/jax](https://github.com/jax-ml/jax) | 36,656 | 2026-11-20 | 函数变换、自动微分与 XLA 执行 | 适合可组合算法和加速器计算；区分编译开销与稳态执行 |
| [BVLC/caffe](https://github.com/BVLC/caffe) | 34,556 | 2024-07-31 | 传统 CNN 框架、模型格式与功能参考 | 保留课程输入格式与历史复现用途；近期训练主线优先现代框架 |
| [mlcommons/training](https://github.com/mlcommons/training) | 1,778 | 2026-10-27 | 训练任务、质量目标与参考实现 | 官方说明参考实现未充分优化；性能基线另选匹配优化实现 |
| [mlcommons/inference](https://github.com/mlcommons/inference) | 1,659 | 2026-11-06 | 推理负载、质量门槛与统计协议 | 作为协议和任务参考；子集实验不自动构成 MLPerf 成绩 |

## 4. 编译器与 kernel 编程

对应模块：`compiler`。

在同一设备、shape/dtype 和正确性标准下，对照融合、分块、布局、编译时间与执行性能；记录目标硬件支持差异。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [tinygrad/tinygrad](https://github.com/tinygrad/tinygrad) | 33,954 | 2026-11-20 | 张量、autograd、IR、编译与执行一体化 | 适合阅读较小全栈实现；模型/算子和设备覆盖需验证 |
| [triton-lang/triton](https://github.com/triton-lang/triton) | 20,607 | 2026-11-20 | GPU tiled kernel 的 DSL/编译 | 适合受控内核创新；并行/布局细节与真实 GPU 相关 |
| [apache/tvm](https://github.com/apache/tvm) | 13,913 | 2026-11-19 | 模型/张量编译、变换与部署 | 适合通用编译研究；与现有 IR/执行器的接入范围需收窄 |
| [NVIDIA/cutlass](https://github.com/NVIDIA/cutlass) | 10,747 | 2026-11-20 | CUDA GEMM、层次分解与数据移动原语 | 可作高性能基线；硬件专门化强，核对实际 kernel 与调优 |
| [tile-ai/tilelang](https://github.com/tile-ai/tilelang) | 9,007 | 2026-11-20 | tile 级语言及基于 TVM 的编译 | 适合对比分块与显式控制；不同后端成熟度逐项核对 |
| [openxla/xla](https://github.com/openxla/xla) | 4,684 | 2026-11-20 | 框架图到多类加速器的编译 | 适合 JAX/TF 等路径；构建和后端范围影响接入成本 |
| [iree-org/iree](https://github.com/iree-org/iree) | 4,023 | 2026-11-20 | 基于 MLIR 的编译与 runtime | 适合编译/运行边界及多设备部署；按目标后端验证 |
| [llvm/torch-mlir](https://github.com/llvm/torch-mlir) | 1,949 | 2026-11-20 | PyTorch/ONNX 到 MLIR 生态的编译桥接 | 是前端/IR 组件，与 IREE 等可组合；不当成完整独立运行框架 |
| [google-ai-edge/litert-torch](https://github.com/google-ai-edge/litert-torch) | 1,112 | 2026-11-20 | PyTorch 到 LiteRT 转换与生成式模型接口 | 旧入口 ai-edge-torch 已迁移；是转换组件，运行依赖 LiteRT |
| [sophgo/tpu-mlir](https://github.com/sophgo/tpu-mlir) | 1,023 | 2026-11-18 | Top/Tpu dialect、量化、LayerGroup 与 TPU 部署 | 首批软件调研；提取 LMEM 生命周期/分块/搬运约束，BM 后端不能直接代表通用 NPU 或 CIM |

## 5. Attention 与推理内核

对应模块：`compiler` / `runtime`。

同一 attention 语义、KV 布局、精度、长度、batch 和 GPU 下验证正确性与时延；分清内核库与服务框架。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [Dao-AILab/flash-attention](https://github.com/Dao-AILab/flash-attention) | 25,322 | 2026-11-20 | attention 的 IO 优化与前后向内核 | 不同代实现有硬件/软件条件；数值精度与 dropout 等保持一致 |
| [flashinfer-ai/flashinfer](https://github.com/flashinfer-ai/flashinfer) | 6,965 | 2026-11-20 | 推理 attention/GEMM/MoE 和多后端 | 关注 paged/ragged KV、prefill/decode；固定后端选择 |

## 6. 加速器映射与架构探索

对应模块：`compiler` / `chipmodel` / `evaluation`。

统一 GEMM、阵列/存储预算和合法映射，先比动作与字节，再比时延/能量；将不同分析假设逐项列出。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [scalesim-project/SCALE-Sim](https://github.com/scalesim-project/SCALE-Sim) | 547 | 2026-11-07 | 脉动阵列时序、双缓冲和访存 trace | 适合细化数字阵列；CALC/USER 与 v2/v3 不能混用 |
| [NVlabs/timeloop](https://github.com/NVlabs/timeloop) | 542 | 2026-07-26 | 张量工作负载、架构和 mapping 空间 | 成熟论文基线；映射限制、稀疏与版本语义需固定 |
| [maestro-project/maestro](https://github.com/maestro-project/maestro) | 267 | 2024-04-15 | 数据流、复用、性能与成本分析 | 提供独立表达角度；最近推送为 2024 年，先核对构建和覆盖 |
| [KULeuven-MICAS/zigzag](https://github.com/KULeuven-MICAS/zigzag) | 210 | 2026-11-06 | 联合架构/映射搜索与存储成本 | 可作另一套分析基线；端口/时延/复用模型与 Timeloop 不同 |
| [Accelergy-Project/accelforge](https://github.com/Accelergy-Project/accelforge) | 64 | 2026-11-19 | 融合感知映射、异构张量加速器 | CiMLoop 指向的新入口；低 stars 仍保留，成熟度待复现 |

## 7. 能量、面积与组件成本

对应模块：`costmodel`。

同一组件/动作、工艺、频率和工作条件下对照覆盖、来源、误差与未知项；全芯片模型和组件模型不能重复计费。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [HewlettPackard/cacti](https://github.com/HewlettPackard/cacti) | 587 | 2024-06-25 | cache/memory 访问时间、功耗与面积 | 工艺和存储组织有限；不把参数外推当作独立校准 |
| [HewlettPackard/mcpat](https://github.com/HewlettPackard/mcpat) | 238 | 2020-08-08 | 多核/众核处理器功耗与面积建模 | 不是性能模拟器；最近推送为 2020 年，技术模型适用性需复核 |
| [Accelergy-Project/accelergy](https://github.com/Accelergy-Project/accelergy) | 183 | 2025-05-26 | 动作计数、ERT/ART 与成本插件 | 适合架构动作成本接口；具体插件决定有效性 |
| [neurosim/DNN_NeuroSim_V1.4](https://github.com/neurosim/DNN_NeuroSim_V1.4) | 82 | 2025-03-09 | CIM 器件、阵列与外围成本 | README 明确 CC BY-NC 4.0；工业复用另核授权 |
| [Accelergy-Project/hwcomponents](https://github.com/Accelergy-Project/hwcomponents) | 13 | 2026-06-22 | 组件面积、能量、延迟和漏电模型 | 新成本入口，README 为 Python 3.12+；插件分别核许可 |
| [Accelergy-Project/hwcomponents-neurosim](https://github.com/Accelergy-Project/hwcomponents-neurosim) | 2 | 2026-06-20 | NeuroSim 组件的 HWComponents 适配 | 适合逐动作查询；包装层许可不能替代上游模型许可判断 |
| [Accelergy-Project/hwcomponents-library](https://github.com/Accelergy-Project/hwcomponents-library) | 1 | 2026-06-22 | 公开论文支持的组件成本条目 | 适合追踪来源；引用要求和每条数据适用范围仍需保留 |

## 8. 处理器与 GPU 细模型

对应模块：`chipmodel` / `simulator`。

选择小型 kernel 或 CPU 工作片段，固定 ISA/trace、微架构和统计窗口；比较支持机制、验证数据和仿真开销。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [gem5/gem5](https://github.com/gem5/gem5) | 2,936 | 2026-11-20 | 处理器、内存与系统架构研究 | 选择具体 CPU/系统模式；大型全系统实验成本单独评估 |
| [gpgpu-sim/gpgpu-sim_distribution](https://github.com/gpgpu-sim/gpgpu-sim_distribution) | 1,776 | 2026-10-03 | CUDA/OpenCL GPU 周期级建模 | 与 Accel-Sim 存在后端依赖关系，不能当作完全独立的双重校准 |
| [accel-sim/accel-sim-framework](https://github.com/accel-sim/accel-sim-framework) | 745 | 2026-10-28 | SASS trace、GPU 周期模型与相关性流程 | tracer/trace/模型必须匹配；维护方新版声明需用本负载验证 |

## 9. 存储与片上网络

对应模块：`chipmodel` / `simulator`。

内存用相同请求流、地址映射、时序和读写比例；NoC 用相同拓扑、路由、flit、buffer 和注入方式。不同子系统不直接比较总时间。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [CMU-SAFARI/ramulator2](https://github.com/CMU-SAFARI/ramulator2) | 718 | 2026-11-04 | DRAM 标准、控制器与周期时序 | 当前 README 为 2.1；可独立 trace 或库接入，避免重复队列状态 |
| [umd-memsys/DRAMsim3](https://github.com/umd-memsys/DRAMsim3) | 529 | 2024-08-03 | DRAM 时序、控制器与功耗/热选项 | 与 Ramulator 横向对照；核对刷新、调度和验证范围 |
| [booksim/booksim2](https://github.com/booksim/booksim2) | 491 | 2024-06-24 | NoC 拓扑、路由与 router 微架构 | 补足无争用路径模型；不是 DRAM 或完整 GPU 模拟器 |

## 10. CIM 数值与架构方法

对应模块：`chipmodel` / `workloads` / `costmodel`。

固定阵列/外围、数值范围、噪声假设与输入分布，分别比较任务质量、动作成本与运行开销。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [IBM/aihwkit](https://github.com/IBM/aihwkit) | 530 | 2026-11-18 | 模拟 CIM 数值非理想性与训练/推理 | 适合质量和器件行为研究；不能单独提供完整系统 PPA |
| [mit-emze/cimloop](https://github.com/mit-emze/cimloop) | 106 | 2026-07-09 | CIM 全栈与统计成本方法、论文 artifact | 明确停止维护；保留复现价值，与 AccelForge/HWComponents 对照 |
| [IBM/aihwkit-lightning](https://github.com/IBM/aihwkit-lightning) | 50 | 2026-11-19 | 面向大模型的高效硬件感知训练 | 与 AIHWKit 互补；比较训练速度同时核对保留了哪些器件效应 |

## 11. 节点、服务与事件框架

对应模块：`systemmodel` / `simulator`。

比较描述层次和时间归属：算子/层、请求/服务或组件事件。以同一层或请求 trace 验证所需范围，不能直接互换不同层的总时间。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [microsoft/vidur](https://github.com/microsoft/vidur) | 733 | 2026-08-24 | profiling 驱动的 LLM 服务仿真 | 适合 batch/到达/调度；已有 profile 不自动适用于新设备 |
| [PrincetonUniversity/LLMCompass](https://github.com/PrincetonUniversity/LLMCompass) | 301 | 2025-10-24 | LLM 推理硬件/软件分层建模和 AE | 适合硬件设计空间；分析结论受 kernel/硬件假设约束 |
| [sstsimulator/sst-core](https://github.com/sstsimulator/sst-core) | 210 | 2026-11-13 | 可组合并行离散事件框架 | 提供引擎与接口，实际模型需另外选择 |
| [sstsimulator/sst-elements](https://github.com/sstsimulator/sst-elements) | 126 | 2026-11-13 | SST 的处理器/存储/网络等组件集合 | 与 SST Core 配套；按组件核精度，二者不是竞争替代品 |

## 12. 集群与网络仿真

对应模块：`clustermodel` / `runtime` / `simulator`。

统一节点拓扑、计算 profile、collective 和消息流，比较计算通信重叠、网络粒度及规模开销。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [aliyun/SimAI](https://github.com/aliyun/SimAI) | 1,310 | 2026-09-20 | 训练/通信及扩展推理系统建模 | 核对子模块、计算 profile 和资源预算；根许可与 README 徽章有差异 |
| [astra-sim/astra-sim](https://github.com/astra-sim/astra-sim) | 727 | 2026-10-29 | 分布式 AI、collective 和多精度网络后端 | 适合软件/硬件协同；核对 Chakra trace 与后端版本 |
| [nsnam/ns-3-dev-git](https://github.com/nsnam/ns-3-dev-git) | 568 | 2026-11-19 | 通用离散事件网络仿真 | 提供细网络机制；AI 工作量/collective 和计算行为需要上层连接 |

## 13. 推理运行时与部署

对应模块：`runtime` / `systemmodel`。

先分服务器吞吐、端侧部署、异构设备等场景，再用同一模型、质量、长度分布、到达过程和硬件比较容量、TTFT/TPOT/goodput。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | 135,799 | 2026-11-20 | 多类本地/云硬件上的 LLM/MLLM 推理 | 适合 CPU/边缘/异构与量化；不直接和不同精度的服务器结果排名 |
| [vllm-project/vllm](https://github.com/vllm-project/vllm) | 97,246 | 2026-11-20 | LLM 服务、KV 管理、continuous batching | 强服务基线；固定 kernel、并行、缓存与调度配置 |
| [sgl-project/sglang](https://github.com/sgl-project/sglang) | 38,866 | 2026-11-20 | LLM/多模态服务、缓存与结构化任务执行 | 与 vLLM 横向比较；任务和缓存命中条件保持一致 |
| [Tencent/ncnn](https://github.com/Tencent/ncnn) | 24,076 | 2026-11-20 | 移动/嵌入式/桌面推理，CPU/Vulkan 后端 | 与 MNN 按同模型/设备/精度比较；关注转换与资源限制 |
| [alibaba/MNN](https://github.com/alibaba/MNN) | 16,577 | 2026-11-20 | 轻量模型部署与移动端推理 | 适合端侧软硬件协同；设备后端、转换和算子覆盖逐项验证 |
| [NVIDIA/TensorRT-LLM](https://github.com/NVIDIA/TensorRT-LLM) | 15,106 | 2026-11-20 | NVIDIA GPU 的 LLM 优化与部署 | 适合厂商栈基线；硬件、编译/执行路径与 kernel 条件明确 |
| [NVIDIA/TensorRT](https://github.com/NVIDIA/TensorRT) | 13,473 | 2026-11-18 | TensorRT OSS 插件、ONNX parser 与部署样例 | 仓库仅为 TensorRT 产品的开源组件子集；目标设备与 SDK 许可/版本另核对 |
| [InternLM/lmdeploy](https://github.com/InternLM/lmdeploy) | 8,151 | 2026-11-20 | TurboMind/PyTorch 引擎与量化 LLM 部署 | 与 vLLM/SGLang 同条件比较；语料中的 ModelEngine-Group 地址应改为 InternLM |
| [pytorch/executorch](https://github.com/pytorch/executorch) | 5,182 | 2026-11-20 | PyTorch 导出、内存规划、分区委托与端侧运行 | 首批端侧对照；动态形状/量化/设备能力按导出路径及后端验证 |
| [google-ai-edge/LiteRT](https://github.com/google-ai-edge/LiteRT) | 3,604 | 2026-11-20 | 端侧运行、Compiled Model 与 NPU 编译插件 | 首批端侧对照；当前有异步与 AOT/JIT 路径，不能沿用截图的统一叉号 |
| [vllm-project/vllm-ascend](https://github.com/vllm-project/vllm-ascend) | 3,122 | 2026-11-20 | vLLM 的 Ascend NPU 硬件插件 | 与 vLLM 存在依赖关系；按 NPU/软件版本核对功能，非独立替代引擎 |
| [ONNX Runtime](https://onnxruntime.ai/) | 待核 | 待核 | 通用模型执行和多后端部署候选 | 官网可访问；仓库 API/README 本轮返回 404，保留收录，stars 待复核 |

## 14. 训练运行时与通信

对应模块：`runtime` / `systemmodel` / `workloads`。

同模型、精度、global batch、质量目标和设备拓扑，对照显存、step time、通信/计算重叠以及 time-to-quality。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [deepspeedai/DeepSpeed](https://github.com/deepspeedai/DeepSpeed) | 43,348 | 2026-11-20 | ZeRO、状态分片与 offload 等训练机制 | 容量、通信和性能一起报告；核对实际使用的优化阶段 |
| [hpcaitech/ColossalAI](https://github.com/hpcaitech/ColossalAI) | 41,420 | 2026-11-19 | 多种并行与异构内存管理 | 作为另一套高热度训练框架比较；区分不同插件与模型支持 |
| [NVIDIA/Megatron-LM](https://github.com/NVIDIA/Megatron-LM) | 18,442 | 2026-11-20 | Transformer 训练与多维并行组件 | 适合作为大模型训练基线；固定 Core/框架版本和策略 |
| [huggingface/accelerate](https://github.com/huggingface/accelerate) | 9,950 | 2026-11-18 | PyTorch 分布式训练启动与精度/设备适配 | 是训练脚本的组合层，可用 DeepSpeed 等后端；不能当作完全独立训练算法 |
| [pytorch/torchtitan](https://github.com/pytorch/torchtitan) | 5,927 | 2026-11-20 | PyTorch 原生的可组合分布式训练 | 适合研究并行机制；README 提示活跃开发及 nightly 条件 |
| [NVIDIA/nccl](https://github.com/NVIDIA/nccl) | 5,247 | 2026-11-19 | GPU collective 通信实现 | 是通信组件，可被多个框架共用；基线共享底层库的关系需记录 |

## 15. 实验调度与设计空间探索

对应模块：`evaluation`。

固定目标函数、可行域、评估预算、随机种子与留出集，比较解的质量、失败率、搜索/编排开销和可重现性。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [ray-project/ray](https://github.com/ray-project/ray) | 44,345 | 2026-11-20 | 分布式执行及 Tune/Train/Serve | 适合扩展宿主实验任务；Ray 调度时间不等于目标硬件执行时间 |
| [optuna/optuna](https://github.com/optuna/optuna) | 15,067 | 2026-11-18 | 参数优化与 trial 管理 | 适合先接入简单搜索；不让搜索掩盖未验证的目标函数 |
| [facebookresearch/nevergrad](https://github.com/facebookresearch/nevergrad) | 4,229 | 2026-11-02 | 无梯度、混合离散/连续黑盒优化 | 适合比较多类搜索策略；统一预算和不可行点处理 |
| [meta-pytorch/botorch](https://github.com/meta-pytorch/botorch) | 3,653 | 2026-11-17 | 可编程贝叶斯优化研究原语 | 适合优化算法创新；统计模型与获取函数需要明确设计 |
| [meta/Ax](https://github.com/meta/Ax) | 2,846 | 2026-11-17 | 自适应实验与约束/多目标优化 | 高层实验管理，可使用 BoTorch；适合系统化 DSE |

## 16. 实验记录与产物管理

对应模块：`artifacts` / `evaluation`。

比较本地/远程运行、输入/版本身份、失败记录、大文件引用、离线重分析与迁移能力；SDK 开源不等于全部托管服务能力开放。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [mlflow/mlflow](https://github.com/mlflow/mlflow) | 28,905 | 2026-11-20 | 实验/指标/产物追踪及浏览 | 可选导出端；维持现有不可变 bundle 与目标/宿主指标语义 |
| [treeverse/dvc](https://github.com/treeverse/dvc) | 15,984 | 2026-11-20 | 数据/模型版本、流水线与 Git 关联 | 适合大输入和数据版本；不替代组件数值验证 |
| [wandb/wandb](https://github.com/wandb/wandb) | 11,332 | 2026-11-20 | 实验追踪、可视化与团队协作 SDK | 需区分 SDK、账户/服务与部署条件；采集/上传保持显式可选 |

## 17. 结果 UI 与可视化

对应模块：`ui`。

用同一配置表、比较图和 trace 检验交互、状态、部署和大数据开销；UI 通过现有 evaluation/artifacts 边界工作。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [streamlit/streamlit](https://github.com/streamlit/streamlit) | 46,450 | 2026-11-20 | Python 数据应用、配置与结果面板 | 适合快速研究界面；验证重运行/缓存对模型状态的影响 |
| [gradio-app/gradio](https://github.com/gradio-app/gradio) | 44,096 | 2026-11-20 | 模型或 Python 函数的交互演示 | 适合独立模块演示；复杂研究管理需额外设计 |
| [plotly/dash](https://github.com/plotly/dash) | 24,499 | 2026-11-19 | 回调式交互分析应用 | 适合定制多图联动；界面开发与状态维护工作相对更多 |
| [google/perfetto](https://github.com/google/perfetto) | 6,807 | 2026-11-20 | 执行 trace、时间线与查询分析 | 适合现成轨迹查看；不是配置/实验全流程 UI |

## 18. EDA 与实现证据

对应模块：`costmodel` / `chipmodel` / `evaluation`。

同 RTL、库、时钟和约束下分别检查功能、综合与布局布线证据。三类工具可组成验证链，不能把其输出当成同一种精度。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [YosysHQ/yosys](https://github.com/YosysHQ/yosys) | 4,910 | 2026-11-20 | RTL 综合与技术映射 | 综合结果依赖库/约束；面积/时序不是最终布线结果 |
| [verilator/verilator](https://github.com/verilator/verilator) | 4,097 | 2026-11-20 | Verilog/SystemVerilog 仿真与联调 | 用于功能/行为验证；本身不提供物理功耗和面积 |
| [The-OpenROAD-Project/OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD) | 3,301 | 2026-11-20 | 物理设计与布局布线/PPA | 适合数字局部实现证据；不替代模拟 CIM 电路验证 |

## 19. 量化与低精度训练推理

对应模块：`workloads / compiler / runtime / evaluation`。

固定模型、校准/评估数据、质量门槛和硬件，比较量化方法、精度粒度、累加、元数据与 kernel 成本。算法和部署库可组合，不把 W4A16 与 W8A8 当成相同计算条件。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [mit-han-lab/llm-awq](https://github.com/mit-han-lab/llm-awq) | 3,667 | 2025-07-17 | 低比特权重量化、校准搜索与 TinyChat 内核 | 同时比较质量、权重格式、量化开销和真实 kernel；不以压缩比代替时延收益 |
| [pytorch/ao](https://github.com/pytorch/ao) | 3,029 | 2026-11-19 | PyTorch 量化、低精度训练和推理优化 | README 声明减少新功能，基础能力向 torch、工作流向训练/推理仓库整合 |
| [IST-DASLab/gptq](https://github.com/IST-DASLab/gptq) | 2,402 | 2024-03-27 | GPTQ 原始量化算法与参考 CUDA kernel | 用于方法和历史基线；原始 artifact 的环境/模型覆盖需与现代部署实现分开 |
| [mit-han-lab/smoothquant](https://github.com/mit-han-lab/smoothquant) | 1,704 | 2024-07-12 | 迁移激活离群值难度的 W8A8 PTQ | 与 AWQ/GPTQ 精度配置不同；固定质量门槛，区分 fake quant 与真实 INT8 执行 |

## 20. 自动并行与并行算法研究

对应模块：`compiler / runtime / clustermodel / evaluation`。

与 PyTorch 及第 14 组的 Megatron、DeepSpeed、TorchTitan 对照。固定全局 batch、收敛目标、拓扑与精度，比较划分、通信、显存、重计算与搜索开销。Optimus 仅作背景参考。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [alpa-projects/alpa](https://github.com/alpa-projects/alpa) | 3,176 | 2023-12-09 | 自动组合算子内/算子间及流水并行 | 已归档且 README 声明不活跃；保留论文 artifact，同时查看 XLA auto_sharding |
| [flexflow/flexflow-train](https://github.com/flexflow/flexflow-train) | 1,900 | 2026-11-19 | 分布式训练并行策略搜索 | 旧 FlexFlow 已拆分 train/serve；当前仓库为训练，论文与当前实现范围分开 |
| [xuqifan897/Optimus](https://github.com/xuqifan897/Optimus) | 28 | 2021-07-11 | 二维张量并行训练研究原型 | 历史参考，非首批精读/复现；PyTorch 1.5/SLURM 环境，非集群调度同名项目 |

## 21. 训练集群与多作业调度

对应模块：`runtime / clustermodel / simulator / evaluation`。

固定任务到达、GPU 类型、吞吐 profile、抢占/恢复成本和质量目标，分别比较完成时间、公平性、利用率与 goodput。它们解决多作业分配，层级不同于单模型张量/流水并行。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [petuum/adaptdl](https://github.com/petuum/adaptdl) | 459 | 2023-03-05 | Pollux/AdaptDL 弹性调度与 batch/学习率协同 | 改变 batch 会影响统计效率；比较达到质量目标的时间与 goodput |
| [SymbioticLab/Tiresias](https://github.com/SymbioticLab/Tiresias) | 167 | 2020-05-07 | 缺少完整作业信息时的 GPU 作业调度 | 仓库声明主要提供离散时间模拟；不能等同当前生产调度系统 |
| [stanford-futuredata/gavel](https://github.com/stanford-futuredata/gavel) | 141 | 2024-07-25 | 异构加速器感知的多作业调度与模拟 | 固定异构吞吐矩阵、策略目标和抢占开销；只有需要多作业调度时接入 |
| [pengyanghua/optimus](https://github.com/pengyanghua/optimus) | 36 | 2021-01-11 | 按作业进度/资源性能模型动态分配集群资源 | 历史参考，非首批精读/复现；MXNet/Kubernetes 原型，非二维并行 Optimus |

## 22. KV cache 分层管理与传输

对应模块：`runtime / systemmodel / clustermodel`。

固定模型/KV 身份、请求轨迹、命中条件和存储/互连资源；比较 TTFT、TPOT、尾延迟、字节量和质量。UCM、LMCache、Mooncake 有功能交集也可组成依赖链，不能简单当成三个端到端服务引擎。

| 项目 | GitHub stars | 最近推送（UTC 日期） | 功能侧重 | 比较边界与接入判断 |
| --- | ---: | --- | --- | --- |
| [LMCache/LMCache](https://github.com/LMCache/LMCache) | 12,399 | 2026-11-20 | 跨引擎 KV 分层存储、卸载、复用与观测 | 与 UCM 比较身份/命中/质量/搬运代价；可组合 Mooncake，非完全独立后端 |
| [kvcache-ai/Mooncake](https://github.com/kvcache-ai/Mooncake) | 7,087 | 2026-11-20 | KV 为中心的解耦服务、存储池与传输引擎 | 区分论文系统、Store、Transfer Engine 与上层集成；避免重复计算网络成本 |
| [ModelEngine-Group/unified-cache-management](https://github.com/ModelEngine-Group/unified-cache-management) | 360 | 2026-11-20 | KV 持久化、前缀复用、稀疏检索与 PD 分离 | 与 vLLM/Ascend 版本配套；3–10× 为维护方场景声明，未独立复现 |

## 后续收录与复核规则

新增候选先进入本表和数据快照，记录来源与待核项；不因热度低、暂不接入、维护迁移或一次查询失败而静默删除。迁移项目保存旧入口与 canonical 仓库，停止维护项目保留历史复现价值。进一步扩充按课题进行，避免把本轮清单误称为完整领域排名。

每个进入正式选型的模块至少横向核对三个相关候选；若它们实际上属于依赖链或不同抽象层，应先拆分角色，再选择可比较的子集。初步比较后记录选择与保留理由，复现任务只针对当前研究必要范围。社区指标定期留快照，未来才能计算增长；活跃度还需结合 release、issue/PR 响应与构建情况，本轮未逐项目审核这些维度。

研究计划和实际接入顺序见[研究开发路线](../RESEARCH_ROADMAP.md)；已实现能力见 [STATUS](../STATUS.md)。
