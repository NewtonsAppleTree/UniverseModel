# sched：训练短链的显式静态阶段与生命周期

`build_training_plan` 产生 float64、无 bias 的 Linear 链，支持隐层 ReLU/identity、mean MSE、完整 dW/dX 和 SGD。顺序为前向 → loss → 逐层反向 → 所有更新，旧权重不会被提前覆盖。每个 GEMM 附带已有 tile、scratch 和逐行流量计划；反向的输入/权重转置实际材料化。

`TrainingTensor` 是命名 backing 张量，非 GPU 物理地址；`TrainingOperation` 是固定枚举的语义操作。`analyze_training_memory` 独立检查唯一生产、定义后使用、所有声明都有来源；返回 inclusive birth/last-use 区间和逐阶段同时占用。输入 birth=-1，保留输出 last_use=N（阶段总数）；某阶段的输入和输出同时活跃，不能用破坏性覆盖降低峰值。解释执行按这些区间释放局部 lease。

关键输入是 batch/层宽/隐层激活、最大 tile、GEMM scratch [B]、backing 容量 [B] 和 max_macs [宿主工作限制]。每张量 bytes=8·rows·columns；backing 峰值=max_stage Σ同阶段活跃张量 bytes。它和 GEMM scratch 是不同资源；不能相加后称完整显存，辅助寄存器、框架 allocator 与缓存仍未建模。

每层前向、dW、dX 各执行 B·din·dout MAC；dW 的 K 是 batch，dX 的 K 是 dout。ReLU 的比较/选择、MSE/SGD 标量动作和转置元素另计。辅助 payload 假设每操作每输入读取一次、每输出写一次；GEMM 使用自身重复装载账本，禁止再加全张量搬运而重复计量。

调用：TrainingSpec/映射/双容量 → lowering → 生命周期验证 → 功能解释或实验分析。当前不接受任意外部训练图执行；生命周期分析器可单独用手工数据验证。依据和限制见[训练指南](../../../evaluation/docs/training_step.md)，反例见[训练编译测试](../../tests/test_training.py)。无目标时钟、事件调度、物理校准或峰值显存的框架等价主张。

<!-- model-fields:start -->

### [training.py](training.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `TrainingTensor` | `name` | `str` | 1（标识/枚举） | Unique data/version identity in one step, not a physical memory address. |
| `TrainingTensor` | `rows` | `int` | element | Row-major matrix rows [element]; scalars are 1x1. |
| `TrainingTensor` | `columns` | `int` | element | Row-major matrix columns [element]. |
| `TrainingTensor` | `initial` | `bool` | 1（布尔） | Available at step entry; x/target and old parameters. |
| `TrainingTensor` | `retained` | `bool` | 1（布尔） | Must remain observable through the step boundary. |
| `TrainingTensor` | `size_bytes` | `int` | —（结构/对象） | 只读派生属性；All training tensors store binary64, including scalar loss and gradients. |
| `TrainingOperation` | `kind` | `Literal['gemm', 'transpose', 'relu', 'relu_backward', 'mse', 'sgd']` | —（结构/对象） | Fixed operation semantics. |
| `TrainingOperation` | `reads` | `tuple[str, ...]` | 1（标识/枚举） | Backing tensors read during this operation; must already be defined. |
| `TrainingOperation` | `writes` | `tuple[str, ...]` | 1（标识/枚举） | Fresh tensors produced; updates never overwrite old weights. |
| `TrainingOperation` | `arithmetic_operations` | `int` | operation | Auxiliary scalar add/subtract/multiply/divide count [operation]. |
| `TrainingOperation` | `comparisons` | `int` | comparison | ReLU predicates [comparison]. |
| `TrainingOperation` | `selections` | `int` | selection | ReLU masked choices [selection], separate from arithmetic. |
| `TrainingOperation` | `transpose_elements` | `int` | element | Elements explicitly rearranged [element]. |
| `TrainingOperation` | `gemm` | `LinearSpec \| None` | —（结构/对象） | Dense contraction semantics for GEMM only. |
| `TrainingOperation` | `mapping` | `LinearPlan \| None` | —（结构/对象） | Ordered GEMM tile updates; no target-time events. |
| `TrainingOperation` | `scratch` | `LinearMemory \| None` | B | Reserved GEMM scratch [B]; auxiliary register demand is unmodeled. |
| `TrainingOperation` | `traffic` | `LinearTraffic \| None` | —（结构/对象） | GEMM backing-to-scratch row requests; no duplicated full-tensor traffic. |
| `TensorLifetime` | `name` | `str` | 1（标识/枚举） | Allocation identity tied to TrainingTensor. |
| `TensorLifetime` | `size_bytes` | `int` | B | Packed backing-store allocation [B]. |
| `TensorLifetime` | `birth` | `int` | —（结构/对象） | -1 for inputs, otherwise producing operation index. |
| `TensorLifetime` | `last_use` | `int` | —（结构/对象） | Last consuming operation, or operation_count for retained results. |
| `TrainingMemoryPoint` | `operation_index` | `int` | —（结构/对象） | -1 initial, 0..N-1 operation, N final observation. |
| `TrainingMemoryPoint` | `live_names` | `tuple[str, ...]` | 1（标识/枚举） | Simultaneously live named backing allocations. |
| `TrainingMemoryPoint` | `live_bytes` | `int` | B | Sum of these allocations [B]; scratch and host objects excluded. |
| `TrainingMemory` | `lifetimes` | `tuple[TensorLifetime, ...]` | —（结构/对象） | One disjoint allocation lifetime per declared tensor. |
| `TrainingMemory` | `points` | `tuple[TrainingMemoryPoint, ...]` | —（结构/对象） | Occupancy through all serial operations. |
| `TrainingMemory` | `peak_bytes` | `int` | B | max(points.live_bytes) [B]. |
| `TrainingMemory` | `capacity_bytes` | `int` | B | Declared backing-store capacity [B]; independent from GEMM scratch. |
| `TrainingPlan` | `tensors` | `tuple[TrainingTensor, ...]` | —（结构/对象） | Shape, ownership and observation boundaries. |
| `TrainingPlan` | `operations` | `tuple[TrainingOperation, ...]` | —（结构/对象） | Forward, loss, reverse differentiation, then all SGD updates. |
| `TrainingPlan` | `memory` | `TrainingMemory` | —（结构/对象） | Backing-store lifetime check; does not model auxiliary compute registers. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `TrainingTensor` | Named dense backing-store allocation; scratch is a separate resource and host snapshots are excluded. |
| `TrainingTensor.size_bytes` | All training tensors store binary64, including scalar loss and gradients. |
| `TrainingOperation` | One serial semantic operation; GEMM subplans include real tails and the existing row-request accounting. |
| `TensorLifetime` | Inclusive birth/last-use interval; inputs and freshly allocated outputs coexist within one operation. |
| `TrainingMemoryPoint` | Each point is a serial operation boundary occupancy, not a cycle or event timestamp. |
| `TrainingMemory` | Static backing-memory feasibility is exact for this materializing schedule, not a GPU allocator prediction. |
| `TrainingPlan` | A built schedule contains only the requested training recipe and its static feasibility evidence. |
| `analyze_training_memory(tensors: tuple[TrainingTensor, ...], operations: tuple[TrainingOperation, ...], capacity_bytes: int)` | Check single production, definition-before-use and retained outputs independently of the schedule builder. |
| `build_training_plan(spec: TrainingSpec, tile: TileShape, strategy: str, *, scratch_capacity_bytes: int, backing_capacity_bytes: int, max_macs: int=1000000)` | Lower a bounded chain; transposes are real allocations and old weights remain until backward finishes. |

<!-- model-fields:end -->
