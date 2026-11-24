# workload：稠密线性算子公共语义

`LinearSpec` 定义 `A[M,K] @ B[K,N] → C[M,N]`；`LinearInputs` 拥有两个不可变、行主序的标量序列快照。不拥有硬件、映射、目标时间或输入生成状态。当前是 `dense-linear/v1`，不代表完整 WorkloadSpec/图 schema。

M/N/K 是正整数元素数，N=1 可表达 MatVec。INT8 输入范围 [-128,127]，INT64 累加/输出；保守要求 `K*128*128 <= 2**63-1`，覆盖所有中间和。float64 必须显式传 Python float，禁止非有限输入；输出有限性由执行方校验。无转置、bias、稀疏跳零、量化 scale、FMA 或零长度张量。

使用：创建 spec/inputs → `validate_inputs` → `input_identity` → 下游消费。身份同时绑定语义与实际数据，不能用 seed 替代实际输入身份。主要敏感参数是尺寸、格式和累加范围；字节大小与工作量不构成物理成本。验证见[工作负载测试](../../tests/workloads/test_linear.py)；生成和参考由 [workloads](../../workloads/UNITS.md) 提供。

## 训练值边界

`training.py` 新增 TrainingSpec、TrainingState、TrainingInputs、TrainingGradients、TrainingResult。支持 float64、无 bias 的 Linear 链与隐层 ReLU/identity、全输出 mean MSE 和 plain SGD；不支持量化训练、momentum 或分布式状态。W 布局 [in,out]，反向零点导数取 0。

state/version 与内容哈希共同绑定梯度；调用方持有不可变旧状态，更新产生 version+1。构造时冻结嵌套数组并检查有限标量，消费时按 batch/widths 校验形状。输入、梯度与新状态分别存储，loss/预测属于更新前。关键量是尺寸/学习率、浮点容差及状态身份。公式、独立参考与版本反例见[训练指南](../../evaluation/docs/training_step.md)。

## Attention 与逻辑 KV 值边界

`attention.py`定义AttentionSpec/Inputs、KvCacheSpec/State；仅标准库公共数据，不包含参考算法、物理cache或运行时。Q[B,Hq,Sq,D]、K[B,Hkv,Skv,D]、V[B,Hkv,Skv,Dv]各轴正整数、Hq可被Hkv整除；每组连续query head共享KV。scale显式且正，binary64输入必须为有限Python float，列表在边界冻结。

causal时j≤query_start+i且query_start+Sq≤Skv；非causal要求起点为零，所以没有全mask行。Spec推导矩形/可见配对与输入元素数；KV派生逻辑容量/驻留字节。独立校验shape后，身份绑定完整语义与实际内容；KV还含版本和容量。调用者拥有快照，追加算法由workloads提供。关键参数与手算关系见[首包指南](../../workloads/docs/foundation_usage.md)；[Attention](../../tests/workloads/test_attention.py)和[KV测试](../../tests/workloads/test_kv_cache.py)验证数值、冻结、形状及身份反例。

## 真实分类数据边界

`classification.py`提供ClassificationData：不可变二维有限浮点features、合法整数labels、唯一feature/class_names及原始source_sha256；身份还含实际内容。它只保存观测，不拥有分类器或物理资源。特征单位由names/来源说明，split/标准化/支持状态归workloads，结果质量归评价协议。尺寸、类别顺序和来源是关键约束；完整真实任务与[数据/指标测试](../../tests/workloads/test_retrieval.py)见[W5指南](../../workloads/docs/mapping_and_quality.md)。

<!-- model-fields:start -->

### [attention.py](attention.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `AttentionSpec` | `batch_size` | `int` | sample | B [sample], positive; all samples share logical lengths in this version. |
| `AttentionSpec` | `query_heads` | `int` | head | Hq [head], positive multiple of Hkv. |
| `AttentionSpec` | `kv_heads` | `int` | head | Hkv [head]; shared logical K/V heads, not physically replicated to Hq. |
| `AttentionSpec` | `query_length` | `int` | token position | Sq [token position], positive and independent of Skv. |
| `AttentionSpec` | `kv_length` | `int` | token position | Skv [token position], positive visible-plus-masked key extent. |
| `AttentionSpec` | `key_dim` | `int` | element/head | D [element/head]; Q and K contraction dimensions are equal. |
| `AttentionSpec` | `value_dim` | `int` | element/head | Dv [element/head]; may differ from D. |
| `AttentionSpec` | `scale` | `float` | 1 | Positive logit multiplier [1]; conventionally 1/sqrt(D), always explicit. |
| `AttentionSpec` | `causal` | `bool` | 1（布尔） | If true, query i can use key j iff j <= query_start+i. |
| `AttentionSpec` | `query_start` | `int` | token position | Absolute query start within the K sequence [token position]; noncausal requires 0. |
| `AttentionSpec` | `dtype` | `Literal['float64']` | —（结构/对象） | Input/output storage semantics; no low-precision or quantized claim. |
| `AttentionSpec` | `schema_version` | `Literal['attention/v1']` | —（结构/对象） | No projection, bias, dropout, position encoding or backward. |
| `AttentionSpec` | `score_pairs` | `int` | pair | 只读派生属性；Complete rectangular score extent R=B*Hq*Sq*Skv [pair], independent of mask exploitation. |
| `AttentionSpec` | `visible_pairs` | `int` | —（结构/对象） | 只读派生属性；Causal valid pairs sum_i(query_start+i+1); no claim that hardware skips masked pairs. |
| `AttentionSpec` | `input_elements` | `int` | —（结构/对象） | 只读派生属性；Unique logical Q/K/V elements; GQA sharing counts K/V by Hkv. |
| `AttentionSpec` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Bind data, profiles and references to complete semantics, including scale and causal alignment. |
| `AttentionInputs` | `q` | `tuple[float, ...]` | B,Hq,Sq,D | Query values [B,Hq,Sq,D], not raw model activations before projection. |
| `AttentionInputs` | `k` | `tuple[float, ...]` | B,Hkv,Skv,D | Key values [B,Hkv,Skv,D]. |
| `AttentionInputs` | `v` | `tuple[float, ...]` | B,Hkv,Skv,Dv | Value values [B,Hkv,Skv,Dv]. |
| `KvCacheSpec` | `batch_size` | `int` | sample | B [sample], uniform token count across samples. |
| `KvCacheSpec` | `kv_heads` | `int` | head | Hkv [head], not query heads. |
| `KvCacheSpec` | `key_dim` | `int` | element/head | D [element/head] for K. |
| `KvCacheSpec` | `value_dim` | `int` | element/head | Dv [element/head] for V. |
| `KvCacheSpec` | `max_tokens` | `int` | token | Logical token limit per sample [token], positive. |
| `KvCacheSpec` | `schema_version` | `Literal['logical-kv/v1']` | —（结构/对象） | Binary64 contiguous logical snapshots only. |
| `KvCacheSpec` | `capacity_bytes` | `int` | B | 只读派生属性；Maximum logical K/V payload B*Hkv*Tmax*(D+Dv)*8 [B], excluding metadata. |
| `KvCacheState` | `spec` | `KvCacheSpec` | —（结构/对象） | Logical batch/head/dimension/capacity contract. |
| `KvCacheState` | `version` | `int` | update | Append generation [update], independent of token count. |
| `KvCacheState` | `tokens` | `int` | token | Resident contiguous positions per sample [token], 0..max_tokens. |
| `KvCacheState` | `k` | `tuple[float, ...]` | B,Hkv,tokens,D | Current keys [B,Hkv,tokens,D]. |
| `KvCacheState` | `v` | `tuple[float, ...]` | B,Hkv,tokens,Dv | Current values [B,Hkv,tokens,Dv]. |
| `KvCacheState` | `resident_bytes` | `int` | —（结构/对象） | 只读派生属性；Resident logical K/V payload; immutable host copies are not target transfer events. |
| `KvCacheState` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Identity includes dimensions, capacity, contents and logical version; same-version foreign state is distinct. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `nonnegative_int(name: str, value: int)` | Logical versions/positions are nonnegative Python integers, excluding bool. |
| `attention_buffer(name: str, values: tuple[float, ...])` | Freeze an explicit finite binary64 buffer; empty arrays are useful for an empty KV snapshot. |
| `AttentionSpec` | Q[B,Hq,Sq,D], K[B,Hkv,Skv,D], V[B,Hkv,Skv,Dv]; contiguous Hq/Hkv query groups share K/V. |
| `AttentionSpec.score_pairs` | Complete rectangular score extent R=B*Hq*Sq*Skv [pair], independent of mask exploitation. |
| `AttentionSpec.visible_pairs` | Causal valid pairs sum_i(query_start+i+1); no claim that hardware skips masked pairs. |
| `AttentionSpec.input_elements` | Unique logical Q/K/V elements; GQA sharing counts K/V by Hkv. |
| `AttentionSpec.identity_hash` | Bind data, profiles and references to complete semantics, including scale and causal alignment. |
| `AttentionInputs` | Independent immutable logical input buffers; flat order follows the spec's B/head/token/feature axes. |
| `validate_attention(spec: AttentionSpec, inputs: AttentionInputs)` | Shape validation is independent of the reference algorithm, mapping and target resources. |
| `attention_identity(spec: AttentionSpec, inputs: AttentionInputs)` | Same shape with different values, head grouping or causal alignment is a different workload input. |
| `KvCacheSpec` | Logical KV capacity/shape; no pages, physical placement, eviction or request scheduler. |
| `KvCacheSpec.capacity_bytes` | Maximum logical K/V payload B*Hkv*Tmax*(D+Dv)*8 [B], excluding metadata. |
| `KvCacheState` | Immutable state owned by the caller; explicit identity/version permits branches but does not arbitrate concurrent commits. |
| `KvCacheState.resident_bytes` | Resident logical K/V payload; immutable host copies are not target transfer events. |
| `KvCacheState.identity_hash` | Identity includes dimensions, capacity, contents and logical version; same-version foreign state is distinct. |

### [classification.py](classification.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `ClassificationData` | `features` | `tuple[tuple[float, ...], ...]` | sample,feature | [sample,feature] finite measurements; source metadata supplies units. |
| `ClassificationData` | `labels` | `tuple[int, ...]` | class index | Zero-based class labels [class index]. |
| `ClassificationData` | `feature_names` | `tuple[str, ...]` | 1（标识/枚举） | Ordered unique feature/measurement names, including units where applicable. |
| `ClassificationData` | `class_names` | `tuple[str, ...]` | 1（标识/枚举） | Ordered unique class names; tie breaking uses this order. |
| `ClassificationData` | `source_sha256` | `str` | 1（标识/枚举） | Exact original file byte identity; transformations create distinct data identity. |
| `ClassificationData` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Actual observations and declared source/order determine experiment input identity. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `ClassificationData` | Original rows and labels retain their source order; partitioning and preprocessing must be explicit downstream. |
| `ClassificationData.identity_hash` | Actual observations and declared source/order determine experiment input identity. |

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
