"""Sourced DMA engines and explicit whole-copy chains over existing memory/topology declarations."""

from dataclasses import dataclass

from chipmodel.common import ClockDomain
from chipmodel.composition.die.topology import ancestry
from chipmodel.composition.graph import validate_model_selection
from chipmodel.control.data_movement import DmaParams
from contracts.hardware.network import string_tuple, validate_count, validate_identity
from contracts.versions.json_codec import content_hash
from systemmodel.io.pcie.model import PcieProfile, PcieService
from systemmodel.memory.model import MemoryPlan, MemorySystem
from systemmodel.topology.graph import freeze_inventory
from systemmodel.topology.query import PathRequest


# An engine reads only explicitly attached local backings and sends posted writes from a terminal egress.
@dataclass(frozen=True, slots=True, kw_only=True)
class DmaEngine:
    resource_id: str  # One exclusive serial DMA channel service, not an aggregate device summary.
    egress_port_id: str  # Initiating address-terminal port owned by an ancestor of this engine.
    read_backing_ids: tuple[str, ...]  # Explicit local source attachments; no implicit remote pull/read service.
    params: DmaParams  # Existing chipmodel startup, beat width and burst-control service model.
    clock: ClockDomain  # Clock converting this engine's cycles to seconds.
    source_ref: str  # Hardware channel service/attachment assumption; excludes software launch overhead.

    # Freeze attachments and retain professional DMA/clock interfaces without copying their formulas.
    def __post_init__(self) -> None:
        for name in ('resource_id','egress_port_id','source_ref'):
            validate_identity(name,getattr(self,name))
        object.__setattr__(self,'read_backing_ids',tuple(sorted(string_tuple('read_backing_ids',self.read_backing_ids,unique=True))))
        if not isinstance(self.params,DmaParams) or not isinstance(self.clock,ClockDomain):
            raise TypeError('expected DmaParams and ClockDomain')


# Sidecar service model preserves S0/S2 schemas while binding ownership and eliminating overlapping service summaries.
@dataclass(frozen=True, slots=True, kw_only=True)
class DmaSystem:
    memory: MemorySystem  # Authoritative physical capacity, mappings' hardware identity and node topology.
    profile: PcieProfile  # One negotiated conventional posted-write format across this fabric.
    engines: tuple[DmaEngine, ...]  # Unique channel resources; references never multiply service capacity.
    pcie_services: tuple[PcieService, ...]  # Unique raw-line services, each wire attached at most once.
    source_ref: str  # Whole-service assembly provenance; calibration is not implied.

    # Check actual engine/wire owners and disallow simultaneous frame/payload summaries for the same physical service.
    def __post_init__(self) -> None:
        if not isinstance(self.memory,MemorySystem) or not isinstance(self.profile,PcieProfile):
            raise TypeError('expected MemorySystem and PcieProfile')
        validate_identity('source_ref',self.source_ref)
        object.__setattr__(self,'engines',freeze_inventory('engines',self.engines,DmaEngine,'resource_id'))
        object.__setattr__(self,'pcie_services',freeze_inventory('pcie_services',self.pcie_services,PcieService,'resource_id'))
        if not self.engines or not self.pcie_services:
            raise ValueError('DMA system requires engines and PCIe services')
        topology = self.memory.node.topology
        paths = ancestry(topology.resources)
        nodes = {r.instance_id:r for r in topology.resources}
        ports = {p.port_id:p for p in topology.ports}
        links = {l.link_id:l for l in topology.links}
        backings = {b.resource_id for b in self.memory.backings}
        selected = tuple(r.resource_id for r in (*self.engines,*self.pcie_services,*topology.constraints))
        validate_model_selection(topology.resources,selected)
        for engine in self.engines:
            port = ports.get(engine.egress_port_id)
            if (port is None or port.direction!='egress' or port.domain_id is None or port.protocol!=self.profile.protocol
                    or 'write' not in port.operations or port.owner_id not in paths[engine.resource_id]):
                raise ValueError('engine must use a compatible ancestor-owned posted-write egress')
            if not set(engine.read_backing_ids)<=backings or any(port.owner_id not in paths[key] for key in engine.read_backing_ids):
                raise ValueError('engine source backing must be explicitly attached within its local owner')
        wires = set()
        for service in self.pcie_services:
            owner = nodes[service.resource_id].parent_id
            service.frame_capacity_Bps(self.profile)
            for key in service.link_ids:
                link = links.get(key)
                if link is None or key in wires:
                    raise ValueError('unknown or multiply served PCIe wire')
                endpoints = (ports[link.source_port_id],ports[link.target_port_id])
                if any(p.protocol!=self.profile.protocol or owner not in paths[p.owner_id] for p in endpoints):
                    raise ValueError('PCIe service owner/protocol incompatible with its wires')
                wires.add(key)
        for constraint in topology.constraints:
            if constraint.capacity_kind!='declared_ceiling':
                raise ValueError('time lower bounds require declared service ceilings, not fitted averages')
            if constraint.byte_basis=='frame' and constraint.frame_format_id!=self.profile.profile_id:
                raise ValueError('shared frame capacity must bind the exact PCIe format')

    # Hardware identity includes source, memory, channels, clocks, framing, coding and every shared resource.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)


# One complete copy leg names local source and remotely writable destination views; dependencies come from chain order.
@dataclass(frozen=True, slots=True, kw_only=True)
class CopyLeg:
    leg_id: str  # Globally unique leg/action ID within a batch.
    engine_id: str  # Explicit hardware DMA channel.
    source_region_id: str  # Readable local view; may alias a prior chain destination.
    source_address: int  # First useful source byte in its address domain [B].
    target_region_id: str  # Writable destination view served by the posted-write route.
    target_address: int  # First useful target byte in its address domain [B].
    link_ids: tuple[str, ...] | None = None  # Explicit route, or deterministic connectivity search.
    max_hops: int = 256  # Host traversal guard [link], unrelated to target time.

    # Validate local declarations; cross-view continuity, capacity and endpoint permissions are checked during analysis.
    def __post_init__(self) -> None:
        for name in ('leg_id','engine_id','source_region_id','target_region_id'):
            validate_identity(name,getattr(self,name))
        for name in ('source_address','target_address'):
            validate_count(name,getattr(self,name))
        request = PathRequest(source_port_id=self.engine_id,target_port_id=self.target_region_id,operation='write',link_ids=self.link_ids,max_hops=self.max_hops)
        object.__setattr__(self,'link_ids',request.link_ids)


# Chains impose full-copy completion before the next leg; staging holds the whole payload without chunk pipelining.
@dataclass(frozen=True, slots=True, kw_only=True)
class CopyChain:
    chain_id: str  # Independent logical transfer identity in a batch.
    payload_bytes: int  # Positive useful payload D [B], conserved through every leg.
    legs: tuple[CopyLeg, ...]  # Ordered nonempty copies; each next source must equal the previous physical destination.

    # Preserve semantic leg order while rejecting invalid types and repeated action identities.
    def __post_init__(self) -> None:
        validate_identity('chain_id',self.chain_id)
        validate_count('payload_bytes',self.payload_bytes,minimum=1)
        if not isinstance(self.legs,(list,tuple)) or not self.legs or any(not isinstance(l,CopyLeg) for l in self.legs):
            raise TypeError('copy chain requires ordered CopyLeg records')
        object.__setattr__(self,'legs',tuple(self.legs))
        if len({l.leg_id for l in self.legs})!=len(self.legs):
            raise ValueError('duplicate chain leg identity')


# A batch names one valid memory placement and simultaneous phase; independent chains must have no write conflicts.
@dataclass(frozen=True, slots=True, kw_only=True)
class CopyBatch:
    placement: MemoryPlan  # Explicit source/destination/staging reservations; does not allocate hidden host buffers.
    phase: int  # Shared logical liveness phase, not target start time or duration.
    chains: tuple[CopyChain, ...]  # Independent chains, with complete sequential copies inside each chain.
    source_ref: str  # Transfer strategy/input provenance; source contents and visibility are assumptions.

    # Freeze the roster; finite execution materialization is separately guarded by the analyzer.
    def __post_init__(self) -> None:
        if not isinstance(self.placement,MemoryPlan):
            raise TypeError('expected MemoryPlan')
        validate_count('phase',self.phase)
        validate_identity('source_ref',self.source_ref)
        object.__setattr__(self,'chains',freeze_inventory('chains',self.chains,CopyChain,'chain_id'))
        ids = [leg.leg_id for chain in self.chains for leg in chain.legs]
        if not ids or len(set(ids))!=len(ids):
            raise ValueError('batch requires globally unique nonempty leg identities')

    # Input identity includes full placement, phase, complete chain order and all requested paths.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)
