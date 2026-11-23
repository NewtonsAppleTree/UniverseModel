# plan：显式线性分块计划

`TileShape` 是最大块尺寸，`LinearTile` 是实际有效 ROI，`LinearPlan` 是绑定 workload 内容哈希的不可变有序更新序列。坐标及尺寸单位为 element，范围是半开区间；尾块缩小，不补算 padding。仅描述功能顺序，不含异步操作、并行时刻或事件状态。

`output_stationary` 保留同一输出块的 C，`reload_partials` 在 K 切片间回写与重读。构造函数只检查局部字段/版本/类型；跨步归约覆盖、grid 与生命周期由 [compiler tiling](../../compiler/src/tiling/UNITS.md) 独立校验。关键参数为 tile M/N/K、策略和语义身份。使用：创建值 → 绑定 workload 校验 → 内存/流量或功能消费。无独立物理计量；[编译测试](../../compiler/tests/test_linear_mapping.py)验证缺失、重复、越界与提前释放等反例。

<!-- model-fields:start -->

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
