# AI 编译、端侧部署与训练软件语料审阅

核对日期：**2026-11-20**。输入是用户提供的《AI 编译器基础》课程解读文本、两张端侧框架对照截图，以及训练方向的补充。文本注明由飞书 aily 生成；截图没有原始链接、统计日期和版本。本页将其作为研究线索，逐项对照维护方资料，不将课程概括直接作为硬件规格或实验结果。

本轮新增 **25 个候选仓库、14 篇代表论文记录**，累计 **102 个候选、44 篇代表论文、22 组选型对照**。GitHub stars、fork、最近推送、许可、README 哈希和论文引用统一维护在[全量对照](open_source_comparison.md)、[调研报告](open_source_landscape.md)与[数据快照](data/open_source_snapshot_2026-11-20.json)；补充技术来源见[语料来源记录](data/ai_software_sources_2026-11-20.json)。本轮完成资料核对，没有构建外部工具、执行性能实验或实现编译/训练模块。

以上“本轮”指资料调研批次。其后已完成窄范围[线性映射实验](../../evaluation/docs/linear_mapping.md)；最新实现边界与验证统一见 [STATUS](../STATUS.md)，训练和外部工具适配仍待推进。

## 1 对 UniverseModel 有什么用

**这些材料与项目使命直接相关：它们补充了从真实 AI 任务，经编译和执行策略，到硬件资源与实验评价的连接方式。** 最值得提取的是可比较的机制、输入输出和验证方法。

| 材料主题 | UniverseModel 归属 | 应研究和比较的内容 | 参考项目 |
| --- | --- | --- | --- |
| 图表示与逐层 lowering | `contracts`、`workloads`、`compiler/src/ir`、`lowering` | 算子、shape、dtype、layout、effect 与目标能力；转换后如何验证语义 | PyTorch、ONNX、MLIR、torch-mlir、TVM、IREE、tpu-mlir |
| LayerGroup、融合与分块 | `compiler/src/tiling`、`memplan`、`sched` | 跨算子 ROI、活跃区间、容量合法性、冗余计算、数据复用与搬运 | tpu-mlir、TVM、IREE、ExecuTorch；用 Timeloop/ZigZag 对照映射计量 |
| DMA 与计算协同 | `compiler/src/sched`、`chipmodel`；需要争用时接入 `runtime/simulator` | 双缓冲容量、数据就绪、bank/端口冲突、共享链路、依赖与释放 | tpu-mlir、IREE、Triton、CUTLASS；细节按目标硬件验证 |
| 量化及 CIM 数值质量 | `workloads`、`compiler`、`evaluation`，结合 `chipmodel/costmodel` | 权重/激活/累加精度、校准、编码/解码、任务质量与物理成本 | AWQ、GPTQ、SmoothQuant、TorchAO、AIHWKit；CIM 成本另用相应模型 |
| 端侧及异构部署 | `compiler`、`runtime`、`systemmodel` | 子图划分、后端委托、CPU fallback、复制/同步和部署产物 | TVM、IREE、ExecuTorch、LiteRT、ONNX Runtime、MNN、ncnn、TensorRT |
| LLM 服务与 KV 管理 | `runtime`、`systemmodel`，按需扩展 `clustermodel` | 请求、batch、KV 身份/生命周期、缓存复用、PD 分离、存储与传输 | vLLM、SGLang、TensorRT-LLM、LMDeploy、vLLM-Ascend；UCM、LMCache、Mooncake |
| 训练与自动并行 | `workloads`、`compiler/src/globalsplit`、`globalsolver`、`runtime`、`clustermodel` | 前向/反向/更新、分片、通信、显存、重计算、流水和训练质量 | PyTorch、Megatron-LM、DeepSpeed、TorchTitan、ColossalAI；Alpa、FlexFlow Train |

这些是研究归属和待实现能力，不改变当前 [STATUS](../STATUS.md)。现有 compiler 的[模块设计](../../compiler/docs/design.md)与[切块/归约约束](../../compiler/docs/tiling_and_reduction.md)已经提供了相应边界，可以沿着真实案例补齐。无需因阅读 MLIR 就立即实现一套完整自定义 dialect，也不能把整个外部框架塞进公共 contracts。

## 2 收录结果与项目身份

**原先已经收录：** LLVM/MLIR、ONNX、PyTorch、TensorFlow、TVM、IREE、XLA、FlashAttention、vLLM、TensorRT-LLM、ONNX Runtime，以及 Megatron-LM、DeepSpeed、TorchTitan、ColossalAI、NCCL 等。TFLite 的历史实现与 TensorFlow 生态相关；ONNX Runtime Mobile 是 ORT 的部署用途，不另造一个独立仓库计数。

本轮新增候选分为六组：

| 方向 | 新增项目 | 主要价值 |
| --- | --- | --- |
| 编译及端侧 | tpu-mlir、torch-mlir、ExecuTorch、LiteRT、LiteRT Torch、TensorRT OSS | 编译接口、内存规划、后端接入和部署边界 |
| 模型任务 | Ultralytics、Caffe | CV 训练/导出/质量参考，以及历史格式兼容 |
| 量化 | AWQ、GPTQ、SmoothQuant、TorchAO | 算法、格式、精度及真实低精度执行的横向比较 |
| 服务与 KV | LMDeploy、vLLM-Ascend、UCM、LMCache、Mooncake | 推理引擎、硬件插件、缓存管理和传输组件 |
| 训练组合与自动并行 | Accelerate、Alpa、FlexFlow Train、Optimus 二维并行 | 训练启动、并行划分和策略搜索；历史 artifact 另标状态 |
| 训练作业调度 | Gavel、Pollux/AdaptDL、Tiresias、Optimus 集群调度 | 多作业资源分配、异构性、公平性、弹性和 goodput |

需要保留的身份与版本纠正：

- **LMDeploy 是 [InternLM/lmdeploy](https://github.com/InternLM/lmdeploy)**，语料给出的 `ModelEngine-Group/lmdeploy` 不作为正式入口。
- `ai-edge-torch` 入口已迁移至 [google-ai-edge/litert-torch](https://github.com/google-ai-edge/litert-torch)，当前名称为 LiteRT Torch；它负责转换，LiteRT 负责运行等后续工作。
- 原 FlexFlow 入口当前指向 [flexflow-train](https://github.com/flexflow/flexflow-train)，维护方已拆分训练与服务仓库；当前训练仓库不代表全部历史部署能力。
- [Alpa](https://github.com/alpa-projects/alpa) 已归档，README 明示不再积极维护，并指向 XLA 的 auto_sharding；保留论文复现价值。TorchAO README 也说明减少新功能开发、将能力整合到 torch 和使用它的训练/推理仓库，需要跟踪维护去向。
- 两个训练相关 Optimus 分别为 [二维并行原型](https://github.com/xuqifan897/Optimus)与[集群调度原型](https://github.com/pengyanghua/optimus)。按用户最新方向，**都仅作历史背景，不进入首批精读与复现**。

候选收录不等于依赖选定。例如 vLLM-Ascend 是 vLLM 插件，Accelerate 可组合 DeepSpeed，LMCache 可使用 Mooncake；这些关系影响比较的独立性和成本归属。

## 3 课程文本中需要纠正或补证的内容

| 原材料中的说法 | 核对结论及采用方式 |
| --- | --- |
| GMEM 一律是片上全局 SRAM；LayerGroup 主要复用 GMEM | **应修正。** tpu-mlir 的 [LayerGroup 文档](https://github.com/sophgo/tpu-mlir/blob/master/docs/developer_manual/source_en/10_layergroup.rst)明确以有限 LMEM 内的切片执行、生命周期和分配减少 GMEM↔LMEM 复制。不能把某一命名直接固定成通用 DDR→GMEM→LMEM 三层物理结构。 |
| 非对称量化将整数 zero-point 放在除法之前 | **公式不一致。** 采用整数零点时应使用下文公式；舍入、饱和、量化轴和 scale 形状仍须显式定义。依据 [MLIR Quantization](https://mlir.llvm.org/docs/Quantization/)。 |
| tpu-mlir 的 BModel 部署效果用 Jetson Orin NX 的 FPS 举例 | **平台归属不成立。** 当前官方示例目标为 BM1684X/BM1688/CV186AH 等。缺少具体编译路径及测量记录时，不能把 NVIDIA Jetson 的数字归给该 BModel 工具链。 |
| KV cache 使完整生成复杂度变为线性 | **统计范围缺失。** 缓存避免历史 K/V 投影的重复计算；标准稠密注意力每个 decode token 仍需读取/处理增长的上下文。不能由单步节省推导完整生成的所有工作都为线性。 |
| W4A16 都要先把 INT4 解包成 INT8；CIM 可直接消除这类成本 | **不能泛化。** 解码、缩放、乘法与累加方式依硬件/kernel；CIM 还需计编码、bit slicing、外围转换和精度代价。4×/8× 是特定位宽假设下的理想权重数据比，不是总内存或加速比。 |
| NPU/CIM 必须完全静态调度；所有同类设备有类似带宽/容量 | **不作为架构要求。** 静态和动态职责由具体目标能力决定；计算、存储、搬运、控制必须有显式资源边界。未注明产品/模式的延迟和带宽不能当校准参数。 |
| LLVM/MLIR 的 SmallVector 一定在栈上、isa/dyn_cast 纯编译期且稳定快十倍、所有定义必须用 TableGen | **作为基础知识纠错。** inline storage 随对象位置；类型查询涉及运行期对象种类；TableGen 是常用声明生成路径。没有对应测量不能保留固定倍数。SSA 值的单次定义也不意味着其引用的内存不可变。 |
| MLIR 论文为 CGO 2020；TopToTpu 等同 Tensor→MemRef | **应区分。** 总表收录的是 CGO 2021 正式 MLIR 论文。Top→Tpu 的目标相关 lowering 与一般 bufferization 是不同概念，具体步骤以目标版本为准。 |

整数 zero-point 约定下，对实数值 `x`、正 scale `s` 和整数零点 `z`：

```text
q = clip(round(x / s) + z, q_min, q_max)
x_hat = s * (q - z)
```

`q/z` 在量化整数域，`s` 表示每个量化整数步长对应的实数尺度。量化质量需要指定数据、指标和阈值；原材料中没有任务定义的“精度百分比”不进入结果表。量化误差与模拟 CIM 非理想性也不应当作同一种噪声处理。

论文与收益声明分别处理：

- **Hybe 与 Kelle 已确认论文身份。** 分别见 [ISCA 2025 官方议程](https://www.iscaconf.org/isca2025/program/)与 [MICRO 2025 官方议程](https://microarch.org/micro58/program/)，适合继续研究 GPU/NPU 协同及 KV/eDRAM 协同。本轮没有确认开源代码和复现实验，不采纳语料中的 2.1×/3.9× 等数字为已验证结论。
- **UCM 确有对应仓库。** README 声明支持 vLLM 和 vLLM-Ascend，列出前缀缓存、稀疏检索和 PD 分离。3–10× 来自维护方声明，仍须核对请求、命中率、硬件、质量和基线，不能解释为任意请求都提升这些倍数。
- **“XgenSilicon MICRO ’25”暂未确认。** 本轮 OpenAlex 结果与所查 MICRO 2025 议程未找到相符论文；保留待核，不据此论证 KL 校准，也不声称工作不存在。
- 与特定企业内部研究方向有关的描述没有原始来源，本轮不将其写为事实或 UniverseModel 的范围限制。

## 4 两张端侧框架表怎样使用

截图选择的五个对象很有价值，比较字段也可以复用；具体单元格需要重做。TVM/IREE 涵盖编译与执行；ExecuTorch/LiteRT/ORT 也存在转换、图优化、分区、后端编译等不同职责，不能靠“推理框架”标签推断没有编译工作。

| 对照维度 | 修订后的核对方法 |
| --- | --- |
| AOT / JIT / codegen | 分别记录离线图转换、内存规划、目标代码生成、加载时编译与后端委托。[LiteRT 后端文档](https://github.com/google-ai-edge/LiteRT/blob/main/litert/BUILD_YOUR_OWN_BACKEND.md)明确有离线 AOT 和设备端 JIT；[ORT](https://onnxruntime.ai/docs/performance/model-optimizations/graph-optimizations.html)支持离线图优化，这又不等于所有后端都生成原生代码。 |
| 异步与并行 | 区分异步 API、设备队列、算子并行、多请求并发和传输重叠。当前 [LiteRT README](https://github.com/google-ai-edge/LiteRT)明确提供异步执行；截图的统一“同步阻塞”结论已不适用。 |
| Dynamic shape | 分导出、IR、内存规划、kernel、delegate 和运行时检查范围。[ExecuTorch 内存规划](https://github.com/pytorch/executorch/blob/main/docs/source/compiler-memory-planning.md)明确处理符号形状和用户提供的 ValueRange；上界分配不等于输入必须固定。具体后端限制仍需实验。 |
| 模型输入 | 标明原生入口、转换链、覆盖算子、fallback 和损失。ONNX→第三方转换→PyTorch 不等于 ExecuTorch 原生完整 ONNX 支持。当前 TVM README 已使用 Relax，截图中的 Relay 路径需要绑定历史版本。 |
| 运行库大小 | 同一目标架构、编译参数、算子裁剪、静态/动态链接和依赖范围下实测；同时报告可执行文件、依赖、权重和运行时峰值。截图的几十 KB/几百 KB 缺测量口径，不作为排名。 |
| 后端/设备/OS | 拆开 CPU ISA、设备、API、库及操作系统；截图将 ARM、Vulkan、XNNPACK、QNN 等放在同一层，容易误判覆盖。 |
| 活跃度/成熟度 | stars 保留带日期快照；PR/issue 定义时间窗与计数方法；项目起始时间、厂商采用和商业成熟度要有原始证据。截图中“某大厂不用 TVM”不能作选型事实。 |

后续端侧横向比较保留 **TVM、IREE、ExecuTorch、LiteRT、ORT、MNN、ncnn**；TensorRT 提供 NVIDIA 设备上的对照。先选共同支持的小模型与一套相同设备条件；CPU 和 NPU/GPU 分别给出结果，不能把不同目标下的库体积、功能和时延混排。

## 5 训练方向必须独立梳理

训练涉及反向、优化器状态、激活保存/重计算、同步和收敛行为，不能用推理矩阵乘工作量简单乘常数表示。PyTorch、Megatron 等已经在总表，但需要把它们在软件栈中的位置展开。

| 层次 | 横向候选 | 优先研究内容 |
| --- | --- | --- |
| 张量/自动微分/图编译 | **PyTorch**；JAX、TensorFlow/XLA | forward/backward 语义、图捕获、编译、融合、动态形状；建立独立梯度/更新参考 |
| 单个训练作业的分布式执行 | **Megatron-LM/Core、DeepSpeed、PyTorch 分布式能力、TorchTitan**；ColossalAI | DP/FSDP/ZeRO、TP/PP/CP/EP 的工作划分、状态分片、通信和显存；按具体版本选择共同能力 |
| 训练组合与低精度 | Accelerate、TorchTitan、TorchAO 及其当前迁移目标 | 启动/适配层与算法区分；低精度、累加、损失缩放、重计算和 checkpoint；记录稳定性与质量 |
| 自动并行与优化 | Alpa/XLA auto_sharding、FlexFlow Train、手工 Megatron/TorchTitan 策略 | 划分与搜索目标、profile 依赖、搜索成本、约束和最优性差距；历史 Optimus 二维并行仅作补充 |
| 通信与集群证据 | NCCL；ASTRA-sim、SimAI、ns-3 | 真实通信实现与模型分层；collective、拓扑、拥塞、计算通信重叠及校准 |
| 多作业资源分配 | Gavel、Pollux/AdaptDL、Tiresias；历史 Optimus 调度 | 只有研究多租户、异构资源或弹性时深入；作业完成时间、公平性、抢占、goodput 与收敛代价 |

[TorchTitan](https://github.com/pytorch/torchtitan) 的当前官方说明列出 FSDP2、DTensor/DeviceMesh、张量/流水/上下文/专家并行、activation checkpointing 和 torch.compile，可作为 PyTorch 组件如何组合成训练系统的阅读入口。Megatron-LM/Core 与 DeepSpeed 提供不同工程组织及优化路径，应与其横向对照，避免只学习一套框架的抽象。

训练调查卡至少包含：模型/数据/序列长度、优化器、精度、全局及微 batch、累积步数、质量目标、并行策略、拓扑、通信后端、重计算和 offload、峰值显存、step time、吞吐、checkpoint 成本、失败和恢复边界。比较 batch 不同或数值方法不同时，补充达到质量目标的时间；tokens/s、GPU 利用率或 MFU 单独不能证明训练更有效。

## 6 对近期路线的具体补充

**首批精读优先：PyTorch、Megatron-LM、DeepSpeed、TorchTitan；TVM、IREE、tpu-mlir；端侧并列对照 ExecuTorch、LiteRT、ORT。** 全量候选继续保留；优先调查不等于一次安装全部软件。现有硬件映射与成本工具调研继续进行。

1. **软件调查卡。** 沿一个小图追踪输入、IR、划分/计划、内存、部署产物与观测结果。记录与 UniverseModel 哪个接口对应、哪些状态由外部工具拥有；用同一问题比较多个候选。
2. **维持首个 GEMM/MatVec 平台实验。** 在既有[路线](../RESEARCH_ROADMAP.md)上补充 LayerGroup 式的依赖和内存问题：先比较两种分块/驻留方案，再用短算子链检验跨算子复用。静态工作量与容量先对齐；需要排队和争用时才加入事件机制。
3. **预备训练实验规约。** 选小型 MLP 或 Transformer block，明确 forward/backward/optimizer step；CPU 上先校验数值和状态账本。有合适 GPU 后，在 PyTorch/FSDP、Megatron、DeepSpeed、TorchTitan 中选语义能对齐的子集，比较两种策略；大模型预训练和多机不是入门验收条件。
4. **按研究问题扩展。** 质量问题接量化/CIM，端侧问题接 delegate/fallback，长上下文接 KV 管理，多机问题接通信模型。每次扩展说明假设、强基线、消融和证据，不将集成框架本身视作论文创新。

这些任务是开发路线的资料和实验输入。正式优先级由路线维护，已实现状态由 STATUS 维护；长期使命无需因这批课程材料改变。
