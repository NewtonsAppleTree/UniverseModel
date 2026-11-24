# compiler：张量区域、切块与规约入口

Attention已有query-block计划、命名区域、KV复制/score落存和独立float64解释；入口见[src](src/UNITS.md)与[W4指南](../workloads/docs/mapping_and_quality.md)。

当前实现稠密线性算子的显式分块、三缓冲内存规划、逐行流量账本和功能解释执行；入口见 [src](src/UNITS.md) 与[验证](tests/UNITS.md)。下表是更广的分析职责，不能将未覆盖的 attention、一般索引映射等记为已实现。先读[模块设计](docs/design.md)、[张量区域契约](../docs/interfaces/tensor_regions.md)和[切块与规约](docs/tiling_and_reduction.md)。

| 分析职责 | 关键输入 / 专业术语 / 单位 | 输出与关系 |
| --- | --- | --- |
| 算子迭代与索引 | shape [element/axis]、M/N/K、parallel/reduction axis、dtype [bit] | GEMM MNK MAC；轴角色由操作定义，训练反向可能改变收缩维 |
| 输出到输入需求 | output ROI、input shape、broadcast/reshape/indexing map | 每输入 exact/cover 区域；ROI extent=end−start，半开区间使用逻辑元素坐标 |
| Tile partition | tile extent/step [element]、alignment [element/B，需明确]、tail policy | 不重不漏的有效分区及必要 mask/padding；地址对齐不等于所有维度整除 |
| Reduction plan | reduction partitions、partial/output dtype、merge/epilogue | K 分块需数值和；context attention 需 m/l/u 状态；区间并集不是数值归并 |
| Memory plan / lowering | storage stride [B]、packing、buffer budget [B]、lifetime | 实际分配、搬运请求和驻留/临时容量；同一输入被需求多次不证明零额外流量 |

最敏感的参数是 tile 的 M/N/K、S_q/S_kv、head/group 范围、累加精度、尾块策略和可驻留容量。逻辑工作量、数组 shape、访问字节、资源请求与完成事件分别维护。

独立使用顺序：已知算子与输出需求 → 验证形状/区域 → 推导输入及规约范围 → 选择合法 tile → 检查容量/映射 → 产生显式局部操作或计划。可只分析一个 GEMM 或 GQA 分区，无须完整图编译。

当前线性任务/计划值已落在 [contracts/workload](../contracts/workload/UNITS.md)、[contracts/plan](../contracts/plan/UNITS.md)；一般 HardwareSpec 仍为提案。compiler 只接收显式容量，不导入 chipmodel；evaluation 将外部模型服务率与流量账本组合。原手册的内容统计与逐项修正见[审阅记录](../docs/reference/layout_roi_review.md)。

<!-- model-fields:start -->



<!-- model-fields:end -->
