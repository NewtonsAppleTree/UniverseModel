"""Cache功能轨迹→DRAM读流量的局部组合；资源下界不等于完整访问执行时间。"""

from dataclasses import dataclass
from fractions import Fraction

from chipmodel.common import finite_fraction, typed_tuple
from chipmodel.memory.access import MemoryAccess
from chipmodel.memory.cache import CacheParams, CacheState, CacheTrace, trace_cache
from chipmodel.memory.controllers.dram_read import DramReadProfile, DramSpanEstimate, estimate_dram_span


# 只引用cache及一个DRAM backing；DRAM读填充计一次，dirty写回保留未知。
@dataclass(frozen=True, slots=True)
class CachedDramAnalysis:
    cache: CacheTrace  # 精确元数据命中/替换与有序外存事务。
    read_services: tuple[DramSpanEstimate, ...]  # 每次cache fill的DRAM条件估算。
    channel_read_bytes: tuple[tuple[int, int], ...]  # 每channel累计burst有效接口字节 [B]，rank共享。
    read_lower_bound_s: float  # max(所有fill条件界,每channel字节/带宽) [s]。
    execution_time_s: None  # lookup、写回、队列与调度未知，整体执行时间不推定。
    unknown_costs: tuple[str, ...]  # 已触及的cache/DRAM缺项；空轨迹可为空。


# 验证完整cache行均落入backing；初态显式恢复，row_state仅用于每个fill的条件分析。
def analyze_cached_dram(params: CacheParams, dram: DramReadProfile, accesses: tuple[MemoryAccess, ...], *,
                        row_state: str, initial_state: CacheState | None = None, flush: bool = False,
                        max_line_touches: int = 100_000) -> CachedDramAnalysis:
    if not isinstance(params, CacheParams) or not isinstance(dram, DramReadProfile):
        raise TypeError("CacheParams and DramReadProfile required")
    if row_state not in ("hit", "closed", "conflict"):
        raise ValueError("explicit DRAM row_state required")
    accesses = typed_tuple("accesses", accesses, MemoryAccess)
    capacity, line = dram.organization.capacity_bytes, params.geometry.line_bytes
    if capacity % line:
        raise ValueError("DRAM backing must contain complete cache lines")
    if any(a.address_bytes + a.length_bytes > capacity for a in accesses):
        raise ValueError("cached access outside DRAM capacity")
    if initial_state is not None:
        if not isinstance(initial_state, CacheState) or any(a + line > capacity for a in initial_state.lru_lines):
            raise ValueError("cache initial state outside DRAM backing")
    cache = trace_cache(params, accesses, initial_state=initial_state, flush=flush, max_line_touches=max_line_touches)
    reads, totals, unknown = [], {}, set()
    if cache.touches or cache.backing_accesses:
        unknown.add("Cache metadata only: lookup/data-array timing, MSHR, coherence and execution schedule unknown")
    for access in cache.backing_accesses:
        if access.direction == "write":
            unknown.add("DRAM dirty writeback service is unknown; read profile cannot price writes")
            continue
        service = estimate_dram_span(dram, access, row_state=row_state)
        reads.append(service)
        unknown.add(service.unknown_reason)
        for channel, amount in service.channel_transferred_bytes:
            totals[channel] = totals.get(channel, 0) + amount
    bus_bound = finite_fraction("cached DRAM read interface bound", Fraction(max(totals.values(), default=0))
                                / Fraction(dram.channel_bandwidth_bytes_per_s))
    return CachedDramAnalysis(cache, tuple(reads), tuple(sorted(totals.items())),
                              max(bus_bound, max((r.lower_bound_s for r in reads), default=0)), None, tuple(sorted(unknown)))
