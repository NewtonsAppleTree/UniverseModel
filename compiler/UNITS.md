# compiler：张量区域、切块与规约入口

当前是编译器骨架与设计文档，未实现下列分析 Unit 或可执行 schema。先读[模块设计](docs/design.md)、[张量区域契约](../docs/interfaces/tensor_regions.md)和[切块与规约](docs/tiling_and_reduction.md)。

| 分析职责 | 关键输入 / 专业术语 / 单位 | 输出与关系 |
| --- | --- | --- |
| 算子迭代与索引 | shape [element/axis]、M/N/K、parallel/reduction axis、dtype [bit] | GEMM MNK MAC；轴角色由操作定义，训练反向可能改变收缩维 |
| 输出到输入需求 | output ROI、input shape、broadcast/reshape/indexing map | 每输入 exact/cover 区域；ROI extent=end−start，半开区间使用逻辑元素坐标 |
| Tile partition | tile extent/step [element]、alignment [element/B，需明确]、tail policy | 不重不漏的有效分区及必要 mask/padding；地址对齐不等于所有维度整除 |
| Reduction plan | reduction partitions、partial/output dtype、merge/epilogue | K 分块需数值和；context attention 需 m/l/u 状态；区间并集不是数值归并 |
| Memory plan / lowering | storage stride [B]、packing、buffer budget [B]、lifetime | 实际分配、搬运请求和驻留/临时容量；同一输入被需求多次不证明零额外流量 |

最敏感的参数是 tile 的 M/N/K、S_q/S_kv、head/group 范围、累加精度、尾块策略和可驻留容量。逻辑工作量、数组 shape、访问字节、资源请求与完成事件分别维护。

独立使用顺序：已知算子与输出需求 → 验证形状/区域 → 推导输入及规约范围 → 选择合法 tile → 检查容量/映射 → 产生显式局部操作或计划。可只分析一个 GEMM 或 GQA 分区，无须完整图编译。

公共字段未来落在 contracts/workload、contracts/plan；策略落在 compiler 的现有职责目录，硬件参数仍来自 HardwareSpec 和[实际模型字段](../chipmodel/UNITS.md)。原手册的内容统计与逐项修正见[审阅记录](../docs/reference/layout_roi_review.md)。
