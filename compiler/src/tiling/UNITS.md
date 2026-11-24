# tiling：线性分块生产与独立合法性检查

`build_plan` 从形状、最大块尺寸和两种策略生成带真实尾块的 LinearPlan；output_stationary 使用 m/n/k 循环，reload_partials 使用 k/m/n 循环。无 padding、并行 split-K 或搜索器；max_steps 控制宿主材料化规模。

`validate_plan` 独立检查语义哈希、网格对齐、ROI 边界、输出覆盖及每块从 0 到 K 的连续递增归约区间。输出驻留只能在当前 C 完成后切换输出块。接受合法输出组重排，不通过重建生成器序列来证明自己正确。

M/N/K 与块尺寸均为 element；步骤数为 ceil(M/Tm)·ceil(N/Tn)·ceil(K/Tk)，实际 MAC 总量必须为 MNK。块尺寸与策略决定容量/搬运，而非时钟。接口顺序：创建公共值 → 生产或提供计划 → 校验 → 下游。无硬件所有权或状态。尾块、乱序、缺失、重复、越界和提前释放验证见[测试](../../tests/test_linear_mapping.py)。

## Attention行所有权

`attention.py`以query_tile逐batch/query head生成AttentionBlock，max_blocks限制宿主材料化。validate_attention_plan用独立行游标检查网格、真实尾块、完整有序且无重复的Q/O覆盖，并绑定Spec哈希。所有可见key在同一输出行中归约，不实现context分割。关键量是query_tile与B·Hq·ceil(Sq/tile)；顺序为Spec→build→validate，行为与手算见[W4指南](../../../workloads/docs/mapping_and_quality.md)和[测试](../../tests/test_attention_mapping.py)。

<!-- model-fields:start -->

### [attention.py](attention.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `build_attention_plan(spec: AttentionSpec, *, query_tile: int, score_policy: str='fused', kv_layout: str='shared', max_blocks: int=100000)` | Each query/head owner retains full-key reduction semantics, using real query tails without padded arithmetic. |
| `validate_attention_plan(spec: AttentionSpec, plan: AttentionPlan)` | Check coverage with a linear row cursor, independently of builder enumeration; duplicates and gaps both fail. |

### [linear.py](linear.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `build_plan(spec: LinearSpec, tile: TileShape, strategy: str, *, max_steps: int=100000)` | Enumerate bounded rectangular updates with real tails; the two policies differ in C residency. |
| `validate_plan(spec: LinearSpec, plan: LinearPlan)` | Check each ROI, per-output contiguous K coverage and C lifetime without rebuilding the producer's sequence. |

<!-- model-fields:end -->
