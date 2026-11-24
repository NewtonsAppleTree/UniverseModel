"""Declared address resolution, permission-aware reachability and explicit NUMA locality."""

from dataclasses import dataclass
from typing import Literal

from contracts.hardware.network import validate_count, validate_identity
from systemmodel.memory.model import MemoryPlan, MemorySystem
from systemmodel.memory.placement import PlacementAnalysis, analyze_placement
from systemmodel.topology.query import PathRequest, SystemPath, find_path, validate_path


# A read/write query binds a live address view and an explicit initiator; no implicit local bypass exists.
@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryAccessRequest:
    source_port_id: str  # Initiator address-terminal egress.
    region_id: str  # Declared address view to resolve.
    address: int  # First byte in the view's address domain [B].
    length_bytes: int  # Requested positive contiguous extent [B].
    phase: int  # Logical liveness phase, nonnegative; not cycle or second.
    operation: Literal['read','write']  # Permission checked on view and complete request path.
    link_ids: tuple[str, ...] | None = None  # Explicit path, or deterministic search when absent.
    max_hops: int = 256  # Host search/path guard [link], not a timing budget.

    # Exact ranges and route shape are checked now; mapping/lifetime/route feasibility remain query outcomes.
    def __post_init__(self) -> None:
        validate_identity('region_id',self.region_id)
        for name in ('address','phase'):
            validate_count(name,getattr(self,name))
        validate_count('length_bytes',self.length_bytes,minimum=1)
        if self.operation not in ('read','write'):
            raise ValueError('memory access requires read/write')
        route = PathRequest(source_port_id=self.source_port_id,target_port_id=self.region_id,operation=self.operation,
                            link_ids=self.link_ids,max_hops=self.max_hops)
        object.__setattr__(self,'link_ids',route.link_ids)


# Resolution identifies backing bytes; it neither reads data nor simulates page tables, TLBs or IOMMUs.
@dataclass(frozen=True, slots=True)
class ResolvedSpan:
    region_id: str  # Selected address view.
    allocation_id: str  # One physical copy, shared by aliases.
    object_id: str  # Logical object identity.
    backing_id: str  # Physical storage identity.
    access_port_id: str  # Required target ingress.
    domain_id: str  # Address namespace of this mapping.
    address: int  # Requested domain address [B].
    length_bytes: int  # Validated requested extent [B].
    phase: int  # Checked logical lifetime phase.
    operation: Literal['read','write']  # Checked view permission.
    physical_offset_bytes: int  # allocation.offset + view.object_offset + address - view.base [B].


# Static access evidence includes capacity, mapping and path; locality provides no latency/energy value.
@dataclass(frozen=True, slots=True)
class MemoryAccessAnalysis:
    placement: PlacementAnalysis  # Capacity/address feasibility tied to hardware and plan identities.
    span: ResolvedSpan  # Exact resolved physical interval and request semantics.
    path: SystemPath  # Actual directed request path and shared resource references.
    locality: Literal['local','remote','unknown']  # Equal/different explicit NUMA labels, or missing membership.
    initiator_numa_id: str | None  # Exact source owner membership; no inheritance.
    backing_numa_id: str | None  # Exact physical backing membership; no inheritance.


# Resolve a span after whole-plan validation; partial object views cannot expose reservation padding.
def _resolve(memory: MemorySystem, plan: MemoryPlan, request: MemoryAccessRequest) -> ResolvedSpan:
    if not isinstance(request,MemoryAccessRequest):
        raise TypeError('expected MemoryAccessRequest')
    region = next((r for r in plan.regions if r.region_id==request.region_id),None)
    if region is None:
        raise ValueError('unknown memory region')
    allocation = next(a for a in plan.allocations if a.allocation_id==region.allocation_id)
    if not allocation.begin_phase<=request.phase<allocation.end_phase:
        raise ValueError('access outside allocation lifetime')
    if request.operation not in region.permissions:
        raise ValueError('access denied by region permission')
    if request.address<region.base_address or request.address+request.length_bytes>region.base_address+region.length_bytes:
        raise ValueError('access span outside memory region')
    port = next(p for p in memory.node.topology.ports if p.port_id==region.access_port_id)
    offset = allocation.offset_bytes+region.object_offset_bytes+request.address-region.base_address
    return ResolvedSpan(region.region_id,allocation.allocation_id,allocation.object_id,allocation.backing_id,
                        port.port_id,port.domain_id,request.address,request.length_bytes,request.phase,request.operation,offset)


# Independently validate a placement and map one address span; source reachability is deliberately checked separately.
def resolve_span(memory: MemorySystem, plan: MemoryPlan, request: MemoryAccessRequest) -> ResolvedSpan:
    analyze_placement(memory,plan)
    return _resolve(memory,plan,request)


# Translate a resolved target into the existing path contract without granting protocol-implied permissions.
def _route_request(request: MemoryAccessRequest, span: ResolvedSpan) -> PathRequest:
    return PathRequest(source_port_id=request.source_port_id,target_port_id=span.access_port_id,operation=request.operation,
                       link_ids=request.link_ids,max_hops=request.max_hops)


# Locality comes from explicit source-owner/backing placement, never hop count or controller ancestry.
def _observe(memory: MemorySystem, request: MemoryAccessRequest, placement: PlacementAnalysis,
             span: ResolvedSpan, path: SystemPath) -> MemoryAccessAnalysis:
    memberships = {member:d.numa_id for d in memory.numa_domains for member in d.member_ids}
    source = next(p for p in memory.node.topology.ports if p.port_id==request.source_port_id)
    initiator,backing = memberships.get(source.owner_id),memberships.get(span.backing_id)
    locality = 'unknown' if initiator is None or backing is None else ('local' if initiator==backing else 'remote')
    return MemoryAccessAnalysis(placement,span,path,locality,initiator,backing)


# Analyze placement, resolve bytes and search/check the request path; read response/data service remains unmodeled.
def analyze_access(memory: MemorySystem, plan: MemoryPlan, request: MemoryAccessRequest) -> MemoryAccessAnalysis:
    placement = analyze_placement(memory,plan)
    span = _resolve(memory,plan,request)
    path = find_path(memory.node.topology,_route_request(request,span))
    return _observe(memory,request,placement,span,path)


# Reanalyze saved static declarations and validate their recorded route, without path search or target execution.
def validate_access(memory: MemorySystem, plan: MemoryPlan, request: MemoryAccessRequest,
                    saved_link_ids: tuple[str, ...]) -> MemoryAccessAnalysis:
    placement = analyze_placement(memory,plan)
    span = _resolve(memory,plan,request)
    path = validate_path(memory.node.topology,_route_request(request,span),saved_link_ids)
    return _observe(memory,request,placement,span,path)
