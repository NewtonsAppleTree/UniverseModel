# compute：工作语义、并行能力与数值计算

输入是已映射的操作/工作量或真实数值，输出是能力上界、分析结果或功能结果。寄存器、缓存和数据传输引用 memory/interconnect，不在计算公式里免费提供。

| 子模块 | 本轮 Unit | 最关键的量与关系 |
| --- | --- | --- |
| [cpu](cpu/UNITS.md) | CpuCore/CpuWork阶段解释 | 精确最窄阶段与有限批次跨度分开，执行时间未知 |
| [gpu](gpu/UNITS.md) | 驻留/启动/尾warp解释 | 各项SM预算和单block限制分开，缺失限额保留未知 |
| [npu](npu/UNITS.md) | GemmWorkload/MacArray与显式格式服务 | 逻辑/实际MAC、完整签名、L/II、尾槽与有效工作分开 |
| [cim](cim/UNITS.md) | 完整位串行MatVec数值链、电导编码、外围 | 数值量纲、位切片、差分位置和ADC共享决定实际动作与精度 |

Scalar/vector/SFU/reduction 等尚无专用功能模型；研究其已知 L/II 服务时可显式使用根模块的 PipelineParams，但须声明 item 的操作类型及精度。不能仅凭 SFU 名称推断 exp/reciprocal 等成本。

最关心的系统量是实际执行工作、可并行部分、数据供给和精度约束。AI prefill、decode、训练反传使用同一组资源，但操作形状、重用和数据移动不同，应由 workloads/compiler 给出，不能为每种 AI 算法复制一套硬件类。

使用顺序：确定操作语义/数值范围 → 选择具体子模块 → 输入参数与工作 → 独立查询 → 显式接上存储与路径。本目录不增加额外计算时延或状态。

CH6能力解释、单因素对照、独立证据与复现见[指南](../docs/compute_capabilities.md)。未知执行时间不能由峰值、occupancy或孤立服务填补。

<!-- model-fields:start -->



<!-- model-fields:end -->
