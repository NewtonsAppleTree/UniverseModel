"""按 block 分配粒度求 SM 驻留上限；occupancy 不是执行利用率。"""

from dataclasses import dataclass

from typing import Literal

from chipmodel.common import ceil_div, count, identifier


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
    max_threads_per_block: int | None = None  # block启动线程上限 [thread/block]；None表示未知。
    max_threads_per_sm: int | None = None  # SM分配的线程槽上限 [thread slot/SM]，本profile按完整warp计。
    max_registers_per_thread: int | None = None  # 每线程寄存器使用上限 [register/thread]。
    max_registers_per_block: int | None = None  # 单block分配后寄存器上限 [register/block]。
    max_shared_bytes_per_block: int | None = None  # 单block分配后shared上限 [B/block]。
    allocation_policy: Literal["padded-warp-block-quantum/v1"] = "padded-warp-block-quantum/v1"  # 先补齐warp，再按block量化；不是厂商通用规则。
    profile_source: str = "unrecorded"  # 资源限制与分配规则的来源/适用域。

    # 检查资源预算；shared memory 可为零，分配粒度必须非零。
    def __post_init__(self) -> None:
        for name in ("warp_size", "max_blocks_per_sm", "max_warps_per_sm", "registers_per_sm", "shared_memory_bytes",
                     "register_allocation_quantum", "shared_allocation_quantum_bytes"):
            count(name, getattr(self, name), 0 if name == "shared_memory_bytes" else 1)
        for name in ("max_threads_per_block", "max_threads_per_sm", "max_registers_per_thread",
                     "max_registers_per_block", "max_shared_bytes_per_block"):
            if getattr(self, name) is not None:
                count(name, getattr(self, name), 0 if "register" in name or "shared" in name else 1)
        if self.allocation_policy != "padded-warp-block-quantum/v1":
            raise ValueError("unsupported GPU allocation policy; provide a matching model")
        identifier("profile_source", self.profile_source)


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
    warps_per_block: int  # ceil(threads/warp_size) [warp/block]。
    padded_threads_per_block: int  # 完整warp槽数 [thread slot/block]。
    tail_thread_slots: int  # padded_threads-threads [thread slot/block]，无效尾lane。
    resident_threads: int  # resident_blocks*threads [thread/SM]，有效线程数。
    thread_slot_efficiency: float  # threads/padded_threads [1]；不表示动态执行利用率。
    block_limits: tuple[tuple[str, int | None], ...]  # 各SM预算可容纳block数；零需求/未知线程限额用None。
    limiting_resources: tuple[str, ...]  # 所有达到驻留容量最小值的SM限制项。
    launch_violations: tuple[str, ...]  # 已知单block限制的违反项，不与SM容量瓶颈混淆。
    launch_feasible: bool | None  # False为已知不可行；True仅在全部本模型限额已知且可容纳；否则None。
    unknown_limits: tuple[str, ...]  # 未提供的启动/线程限额，不假装完整厂商启动验证。
    allocation_policy: str  # 实际使用的分配规则身份。
    profile_source: str  # 限额与规则的来源；occupancy不是性能校准。


# 独立计算 block/warp/register/shared-memory 四项上限；零需求不形成容量瓶颈。
def derive_occupancy(p: GpuSmParams, block: GpuBlock) -> GpuOccupancy:
    if not isinstance(p, GpuSmParams) or not isinstance(block, GpuBlock):
        raise TypeError("derive_occupancy requires GpuSmParams and GpuBlock")
    warps = ceil_div(block.threads, p.warp_size)
    padded = warps * p.warp_size
    registers = (ceil_div(warps * p.warp_size * block.registers_per_thread,
                          p.register_allocation_quantum) * p.register_allocation_quantum)
    shared = (ceil_div(block.shared_memory_bytes, p.shared_allocation_quantum_bytes)
              * p.shared_allocation_quantum_bytes)
    limits = (("blocks", p.max_blocks_per_sm), ("warps", p.max_warps_per_sm // warps),
              ("registers", p.registers_per_sm // registers if registers else None),
              ("shared_memory", p.shared_memory_bytes // shared if shared else None),
              ("thread_slots", p.max_threads_per_sm // padded if p.max_threads_per_sm is not None else None))
    checks = (("max_threads_per_block", block.threads), ("max_registers_per_thread", block.registers_per_thread),
              ("max_registers_per_block", registers), ("max_shared_bytes_per_block", shared))
    violations = tuple(name for name, demand in checks if getattr(p, name) is not None and demand > getattr(p, name))
    unknown = tuple(name for name in (*(name for name, _ in checks), "max_threads_per_sm") if getattr(p, name) is None)
    capacity = min(limit for _, limit in limits if limit is not None)
    resident = 0 if violations else capacity
    active = resident * warps
    feasible = False if not resident else None if unknown else True
    return GpuOccupancy(resident, active, active / p.max_warps_per_sm, registers, shared, warps, padded,
                        padded - block.threads, resident * block.threads, block.threads / padded, limits,
                        tuple(name for name, limit in limits if limit == capacity), violations, feasible, unknown,
                        p.allocation_policy, p.profile_source)
