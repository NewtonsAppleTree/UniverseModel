# compute：工作语义、并行能力与数值计算

输入是已映射的操作/工作量或真实数值，输出是能力上界、分析结果或功能结果。寄存器、缓存和数据传输引用 memory/interconnect，不在计算公式里免费提供。

| 子模块 | 本轮 Unit | 最关键的量与关系 |
| --- | --- | --- |
| [cpu](cpu/UNITS.md) | CpuCore 阶段能力 | 峰值 μop/cycle 为各阶段能力最小值，不等同 ISA IPC |
| [gpu](gpu/UNITS.md) | GpuSmParams/GpuBlock occupancy | block/warp/register/shared-memory 四项预算取最小 |
| [npu](npu/UNITS.md) | GemmWorkload/MacArray | MAC=M*N*K；实际执行量可以大于逻辑量 |
| [cim](cim/UNITS.md) | 电导阵列、编码、外围 | 数值量纲、位切片与 ADC 分享决定实际动作量 |

Scalar/vector/SFU/reduction 等尚无专用功能模型；研究其已知 L/II 服务时可显式使用根模块的 PipelineParams，但须声明 item 的操作类型及精度。不能仅凭 SFU 名称推断 exp/reciprocal 等成本。

最关心的系统量是实际执行工作、可并行部分、数据供给和精度约束。AI prefill、decode、训练反传使用同一组资源，但操作形状、重用和数据移动不同，应由 workloads/compiler 给出，不能为每种 AI 算法复制一套硬件类。

使用顺序：确定操作语义/数值范围 → 选择具体子模块 → 输入参数与工作 → 独立查询 → 显式接上存储与路径。本目录不增加额外计算时延或状态。

<!-- model-fields:start -->



<!-- model-fields:end -->
