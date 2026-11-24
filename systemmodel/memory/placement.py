"""Exact static reservations and live address intervals; phases are logical, not elapsed time."""

from bisect import bisect_left, insort
from dataclasses import dataclass

from systemmodel.memory.model import MemoryPlan, MemorySystem


MAX_PLAN_ENTRIES = 10000  # Host guard per object/allocation/region roster [entry]; not hardware capacity.


# Per-backing peaks count physical copies once and describe logical demand at the same peak phase.
@dataclass(frozen=True, slots=True)
class BackingUsage:
    backing_id: str  # Unique physical storage identity.
    capacity_bytes: int  # Declared allocatable capacity [B].
    peak_reserved_bytes: int  # Maximum simultaneous rounded occupancy [B].
    peak_phase: int | None  # Earliest phase attaining a positive peak; None for an unused backing.
    logical_bytes_at_peak: int  # Sum of object sizes of live copies at peak_phase [B].
    padding_bytes_at_peak: int  # peak_reserved_bytes - logical_bytes_at_peak [B].
    allocation_ids_at_peak: tuple[str, ...]  # Exact copies contributing to that peak, sorted by identity.


# Independent backing peaks must not be summed and presented as a simultaneous node peak.
@dataclass(frozen=True, slots=True)
class PlacementAnalysis:
    memory_identity: str  # Full hardware/NUMA/source SHA256.
    plan_identity: str  # Full logical demand/placement/view/source SHA256.
    backings: tuple[BackingUsage, ...]  # All physical backings, including unused resources.


# Sweep half-open time/space intervals (id, begin, end, offset, extent, logical); endings precede starts.
def _sweep(intervals: list[tuple], label: str) -> tuple:
    events = {}
    for key,begin,end,offset,extent,logical in intervals:
        item = (offset,offset+extent,key,logical)
        events.setdefault(begin,[[],[]])[1].append(item)
        events.setdefault(end,[[],[]])[0].append(item)
    active,occupied,demand = [],0,0
    peak,peak_phase,peak_logical,peak_ids = 0,None,0,()
    for phase,(ends,starts) in sorted(events.items()):
        for item in ends:
            active.pop(bisect_left(active,item))
            occupied -= item[1]-item[0]
            demand -= item[3]
        for item in sorted(starts):
            pos = bisect_left(active,item)
            if (pos and active[pos-1][1]>item[0]) or (pos<len(active) and item[1]>active[pos][0]):
                raise ValueError(f'{label}: overlapping live intervals at phase {phase}: {item[2]}')
            insort(active,item)
            occupied += item[1]-item[0]
            demand += item[3]
        if occupied>peak:
            peak,peak_phase,peak_logical = occupied,phase,demand
            peak_ids = tuple(sorted(item[2] for item in active))
    return peak,peak_phase,peak_logical,peak_ids


# Validate references, rounded physical extents, lifetime reuse and address views without materializing bytes/phases.
def analyze_placement(memory: MemorySystem, plan: MemoryPlan) -> PlacementAnalysis:
    if not isinstance(memory,MemorySystem) or not isinstance(plan,MemoryPlan):
        raise TypeError('expected MemorySystem and MemoryPlan')
    if plan.memory_identity!=memory.identity_hash:
        raise ValueError('memory plan has stale hardware/NUMA identity')
    if any(len(getattr(plan,name))>MAX_PLAN_ENTRIES for name in ('objects','allocations','regions')):
        raise ValueError('memory plan exceeds host entry guard')
    objects = {o.object_id:o for o in plan.objects}
    backings = {b.resource_id:b for b in memory.backings}
    allocations = {a.allocation_id:a for a in plan.allocations}
    ports = {p.port_id:p for p in memory.node.topology.ports}
    domains = {d.domain_id:d for d in memory.node.topology.domains}
    physical = {key:[] for key in backings}
    mapped,used_objects = {},set()
    for allocation in plan.allocations:
        if allocation.object_id not in objects or allocation.backing_id not in backings:
            raise ValueError('allocation references unknown object/backing')
        obj,backing = objects[allocation.object_id],backings[allocation.backing_id]
        granule = backing.allocation_granule_bytes
        reserved = ((obj.size_bytes+granule-1)//granule)*granule
        if allocation.offset_bytes%granule or allocation.offset_bytes+reserved>backing.capacity_bytes:
            raise ValueError('allocation offset/rounded extent violates backing alignment/capacity')
        physical[backing.resource_id].append((allocation.allocation_id,allocation.begin_phase,allocation.end_phase,
                                            allocation.offset_bytes,reserved,obj.size_bytes))
        used_objects.add(obj.object_id)
    if used_objects!=set(objects):
        raise ValueError('every logical object requires at least one physical allocation')
    for region in plan.regions:
        if region.allocation_id not in allocations:
            raise ValueError('region references unknown allocation')
        allocation = allocations[region.allocation_id]
        obj,backing = objects[allocation.object_id],backings[allocation.backing_id]
        if region.access_port_id not in backing.access_port_ids:
            raise ValueError('region port does not serve its backing')
        port = ports[region.access_port_id]
        if not set(region.permissions)<=set(port.operations):
            raise ValueError('region permissions exceed ingress capability')
        domains[port.domain_id].validate_span(region.base_address,region.length_bytes)
        if region.object_offset_bytes+region.length_bytes>obj.size_bytes:
            raise ValueError('region exceeds logical object; padding cannot be addressed')
        mapped.setdefault(port.domain_id,[]).append((region.region_id,allocation.begin_phase,allocation.end_phase,
                                                    region.base_address,region.length_bytes,region.length_bytes))
    usages = []
    for key,backing in backings.items():
        peak,phase,logical,ids = _sweep(physical[key],f'physical backing {key}')
        usages.append(BackingUsage(key,backing.capacity_bytes,peak,phase,logical,peak-logical,ids))
    for key,intervals in mapped.items():
        _sweep(intervals,f'address domain {key}')
    return PlacementAnalysis(memory.identity_hash,plan.identity_hash,tuple(usages))
