# gpu：SM 资源与 block 驻留

Unit 是 SM 资源预算与一个 kernel block 的需求；`derive_occupancy` 返回静态驻留结果。Warp size、资源数量、分配粒度都显式传入，没有 NVIDIA/AMD 隐式默认值。

先计算 `warps=ceil(threads/warp_size)`，用完整 warp 槽位计算寄存器需求，再按 block 粒度上取整；shared memory 单独对齐。驻留容量取block、warp、register、shared-memory及已知thread-slot限额的最小值。零需求不形成该资源约束。规则身份为padded-warp-block-quantum/v1；来源由profile_source维护。

最敏感的是 registers/thread、shared bytes/block、尾 warp 与分配粒度。Occupancy 是驻留 warp 占比，不是 GPU utilization、吞吐或隐藏延迟能力。本模型按 block 分配寄存器；具体架构按 warp/partition 分配时需要新规则，不能直接套用。

Warp scheduler、scoreboard、SIMT 分歧、tensor/SFU、coalescer 和 bank 冲突仍未实现。它们未来分别需要 issue/latency、操作精度、事务粒度和访问掩码。共享物理存储仍由 memory 计量。

CH6输出每项block_limits、SM限制项、单block启动违反项与尾线程槽。单block线程/寄存器/shared限额失败或SM无法容纳时launch_feasible=False；全部本模型限额已知且可容纳为True；有缺失限额为None，仍返回条件驻留容量和unknown_limits。True不代替设备启动验证。33/64线程可以具有相同occupancy但有效线程比例不同；80组逐block资源消耗枚举及启动反例见[CH6指南](../../docs/compute_capabilities.md)。

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
| `GpuSmParams` | `max_threads_per_block` | `int \| None` | thread/block | block启动线程上限 [thread/block]；None表示未知。 |
| `GpuSmParams` | `max_threads_per_sm` | `int \| None` | thread slot/SM | SM分配的线程槽上限 [thread slot/SM]，本profile按完整warp计。 |
| `GpuSmParams` | `max_registers_per_thread` | `int \| None` | register/thread | 每线程寄存器使用上限 [register/thread]。 |
| `GpuSmParams` | `max_registers_per_block` | `int \| None` | register/block | 单block分配后寄存器上限 [register/block]。 |
| `GpuSmParams` | `max_shared_bytes_per_block` | `int \| None` | B/block | 单block分配后shared上限 [B/block]。 |
| `GpuSmParams` | `allocation_policy` | `Literal['padded-warp-block-quantum/v1']` | —（结构/对象） | 先补齐warp，再按block量化；不是厂商通用规则。 |
| `GpuSmParams` | `profile_source` | `str` | 1（标识/枚举） | 资源限制与分配规则的来源/适用域。 |
| `GpuBlock` | `threads` | `int` | thread | 每 block 有效线程数 [thread]。 |
| `GpuBlock` | `registers_per_thread` | `int` | register/thread | 每线程标量寄存器需求 [register/thread]。 |
| `GpuBlock` | `shared_memory_bytes` | `int` | B | 每 block shared-memory 需求 [B]。 |
| `GpuOccupancy` | `resident_blocks` | `int` | block/SM | 各预算可容纳 block 数的最小值 [block/SM]。 |
| `GpuOccupancy` | `active_warps` | `int` | warp/SM | resident_blocks*ceil(threads/warp_size) [warp/SM]。 |
| `GpuOccupancy` | `occupancy_fraction` | `float` | 1 | active_warps/max_warps_per_sm [1]。 |
| `GpuOccupancy` | `allocated_registers_per_block` | `int` | register/block | padded_threads*r 向上取整到分配粒度 [register/block]。 |
| `GpuOccupancy` | `allocated_shared_bytes_per_block` | `int` | B/block | shared bytes 向上对齐 [B/block]。 |
| `GpuOccupancy` | `warps_per_block` | `int` | warp/block | ceil(threads/warp_size) [warp/block]。 |
| `GpuOccupancy` | `padded_threads_per_block` | `int` | thread slot/block | 完整warp槽数 [thread slot/block]。 |
| `GpuOccupancy` | `tail_thread_slots` | `int` | thread slot/block | padded_threads-threads [thread slot/block]，无效尾lane。 |
| `GpuOccupancy` | `resident_threads` | `int` | thread/SM | resident_blocks*threads [thread/SM]，有效线程数。 |
| `GpuOccupancy` | `thread_slot_efficiency` | `float` | 1 | threads/padded_threads [1]；不表示动态执行利用率。 |
| `GpuOccupancy` | `block_limits` | `tuple[tuple[str, int \| None], ...]` | 1（标识/枚举） | 各SM预算可容纳block数；零需求/未知线程限额用None。 |
| `GpuOccupancy` | `limiting_resources` | `tuple[str, ...]` | 1（标识/枚举） | 所有达到驻留容量最小值的SM限制项。 |
| `GpuOccupancy` | `launch_violations` | `tuple[str, ...]` | 1（标识/枚举） | 已知单block限制的违反项，不与SM容量瓶颈混淆。 |
| `GpuOccupancy` | `launch_feasible` | `bool \| None` | —（结构/对象） | False为已知不可行；True仅在全部本模型限额已知且可容纳；否则None。 |
| `GpuOccupancy` | `unknown_limits` | `tuple[str, ...]` | 1（标识/枚举） | 未提供的启动/线程限额，不假装完整厂商启动验证。 |
| `GpuOccupancy` | `allocation_policy` | `str` | 1（标识/枚举） | 实际使用的分配规则身份。 |
| `GpuOccupancy` | `profile_source` | `str` | 1（标识/枚举） | 限额与规则的来源；occupancy不是性能校准。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `GpuSmParams` | SM 资源预算；register/shared-memory 分配规则在本模型中按 block 向上取整。 |
| `GpuBlock` | 一个 kernel block 的显式资源需求；尾 warp 仍占用完整线程槽。 |
| `GpuOccupancy` | 驻留分析输出；资源不足时 resident_blocks=0，不能伪装成可运行。 |
| `derive_occupancy(p: GpuSmParams, block: GpuBlock)` | 独立计算 block/warp/register/shared-memory 四项上限；零需求不形成容量瓶颈。 |

<!-- model-fields:end -->
