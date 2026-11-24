# plan：显式线性分块计划

`TileShape` 是最大块尺寸，`LinearTile` 是实际有效 ROI，`LinearPlan` 是绑定 workload 内容哈希的不可变有序更新序列。坐标及尺寸单位为 element，范围是半开区间；尾块缩小，不补算 padding。仅描述功能顺序，不含异步操作、并行时刻或事件状态。

`output_stationary` 保留同一输出块的 C，`reload_partials` 在 K 切片间回写与重读。构造函数只检查局部字段/版本/类型；跨步归约覆盖、grid 与生命周期由 [compiler tiling](../../compiler/src/tiling/UNITS.md) 独立校验。关键参数为 tile M/N/K、策略和语义身份。使用：创建值 → 绑定 workload 校验 → 内存/流量或功能消费。无独立物理计量；[编译测试](../../compiler/tests/test_linear_mapping.py)验证缺失、重复、越界与提前释放等反例。

## Attention query-block计划

`attention.py`定义AttentionBlock和AttentionPlan，绑定完整任务哈希、query_tile、fused/spill与shared/expanded。每块拥有一个batch/query head的连续完整输出行，rows为真实尾块；不包含context切片或事件时序。只冻结公共值，区域穷尽/顺序由compiler独立校验。关键参数是query_tile、score驻留和KV副本策略，决定容量/搬运，不能改变任务含义。接口/公式与证据见[W4指南](../../workloads/docs/mapping_and_quality.md)和[测试](../../compiler/tests/test_attention_mapping.py)。

<!-- model-fields:start -->

### [attention.py](attention.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `AttentionBlock` | `batch` | `int` | sample index | Batch index [sample index]. |
| `AttentionBlock` | `head` | `int` | head index | Query head index [head index], not KV head. |
| `AttentionBlock` | `query_start` | `int` | token index | Local row start in Q [token index], distinct from the spec's absolute causal origin. |
| `AttentionBlock` | `rows` | `int` | token | Consecutive complete output rows [token], positive. |
| `AttentionPlan` | `workload_hash` | `str` | 1（标识/枚举） | Full AttentionSpec identity, including causal origin and scale. |
| `AttentionPlan` | `query_tile` | `int` | token | Maximum rows per block [token]. |
| `AttentionPlan` | `score_policy` | `Literal['fused', 'spill']` | —（结构/对象） | Local score/probability reuse, or four external intermediate transfers. |
| `AttentionPlan` | `kv_layout` | `Literal['shared', 'expanded']` | —（结构/对象） | Hkv backing, or an explicit Hq-replicated temporary backing. |
| `AttentionPlan` | `blocks` | `tuple[AttentionBlock, ...]` | —（结构/对象） | Complete ordered row owners; no implicit parallel execution. |
| `AttentionPlan` | `schema_version` | `Literal['attention-plan/v1']` | —（结构/对象） | Full-key reductions, no context partition. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `AttentionBlock` | A block owns complete output rows for one batch/query head; each row reduces over its visible keys. |
| `AttentionPlan` | Plans fix head-major query blocking, score residency and explicit KV replication; arithmetic remains binary64. |

### [linear.py](linear.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `TileShape` | `m` | `int` | element | Maximum output rows per tile [element]; >0. |
| `TileShape` | `n` | `int` | element | Maximum output columns per tile [element]; >0. |
| `TileShape` | `k` | `int` | element | Maximum reduction terms per tile [element]; >0. |
| `LinearTile` | `m0` | `int` | element index | Output row start [element index]; >=0. |
| `LinearTile` | `n0` | `int` | element index | Output column start [element index]; >=0. |
| `LinearTile` | `k0` | `int` | element index | Reduction start [element index]; >=0. |
| `LinearTile` | `m` | `int` | element | Actual output rows [element]; >0. |
| `LinearTile` | `n` | `int` | element | Actual output columns [element]; >0. |
| `LinearTile` | `k` | `int` | element | Actual reduction terms [element]; >0. |
| `LinearPlan` | `workload_hash` | `str` | 1（标识/枚举） | Content hash of LinearSpec; rejects plans for a different shape/format. |
| `LinearPlan` | `tile_shape` | `TileShape` | element | Maximum extents defining the output/reduction grid [element]. |
| `LinearPlan` | `strategy` | `Literal['output_stationary', 'reload_partials']` | —（结构/对象） | Explicit C lifetime/traffic policy. |
| `LinearPlan` | `steps` | `tuple[LinearTile, ...]` | —（结构/对象） | Ordered updates; no implicit parallelism or asynchronous events. |
| `LinearPlan` | `schema_version` | `Literal['linear-plan/v1']` | —（结构/对象） | Plan semantics version. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `TileShape` | Maximum tile extents; tails are smaller and do not imply padded arithmetic. |
| `LinearTile` | One rectangular multiply update; output C[m0:m0+m,n0:n0+n] accumulates this K interval. |
| `LinearPlan` | Versioned ordered plan: output-stationary keeps C locally; reload-partials spills between K slices. |

<!-- model-fields:end -->
