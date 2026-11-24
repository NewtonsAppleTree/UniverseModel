"""Whole-copy dependencies and unique service work; necessary time bounds are not executed completion times."""

from collections import Counter
from dataclasses import dataclass
from fractions import Fraction

from chipmodel.common import finite_fraction
from chipmodel.composition.bounds import ActionEstimate, ResourceBudget, ResourceDemand, TimeBounds, estimate_time_bounds
from chipmodel.control.data_movement import DmaEstimate, estimate_dma
from systemmodel.io.dma.model import CopyBatch, DmaSystem
from systemmodel.io.pcie.model import PcieTraffic, packetize_write
from systemmodel.memory.access import MemoryAccessRequest, ResolvedSpan, resolve_span
from systemmodel.memory.placement import PlacementAnalysis, analyze_placement
from systemmodel.topology.query import PathRequest, SystemPath, find_path, validate_path


MAX_COPY_LEGS = 1024  # Host materialization/conflict-check guard [leg], not target queue depth.


# One copy exposes its resolved bytes, request route and channel/TLP accounting for independent replay.
@dataclass(frozen=True, slots=True)
class CopyLegAnalysis:
    chain_id: str  # Owning logical copy chain.
    leg_id: str  # Unique action identity.
    engine_id: str  # One serial DMA channel resource.
    source: ResolvedSpan  # Readable local source bytes, not a simulated memory read.
    target: ResolvedSpan  # Writable destination bytes, not proof of data visibility.
    path: SystemPath  # Actual posted-write route; no implicit P2P or intermediate endpoint transit.
    dma: DmaEstimate  # Existing channel startup/burst service, excluding memory and link service.
    traffic: PcieTraffic  # Exact useful/padded/protocol bytes for one traversal.
    lower_bound_s: float  # Maximum known necessary resource service within this leg [s], not sum of hop times.


# Read/write byte counts remain explicit even when backing timing is unknown.
@dataclass(frozen=True, slots=True)
class MemoryWork:
    backing_id: str  # Unique physical backing, shared by all address aliases.
    read_bytes: int  # Total requested useful source bytes [B]; no cache/DRAM transaction inference.
    write_bytes: int  # Total requested useful destination bytes [B].


# Work is accumulated once per physical resource, retaining repeated visits from real transfer paths.
@dataclass(frozen=True, slots=True)
class ServiceWork:
    resource_id: str  # Unique channel, line service or declared shared constraint.
    work_unit: str  # cycle, frame_byte or payload_byte; different representations cannot be summed.
    amount: int  # Sum of all actual visits' work in work_unit, exact integer.
    rate_per_s: float  # Declared zero-credit service ceiling [work_unit/s].
    lower_bound_s: float  # amount / rate_per_s [s].


# Static transfer evidence combines byte conservation, staging reservations and necessary service/dependency bounds.
@dataclass(frozen=True, slots=True)
class TransferAnalysis:
    system_identity: str  # Complete memory/PCIe/channel/source SHA256.
    batch_identity: str  # Complete placement/request/chain/source SHA256.
    placement: PlacementAnalysis  # Valid physical/address reservation analysis at all declared phases.
    legs: tuple[CopyLegAnalysis, ...]  # Canonical chain order, preserving execution dependency order inside each chain.
    memory_work: tuple[MemoryWork, ...]  # Unique backing read/write totals; timing unknown.
    staging_allocation_ids: tuple[str, ...]  # Actual intermediate physical reservations, deduplicated across aliases.
    actions: tuple[ActionEstimate, ...]  # Whole-copy dependency DAG and actual resource demands.
    budgets: tuple[ResourceBudget, ...]  # Unique ceilings; initial_credit=0 is an explicit service assumption.
    contributions: tuple[ServiceWork, ...]  # Aggregate service demand and explanatory bounds.
    bounds: TimeBounds  # Maximum of necessary dependency and shared-work bounds.
    unknown_costs: tuple[str, ...]  # Explicit omitted services/costs; unknown never becomes zero energy/time.


# Compare physical useful-byte spans, allowing distinct address aliases to refer to the same storage.
def _same_span(first: ResolvedSpan, second: ResolvedSpan) -> bool:
    return (first.backing_id,first.physical_offset_bytes,first.length_bytes)==(second.backing_id,second.physical_offset_bytes,second.length_bytes)


# Half-open physical intervals conflict only when they share a backing and at least one modeled access writes.
def _overlap(first: ResolvedSpan, second: ResolvedSpan) -> bool:
    return (first.backing_id==second.backing_id and first.physical_offset_bytes<second.physical_offset_bytes+second.length_bytes
            and second.physical_offset_bytes<first.physical_offset_bytes+first.length_bytes)


# Build one immutable set of zero-credit ceilings; PCIe coding is in capacity and TLP overhead is in demand.
def _budgets(system: DmaSystem) -> tuple[ResourceBudget, ...]:
    result = [ResourceBudget(resource_id=e.resource_id,work_unit='cycle',rate_per_s=e.clock.frequency_hz,initial_credit=0) for e in system.engines]
    result.extend(ResourceBudget(resource_id=s.resource_id,work_unit='frame_byte',rate_per_s=s.frame_capacity_Bps(system.profile),initial_credit=0) for s in system.pcie_services)
    result.extend(ResourceBudget(resource_id=c.resource_id,work_unit=c.byte_basis+'_byte',rate_per_s=c.capacity_Bps,initial_credit=0) for c in system.memory.node.topology.constraints)
    return tuple(sorted(result,key=lambda b:b.resource_id))


# Resolve all copies, reject ambiguous hazards, retain every visit and compose bounds; saved routes bypass path search.
def _analyze(system: DmaSystem, batch: CopyBatch, saved_paths: tuple[SystemPath, ...] | None) -> TransferAnalysis:
    if not isinstance(system,DmaSystem) or not isinstance(batch,CopyBatch):
        raise TypeError('expected DmaSystem and CopyBatch')
    count = sum(len(chain.legs) for chain in batch.chains)
    if count>MAX_COPY_LEGS:
        raise ValueError('copy batch exceeds host leg guard')
    if saved_paths is not None and (not isinstance(saved_paths,(list,tuple)) or len(saved_paths)!=count or any(not isinstance(p,SystemPath) for p in saved_paths)):
        raise ValueError('saved route roster must match all copy legs')
    placement = analyze_placement(system.memory,batch.placement)
    topology = system.memory.node.topology
    ports = {p.port_id:p for p in topology.ports}
    engines = {e.resource_id:e for e in system.engines}
    wire_services = {key:s for s in system.pcie_services for key in s.link_ids}
    budget_list = _budgets(system)
    budgets = {b.resource_id:b for b in budget_list}
    legs,actions,staging = [],[],set()
    reads,writes,total = Counter(),Counter(),Counter()
    for chain in batch.chains:
        previous = None
        for leg in chain.legs:
            engine = engines.get(leg.engine_id)
            if engine is None:
                raise ValueError('unknown DMA engine')
            source = resolve_span(system.memory,batch.placement,MemoryAccessRequest(source_port_id=engine.egress_port_id,
                                  region_id=leg.source_region_id,address=leg.source_address,length_bytes=chain.payload_bytes,phase=batch.phase,operation='read'))
            target = resolve_span(system.memory,batch.placement,MemoryAccessRequest(source_port_id=engine.egress_port_id,
                                  region_id=leg.target_region_id,address=leg.target_address,length_bytes=chain.payload_bytes,phase=batch.phase,operation='write'))
            if source.backing_id not in engine.read_backing_ids or source.domain_id!=ports[engine.egress_port_id].domain_id:
                raise ValueError('source is not in the engine local address domain/backing attachments')
            if _overlap(source,target):
                raise ValueError('overlapping source/destination copy is unsupported; no memmove inference')
            if previous is not None:
                if not _same_span(previous.target,source):
                    raise ValueError('staging chain breaks physical byte continuity')
                staging.add(source.allocation_id)
            request = PathRequest(source_port_id=engine.egress_port_id,target_port_id=target.access_port_id,operation='write',link_ids=leg.link_ids,max_hops=leg.max_hops)
            path = find_path(topology,request) if saved_paths is None else validate_path(topology,request,saved_paths[len(legs)].link_ids)
            if saved_paths is not None and path!=saved_paths[len(legs)]:
                raise ValueError('saved path observations disagree with topology/request')
            if any(key not in wire_services for key in path.link_ids):
                raise ValueError('copy path has an unmodeled PCIe wire service')
            traffic = packetize_write(system.profile,target.address,chain.payload_bytes)
            dma = estimate_dma(engine.params,engine.clock,chain.payload_bytes)
            work = Counter({engine.resource_id:dma.completion_cycles})
            for key in path.link_ids:
                work[wire_services[key].resource_id] += traffic.frame_bytes
            for key in path.constraint_visits:
                work[key] += chain.payload_bytes if budgets[key].work_unit=='payload_byte' else traffic.frame_bytes
            latency = max(finite_fraction('leg service bound',Fraction(amount)/Fraction(budgets[key].rate_per_s)) for key,amount in work.items())
            demands = tuple(ResourceDemand(resource_id=key,work_unit=budgets[key].work_unit,amount=amount) for key,amount in sorted(work.items()))
            actions.append(ActionEstimate(action_id=leg.leg_id,latency_s=latency,dependencies=(previous.leg_id,) if previous else (),demands=demands))
            item = CopyLegAnalysis(chain.chain_id,leg.leg_id,engine.resource_id,source,target,path,dma,traffic,latency)
            legs.append(item)
            previous = item
            total.update(work)
            reads[source.backing_id] += chain.payload_bytes
            writes[target.backing_id] += chain.payload_bytes
    for i,first in enumerate(legs):
        for second in legs[i+1:]:
            if first.chain_id!=second.chain_id and (_overlap(first.target,second.source) or _overlap(first.target,second.target) or _overlap(first.source,second.target)):
                raise ValueError('independent copy chains have a physical read/write hazard; add a whole-copy chain')
    memory_work = tuple(MemoryWork(key,reads[key],writes[key]) for key in sorted(set(reads)|set(writes)))
    contributions = tuple(ServiceWork(key,budgets[key].work_unit,amount,budgets[key].rate_per_s,
                                      finite_fraction('shared service bound',Fraction(amount)/Fraction(budgets[key].rate_per_s))) for key,amount in sorted(total.items()))
    unknown = tuple(f'{m.backing_id}: backing read/write service and access energy unmodeled' for m in memory_work)+(
        'PCIe flow-control credits, DLLP/ACK traffic, replay, propagation, final coding-block padding and arbitration unmodeled',
        'No execution/visibility events, host software launch, data contents or calibrated complete physical energy')
    bounds = estimate_time_bounds(tuple(actions),budget_list)
    return TransferAnalysis(system.identity_hash,batch.identity_hash,placement,tuple(legs),memory_work,tuple(sorted(staging)),tuple(actions),budget_list,contributions,bounds,unknown)


# Analyze declared local-source posted writes and whole-buffer staging with deterministic path search when needed.
def analyze_transfers(system: DmaSystem, batch: CopyBatch) -> TransferAnalysis:
    return _analyze(system,batch,None)


# Independently recheck saved paths and deterministic work/bounds without selecting new routes or running hardware.
def validate_transfers(system: DmaSystem, batch: CopyBatch, saved_paths: tuple[SystemPath, ...]) -> TransferAnalysis:
    return _analyze(system,batch,saved_paths)
