"""按 block 分配粒度求 SM 驻留上限；occupancy 不是执行利用率。"""

from dataclasses import dataclass

from chipmodel.common import ceil_div, count


# SM 资源预算；register/shared-memory 分配规则在本模型中按 block 向上取整。
@dataclass(frozen=True, slots=True, kw_only=True)
class GpuSmParams:
    warp_size: int  # 每 warp 的线程槽数 [thread/warp]。
    max_blocks_per_sm: int  # 硬件 block/CTA 驻留上限 [block/SM]。
    max_warps_per_sm: int  # Warp 驻留上限 [warp/SM]。
    registers_per_sm: int  # 可分配标量寄存器总数 [register/SM]；不是 byte。
    shared_memory_bytes: int  # 每 SM 可用于 block 的 shared memory [B]。
    register_allocation_quantum: int  # 每 block 寄存器分配粒度 [register]。
    shared_allocation_quantum_bytes: int  # 每 block shared-memory 分配粒度 [B]。

    # 检查资源预算；shared memory 可为零，分配粒度必须非零。
    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            count(name, getattr(self, name), 0 if name == "shared_memory_bytes" else 1)


# 一个 kernel block 的显式资源需求；尾 warp 仍占用完整线程槽。
@dataclass(frozen=True, slots=True, kw_only=True)
class GpuBlock:
    threads: int  # 每 block 有效线程数 [thread]。
    registers_per_thread: int  # 每线程标量寄存器需求 [register/thread]。
    shared_memory_bytes: int  # 每 block shared-memory 需求 [B]。

    # 线程非空；允许不使用寄存器或 shared memory 的抽象任务。
    def __post_init__(self) -> None:
        count("threads", self.threads)
        count("registers_per_thread", self.registers_per_thread, 0)
        count("shared_memory_bytes", self.shared_memory_bytes, 0)


# 驻留分析输出；资源不足时 resident_blocks=0，不能伪装成可运行。
@dataclass(frozen=True, slots=True)
class GpuOccupancy:
    resident_blocks: int  # 各预算可容纳 block 数的最小值 [block/SM]。
    active_warps: int  # resident_blocks*ceil(threads/warp_size) [warp/SM]。
    occupancy_fraction: float  # active_warps/max_warps_per_sm [1]。
    allocated_registers_per_block: int  # padded_threads*r 向上取整到分配粒度 [register/block]。
    allocated_shared_bytes_per_block: int  # shared bytes 向上对齐 [B/block]。


# 独立计算 block/warp/register/shared-memory 四项上限；零需求不形成容量瓶颈。
def derive_occupancy(p: GpuSmParams, block: GpuBlock) -> GpuOccupancy:
    warps = ceil_div(block.threads, p.warp_size)
    registers = (ceil_div(warps * p.warp_size * block.registers_per_thread,
                          p.register_allocation_quantum) * p.register_allocation_quantum)
    shared = (ceil_div(block.shared_memory_bytes, p.shared_allocation_quantum_bytes)
              * p.shared_allocation_quantum_bytes)
    limits = [p.max_blocks_per_sm, p.max_warps_per_sm // warps]
    if registers:
        limits.append(p.registers_per_sm // registers)
    if shared:
        limits.append(p.shared_memory_bytes // shared)
    resident = min(limits)
    active = resident * warps
    return GpuOccupancy(resident, active, active / p.max_warps_per_sm, registers, shared)
