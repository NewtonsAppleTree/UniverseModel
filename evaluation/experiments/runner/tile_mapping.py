"""把 Linear 计划变成显式地址访问；硬件层不导入编译器或推测复用。"""

from dataclasses import dataclass
from typing import Literal

from chipmodel.common import count, identifier, typed_tuple
from chipmodel.composition.tile.digital import DigitalTile, TileWork
from chipmodel.composition.transfer import TransferRequest
from chipmodel.compute.npu.mac import MacArithmetic
from chipmodel.memory.buffer import BufferParams, BufferReservation
from chipmodel.memory.sram.access import SramAccess
from compiler.src.memplan.linear import LinearMemory, LinearTraffic
from compiler.src.tiling.linear import validate_plan
from contracts.plan.linear import LinearPlan
from contracts.workload.linear import LinearSpec


# 可替换的本地硬件适配；现阶段仅支持一个有明确复用语义的标量访问映射。
@dataclass(frozen=True, slots=True, kw_only=True)
class LinearTileBackend:
    tile: DigitalTile  # 独立可调用的 MAC/SRAM/DMA/路径组合。
    external_memory_id: str  # 外部 A/B/C 数据所在资源 ID。
    channel_id: str  # 本研究使用的单个串行 DMA 通道 ID。
    profile_source: str  # 服务参数来源/假设版本；未校准不能标成实测。
    load_path: tuple[str, ...] = ()  # 外部到 scratch 的固定有向路径。
    store_path: tuple[str, ...] = ()  # scratch 到外部的固定有向路径。
    access_policy: Literal["scalar-ab-register-c/v1"] = "scalar-ab-register-c/v1"  # 每 MAC 各读 A/B；每 K slice 在寄存器累加 C。
    max_local_accesses: int = 200_000  # 显式本地请求的宿主展开上限 [request]，非目标硬件预算。

    # 保留 profile 与访问策略身份；配置资源不允许借用不存在的能力。
    def __post_init__(self) -> None:
        if not isinstance(self.tile, DigitalTile):
            raise TypeError("tile must be DigitalTile")
        for name in ("external_memory_id", "channel_id", "profile_source"):
            identifier(name, getattr(self, name))
        count("max_local_accesses", self.max_local_accesses)
        if self.access_policy != "scalar-ab-register-c/v1":
            raise ValueError("unsupported local access policy")
        for name in ("load_path", "store_path"):
            object.__setattr__(self, name, typed_tuple(name, getattr(self, name), str))
        if self.external_memory_id == self.tile.scratch_id:
            raise ValueError("external tensors and scratch need distinct backing")
        if self.external_memory_id not in {m.resource_id for m in self.tile.resources.memories}:
            raise ValueError("external memory is missing")
        if self.channel_id not in {c.resource_id for c in self.tile.resources.channels}:
            raise ValueError("DMA channel is missing")


# Packed A/B/C arenas: no A/B broadcast, scalar C register residency only within each K update.
def map_linear_tile(backend: LinearTileBackend, spec: LinearSpec, plan: LinearPlan,
                    memory: LinearMemory, traffic: LinearTraffic) -> TileWork:
    validate_plan(spec, plan)
    request_count = sum(2 * s.m * s.n * s.k + s.m * s.n * (1 + bool(s.k0)) for s in plan.steps)
    if request_count > backend.max_local_accesses:
        raise ValueError("local access materialization exceeds max_local_accesses")
    operand, result = spec.operand_bytes, spec.result_bytes
    external_b = spec.m * spec.k * operand
    external_c = external_b + spec.k * spec.n * operand
    scratch_id = backend.tile.scratch_id
    reservations = tuple(BufferReservation(reservation_id=name, backing_id=scratch_id, offset_bytes=offset,
                                           buffer=BufferParams(slot_count=1, slot_bytes=size))
                         for name, offset, size in (("A", memory.a_offset, memory.a_bytes),
                                                    ("B", memory.b_offset, memory.b_bytes),
                                                    ("C", memory.c_offset, memory.c_bytes)))
    accesses, transfers, row_signatures = [], [], []
    for index, step in enumerate(plan.steps):
        rows = [("a_read", step.m, step.k * operand, (step.m0 * spec.k + step.k0) * operand,
                 spec.k * operand, memory.a_offset),
                ("b_read", step.k, step.n * operand, external_b + (step.k0 * spec.n + step.n0) * operand,
                 spec.n * operand, memory.b_offset)]
        if step.k0 and plan.strategy == "reload_partials":
            rows.append(("partial_read", step.m, step.n * result,
                         external_c + (step.m0 * spec.n + step.n0) * result, spec.n * result, memory.c_offset))
        if step.k0 + step.k == spec.k or plan.strategy == "reload_partials":
            purpose = "output_write" if step.k0 + step.k == spec.k else "partial_write"
            rows.append((purpose, step.m, step.n * result,
                         external_c + (step.m0 * spec.n + step.n0) * result, spec.n * result, memory.c_offset))
        for purpose, count_rows, payload, external_base, stride, local_base in rows:
            load = purpose.endswith("read")
            for row in range(count_rows):
                ext, local = external_base + row * stride, local_base + row * payload
                transfers.append(TransferRequest(request_id=f"dma/{index}/{purpose}/{row}",
                    source_id=backend.external_memory_id if load else scratch_id,
                    target_id=scratch_id if load else backend.external_memory_id,
                    source_address_bytes=ext if load else local, target_address_bytes=local if load else ext,
                    payload_bytes=payload, channel_id=backend.channel_id,
                    path=backend.load_path if load else backend.store_path))
                row_signatures.append((index, purpose, payload))
        for i in range(step.m):
            for j in range(step.n):
                c_address = memory.c_offset + (i * step.n + j) * result
                if step.k0:
                    accesses.append(SramAccess(request_id=f"local/{index}/{i}/{j}/c_read", address_bytes=c_address,
                                                length_bytes=result, direction="read"))
                for k in range(step.k):
                    for operand_name, address in (("a", memory.a_offset + (i * step.k + k) * operand),
                                                   ("b", memory.b_offset + (k * step.n + j) * operand)):
                        accesses.append(SramAccess(request_id=f"local/{index}/{i}/{j}/{k}/{operand_name}",
                                                    address_bytes=address, length_bytes=operand, direction="read"))
                accesses.append(SramAccess(request_id=f"local/{index}/{i}/{j}/c_write", address_bytes=c_address,
                                            length_bytes=result, direction="write"))
    if row_signatures != [(r.step_index, r.purpose, r.payload_bytes) for r in traffic.transfers]:
        raise ValueError("address mapping and compiler traffic disagree")
    if traffic.executed_macs != sum(s.m * s.n * s.k for s in plan.steps):
        raise ValueError("MAC accounting disagrees with mapped plan")
    arithmetic = (MacArithmetic(operation="integer_mac" if spec.dtype == "int8" else "float_mul_add",
                                operand_format=spec.dtype, accumulator_format=spec.result_dtype, output_format=spec.result_dtype)
                  if backend.tile.mac_arithmetic is not None else None)
    return TileWork(work_id=f"linear/{plan.workload_hash}", executed_macs=traffic.executed_macs,
                    local_accesses=tuple(accesses), transfers=tuple(transfers), reservations=reservations,
                    mac_arithmetic=arithmetic, logical_macs=spec.m * spec.n * spec.k if arithmetic else None)
