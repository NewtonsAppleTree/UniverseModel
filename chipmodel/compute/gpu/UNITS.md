# gpu：SM 资源与 block 驻留

Unit 是 SM 资源预算与一个 kernel block 的需求；`derive_occupancy` 返回静态驻留结果。Warp size、资源数量、分配粒度都显式传入，没有 NVIDIA/AMD 隐式默认值。

先计算 `warps=ceil(threads/warp_size)`，用完整 warp 槽位计算寄存器需求，再按 block 粒度上取整；shared memory 单独对齐。驻留 block 数为硬件 block 上限、warp 上限和两个容量上限的最小值。零需求的资源不构成约束；结果为零表示当前 block 无法驻留。

最敏感的是 registers/thread、shared bytes/block、尾 warp 与分配粒度。Occupancy 是驻留 warp 占比，不是 GPU utilization、吞吐或隐藏延迟能力。本模型按 block 分配寄存器；具体架构按 warp/partition 分配时需要新规则，不能直接套用。

Warp scheduler、scoreboard、SIMT 分歧、tensor/SFU、coalescer 和 bank 冲突仍未实现。它们未来分别需要 issue/latency、操作精度、事务粒度和访问掩码。共享物理存储仍由 memory 计量。

<!-- model-fields:start -->

### [occupancy.py](occupancy.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `GpuSmParams` | `warp_size` | `int` | thread/warp | 每 warp 的线程槽数 [thread/warp]。 |
| `GpuSmParams` | `max_blocks_per_sm` | `int` | block/SM | 硬件 block/CTA 驻留上限 [block/SM]。 |
| `GpuSmParams` | `max_warps_per_sm` | `int` | warp/SM | Warp 驻留上限 [warp/SM]。 |
| `GpuSmParams` | `registers_per_sm` | `int` | register/SM | 可分配标量寄存器总数 [register/SM]；不是 byte。 |
| `GpuSmParams` | `shared_memory_bytes` | `int` | B | 每 SM 可用于 block 的 shared memory [B]。 |
| `GpuSmParams` | `register_allocation_quantum` | `int` | register | 每 block 寄存器分配粒度 [register]。 |
| `GpuSmParams` | `shared_allocation_quantum_bytes` | `int` | B | 每 block shared-memory 分配粒度 [B]。 |
| `GpuBlock` | `threads` | `int` | thread | 每 block 有效线程数 [thread]。 |
| `GpuBlock` | `registers_per_thread` | `int` | register/thread | 每线程标量寄存器需求 [register/thread]。 |
| `GpuBlock` | `shared_memory_bytes` | `int` | B | 每 block shared-memory 需求 [B]。 |
| `GpuOccupancy` | `resident_blocks` | `int` | block/SM | 各预算可容纳 block 数的最小值 [block/SM]。 |
| `GpuOccupancy` | `active_warps` | `int` | warp/SM | resident_blocks*ceil(threads/warp_size) [warp/SM]。 |
| `GpuOccupancy` | `occupancy_fraction` | `float` | 1 | active_warps/max_warps_per_sm [1]。 |
| `GpuOccupancy` | `allocated_registers_per_block` | `int` | register/block | padded_threads*r 向上取整到分配粒度 [register/block]。 |
| `GpuOccupancy` | `allocated_shared_bytes_per_block` | `int` | B/block | shared bytes 向上对齐 [B/block]。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `GpuSmParams` | SM 资源预算；register/shared-memory 分配规则在本模型中按 block 向上取整。 |
| `GpuBlock` | 一个 kernel block 的显式资源需求；尾 warp 仍占用完整线程槽。 |
| `GpuOccupancy` | 驻留分析输出；资源不足时 resident_blocks=0，不能伪装成可运行。 |
| `derive_occupancy(p: GpuSmParams, block: GpuBlock)` | 独立计算 block/warp/register/shared-memory 四项上限；零需求不形成容量瓶颈。 |

<!-- model-fields:end -->
