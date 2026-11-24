# graphs：Linear 训练短链与完整语义工作

当前 `training.py` 构造窄范围的 Linear→可选 ReLU→Linear 训练链，支持 1–16 层 Linear；不是通用图 IR。语义值由 [contracts/workload](../../contracts/workload/UNITS.md)维护，输入生成和工作量不依赖 compiler/hardware。给定 TrainingSpec 与 seed，`generate_training` 返回 version=0 的独立权重快照及实际 x/target。

生成算法 `training-sha256-index-v1` 对 `training-input/v1:{seed}:{label}:{index}` 的 ASCII 字节求 SHA256，首字节 `%17-8` 再除 16；label 是 x、target、w0/w1 等独立张量名。seed 为 uint64，max_elements 限制参数和输入总元素数；仅为稳定有界测试数据，不声称代表性或无偏分布。

设 P=Σ din·dout，B=batch，D=B·d_final，H=B·Σhidden_width。完整 GEMM 工作=3BP MAC；mean MSE 的标量动作=4D+2，SGD=2P。ReLU 在前向/反向各 H 次比较与选择，identity 为零。反向材料化转置共 B·Σ各层输入宽+P 个元素，参数唯一容量=8P B。不能将 MAC 乘 2 后宣称包含全部训练工作；其他动作分开统计。

接口：spec → 生成 state/data / `describe_training` → 独立参考或外部执行。最敏感的是 batch/层宽、激活策略、精度、seed 与宿主规模预算；无模型时延/能耗。手算、MSE 归一化、有限差分见[验证](../../tests/workloads/test_training.py)，跨模块范围见[指南](../../evaluation/docs/training_step.md)。

## 逻辑 KV 快照与追加

`kv_cache.py` 的 append_kv 在每个B/Hkv组内沿token轴追加，要求源内容身份匹配、正token数、shape和逻辑容量合法；返回version+1的新快照，不改旧值。状态/容量定义在[公共契约](../../contracts/workload/UNITS.md)。关键量为tokens、max_tokens、B·Hkv·(D+Dv)与max_elements宿主材料化预算；容量为8B·Hkv·max_tokens·(D+Dv) B，不计物理page或传输。

顺序：创建空/完整KvCacheState → append_kv → 显式AttentionSpec/query_start → attention_from_cache → 独立参考。绑定检查resident长度和B/Hkv/D/Dv一致。纯函数允许分支，不提供全局版本仲裁或调度。多batch/head整段prefill与逐token/分块追加等价、容量和身份反例见[测试](../../tests/workloads/test_kv_cache.py)，用途与限制见[指南](../docs/foundation_usage.md)。

## 标准化RBF检索分类图

`retrieval.py`定义不可变RetrievalSplit/State，stratified_split按带seed/label/row的SHA256排序给出穷尽互斥train/validation/test。fit_retrieval只在train上拟合mean与population std，常量维std取1；select_retrieval_scale只用validation准确率且并列取首项。retrieval_attention将Q=[2x,-||x||²,1]、K=[z,1,-||z||²]和one-hot V连接到公共Attention，QK=-||x-z||²，scale为显式RBF逆带宽。key_decimals只舍入支持坐标，保留float64存储，物理转换成本未知。关键量为split、train规模、scale候选和舍入精度；状态身份包含实际来源/参数/支持值。独立顺序、无泄漏/手算证据见[W5指南](../docs/mapping_and_quality.md)及[测试](../../tests/workloads/test_retrieval.py)。

<!-- model-fields:start -->

### [kv_cache.py](kv_cache.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `append_kv(state: KvCacheState, *, k: tuple[float, ...], v: tuple[float, ...], tokens: int, expected_identity: str, max_elements: int=1000000)` | Append token slices within each B/head group; a flat old+new concatenation would corrupt multihead/batch layout. |
| `attention_from_cache(spec: AttentionSpec, state: KvCacheState, q: tuple[float, ...])` | Bind an explicit query to resident KV; caller selects causal query positions, preserving the cache snapshot. |

### [retrieval.py](retrieval.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `RetrievalSplit` | `data_identity` | `str` | 1（标识/枚举） | Full ClassificationData identity. |
| `RetrievalSplit` | `seed` | `int` | —（结构/对象） | uint64 seed for split-sha256/v1 ordering. |
| `RetrievalSplit` | `train` | `tuple[int, ...]` | —（结构/对象） | Support/normalization training row indices. |
| `RetrievalSplit` | `validation` | `tuple[int, ...]` | —（结构/对象） | Hyperparameter-selection row indices. |
| `RetrievalSplit` | `test` | `tuple[int, ...]` | —（结构/对象） | Held-out reporting row indices; never used in fitting/selection. |
| `RetrievalState` | `data_identity` | `str` | 1（标识/枚举） | Exact source observations used to fit this state. |
| `RetrievalState` | `split` | `RetrievalSplit` | —（结构/对象） | Explicit training/validation/test partition and generation seed. |
| `RetrievalState` | `means` | `tuple[float, ...]` | source feature unit | Training-only per-feature mean [source feature unit]. |
| `RetrievalState` | `scales` | `tuple[float, ...]` | source feature unit | Training population standard deviations [source feature unit]; zero variance uses 1. |
| `RetrievalState` | `support` | `tuple[tuple[float, ...], ...]` | 1 | Training vectors after fixed standardization [1]. |
| `RetrievalState` | `labels` | `tuple[int, ...]` | class index | Training support labels [class index]. |
| `RetrievalState` | `classes` | `int` | class | Number of classes, defining one-hot V width [class]. |
| `RetrievalState` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Source, split, normalization and support contents all participate in model identity. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `RetrievalSplit` | A split owns disjoint exhaustive source row indices, without altering the original observations. |
| `RetrievalState` | Standardized support vectors and labels form a fitted nonparametric model; all fitted statistics use training rows only. |
| `RetrievalState.identity_hash` | Source, split, normalization and support contents all participate in model identity. |
| `stratified_split(data: ClassificationData, *, seed: int, train_per_class: int, validation_per_class: int)` | Class-stratified hash ordering is stable across Python versions; remaining examples become the test partition. |
| `fit_retrieval(data: ClassificationData, split: RetrievalSplit)` | Validate complete partition ownership before computing statistics solely from the declared training subset. |
| `retrieval_vectors(state: RetrievalState, queries: tuple[tuple[float, ...], ...], key_decimals: int \| None=None)` | Normalize query measurements with training statistics; optional decimal rounding affects only stored support keys. |
| `retrieval_attention(state: RetrievalState, queries: tuple[tuple[float, ...], ...], *, scale: float, key_decimals: int \| None=None)` | Q=[2x,-\|\|x\|\|²,1], K=[z,1,-\|\|z\|\|²] gives QK=-\|\|x-z\|\|²; V is the support label's one-hot vector. |
| `select_retrieval_scale(state: RetrievalState, data: ClassificationData, scales: tuple[float, ...], *, max_macs: int=1000000, max_score_pairs: int=100000)` | Select the first maximum-accuracy scale using validation rows only; the full ordered score table remains evidence. |

### [training.py](training.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `TrainingWork` | `gemm_macs` | `int` | MAC | 3*B*sum(d_l*d_(l+1)) [MAC]; includes every input and weight gradient. |
| `TrainingWork` | `scalar_arithmetic_operations` | `int` | scalar operation | Mean-MSE 4*B*d_L+2 plus SGD 2*P [scalar operation]. |
| `TrainingWork` | `comparisons` | `int` | comparison | Forward/backward ReLU 2*B*sum(hidden_widths) [comparison]; zero for identity. |
| `TrainingWork` | `selections` | `int` | selection | Forward/backward ReLU 2*B*sum(hidden_widths) [selection]; no floating multiply implied. |
| `TrainingWork` | `transpose_elements` | `int` | element | sum(B*d_l + d_l*d_(l+1)) [element]; explicit backward input/weight transposes. |
| `TrainingWork` | `parameter_bytes` | `int` | B | 8*P [B]; excludes activations, gradients, next state and scratch. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `TrainingWork` | Keep dense contractions, auxiliary arithmetic, comparisons and data rearrangements in distinct counters. |
| `describe_training(spec: TrainingSpec)` | Derive logical actions independently of the compiler schedule; do not approximate training with only 3x forward. |
| `generate_training(spec: TrainingSpec, seed: int, *, max_elements: int=1000000)` | SHA256-index-v1 uses distinct tensor labels, immutable dyadic float data and a materialization bound. |

<!-- model-fields:end -->
