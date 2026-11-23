"""Three disjoint scratch buffers and explicit row-wise external payload requests."""

from dataclasses import dataclass
from typing import Literal

from compiler.src.tiling.linear import validate_plan
from contracts.plan.linear import LinearPlan
from contracts.workload.linear import LinearSpec, positive_int


# Contiguous scratch arenas; offsets are local bytes, not external tensor addresses.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinearMemory:
    a_offset: int  # A arena start [B]; zero in this allocator.
    a_bytes: int  # Maximum packed A tile storage [B].
    b_offset: int  # B arena start=a_bytes [B].
    b_bytes: int  # Maximum packed B tile storage [B].
    c_offset: int  # C arena start=a_bytes+b_bytes [B].
    c_bytes: int  # Maximum accumulator/output tile storage [B].
    allocation_bytes: int  # a_bytes+b_bytes+c_bytes [B]; three simultaneously reserved arenas.
    peak_live_bytes: int  # max over updates of A+B+C valid tile payload [B].
    capacity_bytes: int  # Declared single scratch resource capacity [B].


# One externally contiguous tensor-row copy; no cross-row coalescing, no implicit zero-byte requests.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinearTransfer:
    step_index: int  # Index of the consuming/producing plan update [step].
    purpose: Literal["a_read", "b_read", "partial_read", "partial_write", "output_write"]  # Cost ownership.
    payload_bytes: int  # Contiguous row payload [B]; burst rounding belongs to DMA backend.


# Mapping-specific movement differs from the unique logical workload footprint.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinearTraffic:
    executed_macs: int  # Sum of actual tail-aware update work [MAC]; no padding or skipped zeros.
    a_read_bytes: int  # Sum of row payloads loading A [B].
    b_read_bytes: int  # Sum of row payloads loading B [B].
    partial_read_bytes: int  # Reloaded unfinished C payload [B].
    partial_write_bytes: int  # Spilled unfinished C payload [B].
    output_write_bytes: int  # Final completed C payload written once per output [B].
    transfers: tuple[LinearTransfer, ...]  # Serial DMA requests in each step's data-dependency order.

    # Total external payload D=A+B+partial reads+writes+final output [B].
    @property
    def external_bytes(self) -> int:
        return (self.a_read_bytes + self.b_read_bytes + self.partial_read_bytes
                + self.partial_write_bytes + self.output_write_bytes)


# Reserve disjoint A/B/C arenas and reject insufficient capacity before functional execution.
def plan_memory(spec: LinearSpec, plan: LinearPlan, capacity_bytes: int) -> LinearMemory:
    validate_plan(spec, plan)
    positive_int("capacity_bytes", capacity_bytes)
    sizes = [(step.m * step.k * spec.operand_bytes, step.k * step.n * spec.operand_bytes,
              step.m * step.n * spec.result_bytes) for step in plan.steps]
    a, b, c = (max(size[axis] for size in sizes) for axis in range(3))
    allocation = a + b + c
    if allocation > capacity_bytes:
        raise ValueError(f"scratch capacity exceeded: need {allocation} bytes, have {capacity_bytes}")
    return LinearMemory(a_offset=0, a_bytes=a, b_offset=a, b_bytes=b, c_offset=a + b, c_bytes=c,
                        allocation_bytes=allocation, peak_live_bytes=max(map(sum, sizes)), capacity_bytes=capacity_bytes)


# Expand row-major ROI copies; output-stationary retains C, reload-partials loads/stores between K slices.
def count_traffic(spec: LinearSpec, plan: LinearPlan, *, max_transfers: int = 1_000_000) -> LinearTraffic:
    validate_plan(spec, plan)
    positive_int("max_transfers", max_transfers)
    transfers = []
    totals = {name: 0 for name in ("a_read", "b_read", "partial_read", "partial_write", "output_write")}
    macs = 0
    for index, step in enumerate(plan.steps):
        final = step.k0 + step.k == spec.k
        rows = [("a_read", step.m, step.k * spec.operand_bytes),
                ("b_read", step.k, step.n * spec.operand_bytes)]
        if plan.strategy == "reload_partials" and step.k0:
            rows.append(("partial_read", step.m, step.n * spec.result_bytes))
        if final or plan.strategy == "reload_partials":
            rows.append(("output_write" if final else "partial_write", step.m, step.n * spec.result_bytes))
        if len(transfers) + sum(count for _, count, _ in rows) > max_transfers:
            raise ValueError("transfer materialization exceeds max_transfers")
        for purpose, count, payload in rows:
            totals[purpose] += count * payload
            transfers.extend(LinearTransfer(step_index=index, purpose=purpose, payload_bytes=payload) for _ in range(count))
        macs += step.m * step.n * step.k
    return LinearTraffic(executed_macs=macs, a_read_bytes=totals["a_read"], b_read_bytes=totals["b_read"],
                         partial_read_bytes=totals["partial_read"], partial_write_bytes=totals["partial_write"],
                         output_write_bytes=totals["output_write"], transfers=tuple(transfers))
