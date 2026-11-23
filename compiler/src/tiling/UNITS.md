# tiling：线性分块生产与独立合法性检查

`build_plan` 从形状、最大块尺寸和两种策略生成带真实尾块的 LinearPlan；output_stationary 使用 m/n/k 循环，reload_partials 使用 k/m/n 循环。无 padding、并行 split-K 或搜索器；max_steps 控制宿主材料化规模。

`validate_plan` 独立检查语义哈希、网格对齐、ROI 边界、输出覆盖及每块从 0 到 K 的连续递增归约区间。输出驻留只能在当前 C 完成后切换输出块。接受合法输出组重排，不通过重建生成器序列来证明自己正确。

M/N/K 与块尺寸均为 element；步骤数为 ceil(M/Tm)·ceil(N/Tn)·ceil(K/Tk)，实际 MAC 总量必须为 MNK。块尺寸与策略决定容量/搬运，而非时钟。接口顺序：创建公共值 → 生产或提供计划 → 校验 → 下游。无硬件所有权或状态。尾块、乱序、缺失、重复、越界和提前释放验证见[测试](../../tests/test_linear_mapping.py)。

<!-- model-fields:start -->

### [linear.py](linear.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `build_plan(spec: LinearSpec, tile: TileShape, strategy: str, *, max_steps: int=100000)` | Enumerate bounded rectangular updates with real tails; the two policies differ in C residency. |
| `validate_plan(spec: LinearSpec, plan: LinearPlan)` | Check each ROI, per-output contiguous K coverage and C lifetime without rebuilding the producer's sequence. |

<!-- model-fields:end -->
