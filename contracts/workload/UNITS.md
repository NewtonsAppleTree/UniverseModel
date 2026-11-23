# workload：稠密线性算子公共语义

`LinearSpec` 定义 `A[M,K] @ B[K,N] → C[M,N]`；`LinearInputs` 拥有两个不可变、行主序的标量序列快照。不拥有硬件、映射、目标时间或输入生成状态。当前是 `dense-linear/v1`，不代表完整 WorkloadSpec/图 schema。

M/N/K 是正整数元素数，N=1 可表达 MatVec。INT8 输入范围 [-128,127]，INT64 累加/输出；保守要求 `K*128*128 <= 2**63-1`，覆盖所有中间和。float64 必须显式传 Python float，禁止非有限输入；输出有限性由执行方校验。无转置、bias、稀疏跳零、量化 scale、FMA 或零长度张量。

使用：创建 spec/inputs → `validate_inputs` → `input_identity` → 下游消费。身份同时绑定语义与实际数据，不能用 seed 替代实际输入身份。主要敏感参数是尺寸、格式和累加范围；字节大小与工作量不构成物理成本。验证见[工作负载测试](../../tests/workloads/test_linear.py)；生成和参考由 [workloads](../../workloads/UNITS.md) 提供。

## 训练值边界

`training.py` 新增 TrainingSpec、TrainingState、TrainingInputs、TrainingGradients、TrainingResult。支持 float64、无 bias 的 Linear 链与隐层 ReLU/identity、全输出 mean MSE 和 plain SGD；不支持量化训练、momentum 或分布式状态。W 布局 [in,out]，反向零点导数取 0。

state/version 与内容哈希共同绑定梯度；调用方持有不可变旧状态，更新产生 version+1。构造时冻结嵌套数组并检查有限标量，消费时按 batch/widths 校验形状。输入、梯度与新状态分别存储，loss/预测属于更新前。关键量是尺寸/学习率、浮点容差及状态身份。公式、独立参考与版本反例见[训练指南](../../evaluation/docs/training_step.md)。

<!-- model-fields:start -->

### [linear.py](linear.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `LinearSpec` | `m` | `int` | element | Output rows M [element]; >0. |
| `LinearSpec` | `n` | `int` | element | Output columns N [element]; >0, N=1 also represents MatVec. |
| `LinearSpec` | `k` | `int` | element | Reduction extent K [element]; >0. |
| `LinearSpec` | `dtype` | `Literal['int8', 'float64']` | —（结构/对象） | Operand format; signed INT8 or finite IEEE binary64. |
| `LinearSpec` | `schema_version` | `Literal['dense-linear/v1']` | —（结构/对象） | Semantics version, not a hardware identity. |
| `LinearSpec` | `operand_bytes` | `int` | —（结构/对象） | 只读派生属性；Byte-addressable operand storage: INT8=1 B, binary64=8 B per element. |
| `LinearSpec` | `result_bytes` | `int` | —（结构/对象） | 只读派生属性；Accumulators and outputs use INT64 or binary64, both 8 B per element. |
| `LinearSpec` | `result_dtype` | `str` | 1（标识/枚举） | 只读派生属性；Explicit accumulation/output format; output is never implicitly requantized to INT8. |
| `LinearSpec` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Bind mappings and input identities to complete versioned semantics. |
| `LinearInputs` | `a` | `tuple[int \| float, ...]` | element value | Flattened A, offset i*K+p [element value]. |
| `LinearInputs` | `b` | `tuple[int \| float, ...]` | element value | Flattened B, offset p*N+j [element value]. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `positive_int(name: str, value: int)` | Require a positive discrete extent/capacity; bool is never an integer parameter. |
| `LinearSpec` | A[M,K] @ B[K,N] -> C[M,N]; dense row-major, alpha=1, beta=0, no bias/transpose/FMA. |
| `LinearSpec.operand_bytes` | Byte-addressable operand storage: INT8=1 B, binary64=8 B per element. |
| `LinearSpec.result_bytes` | Accumulators and outputs use INT64 or binary64, both 8 B per element. |
| `LinearSpec.result_dtype` | Explicit accumulation/output format; output is never implicitly requantized to INT8. |
| `LinearSpec.identity_hash` | Bind mappings and input identities to complete versioned semantics. |
| `LinearInputs` | Inline immutable row-major operands; shape and format are validated against a LinearSpec. |
| `validate_inputs(spec: LinearSpec, inputs: LinearInputs)` | Check lengths and actual scalar representation before any consumer accesses an operand. |
| `input_identity(spec: LinearSpec, inputs: LinearInputs)` | Content identity includes shape/format semantics as well as both actual operand buffers. |

### [training.py](training.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `TrainingSpec` | `batch_size` | `int` | sample | Batch B [sample]; positive. |
| `TrainingSpec` | `widths` | `tuple[int, ...]` | element | Input, optional hidden, output widths [element]; at least two positive widths. |
| `TrainingSpec` | `hidden_activation` | `Literal['identity', 'relu']` | —（结构/对象） | Applied between Linear layers only. |
| `TrainingSpec` | `dtype` | `Literal['float64']` | —（结构/对象） | All inputs, weights, activations, gradients and updates use binary64. |
| `TrainingSpec` | `schema_version` | `Literal['linear-training/v1']` | —（结构/对象） | Fixed mean-MSE/plain-SGD semantics. |
| `TrainingSpec` | `parameter_elements` | `int` | —（结构/对象） | 只读派生属性；All dense parameter elements P=sum(d_l*d_(l+1)); bias and optimizer states are absent. |
| `TrainingSpec` | `gemm_macs` | `int` | —（结构/对象） | 只读派生属性；Full forward, all dW and all dX execute 3*B*P MAC, excluding separate scalar actions. |
| `TrainingState` | `version` | `int` | step | Logical update version [step]; >=0, incremented even for learning_rate=0. |
| `TrainingState` | `weights` | `tuple[tuple[float, ...], ...]` | —（结构/对象） | Owned immutable parameter buffers; no optimizer momentum state. |
| `TrainingState` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Bind both parameter contents and logical version, preventing same-version foreign-gradient reuse. |
| `TrainingInputs` | `x` | `tuple[float, ...]` | B,d_0 | Row-major input [B,d_0]. |
| `TrainingInputs` | `target` | `tuple[float, ...]` | B,d_L | Row-major regression target [B,d_L]. |
| `TrainingGradients` | `state_identity` | `str` | 1（标识/枚举） | SHA256 of source TrainingState; distinct from a workload or run identity. |
| `TrainingGradients` | `state_version` | `int` | step | Source parameter version [step]; must match before applying SGD. |
| `TrainingGradients` | `weights` | `tuple[tuple[float, ...], ...]` | —（结构/对象） | dLoss/dW_l in the same layout as each weight. |
| `TrainingGradients` | `x` | `tuple[float, ...]` | B,d_0 | dLoss/dX [B,d_0]; all input gradients are computed. |
| `TrainingResult` | `loss` | `float` | value squared | Mean squared error sum((prediction-target)^2)/(B*d_L) [value squared]. |
| `TrainingResult` | `prediction` | `tuple[float, ...]` | B,d_L | Pre-update output [B,d_L]. |
| `TrainingResult` | `gradients` | `TrainingGradients` | —（结构/对象） | Derivatives with respect to the old state and input. |
| `TrainingResult` | `next_state` | `TrainingState` | —（结构/对象） | Updated weights, version=old.version+1; original state remains unchanged. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `float_buffer(values: tuple[float, ...])` | Snapshot an explicitly binary64 flat buffer; no coercion of bool, integer or nonfinite values. |
| `validate_learning_rate(value: float)` | Validate SGD learning rate; zero is useful for a gradient-only observation with a new step version. |
| `TrainingSpec` | Bias-free dense chain; hidden ReLU has derivative zero at zero and MSE averages all output elements. |
| `TrainingSpec.parameter_elements` | All dense parameter elements P=sum(d_l*d_(l+1)); bias and optimizer states are absent. |
| `TrainingSpec.gemm_macs` | Full forward, all dW and all dX execute 3*B*P MAC, excluding separate scalar actions. |
| `TrainingState` | A step consumes an immutable parameter snapshot; matrix W_l is row-major [in_width,out_width]. |
| `TrainingState.identity_hash` | Bind both parameter contents and logical version, preventing same-version foreign-gradient reuse. |
| `TrainingInputs` | Actual training data is part of every saved experiment, not inferred from shape or seed alone. |
| `TrainingGradients` | Gradients identify the exact parameter snapshot used during differentiation. |
| `TrainingResult` | Numeric result separates pre-update prediction/loss/gradients from the next immutable state. |
| `validate_training(spec: TrainingSpec, state: TrainingState, inputs: TrainingInputs)` | Validate parameter and data shapes without referring to any mapped plan or target resource. |

<!-- model-fields:end -->
