"""Explicit buffered NIC boundaries with DMA supply/drain paths and registration checks."""

from dataclasses import dataclass
from typing import Literal

from chipmodel.composition.die.topology import ancestry
from chipmodel.composition.graph import validate_model_selection
from contracts.hardware.network import BandwidthConstraint, NetworkEndpointSpec, string_tuple, validate_count, validate_identity
from contracts.versions.json_codec import content_hash
from systemmodel.io.dma.analysis import TransferAnalysis, analyze_transfers, validate_transfers
from systemmodel.io.dma.model import CopyBatch, DmaSystem
from systemmodel.topology.graph import freeze_inventory
from systemmodel.topology.query import SystemPath


# A network endpoint references one NIC and explicit packet staging storage; local DMA and fabric service remain separate.
@dataclass(frozen=True, slots=True, kw_only=True)
class NicPort:
    resource_id: str  # Existing modeled NIC device, owning the buffer subtree.
    endpoint: NetworkEndpointSpec  # Standard-library cluster boundary; capacities are referenced, never cloned per rank.
    buffer_backing_ids: tuple[str, ...]  # Explicit finite transmit/receive buffers under this NIC [resource ID].
    rdma_write_enabled: bool  # Declared remote-write capability; registration/path checks are still mandatory.
    source_ref: str  # Buffered architecture/capability provenance; no implicit coherent access.

    # Freeze buffer membership and require an actual Boolean capability declaration.
    def __post_init__(self) -> None:
        for name in ('resource_id','source_ref'):
            validate_identity(name,getattr(self,name))
        if not isinstance(self.endpoint,NetworkEndpointSpec) or type(self.rdma_write_enabled) is not bool:
            raise TypeError('invalid NIC endpoint/capability')
        object.__setattr__(self,'buffer_backing_ids',tuple(sorted(string_tuple('buffer_backing_ids',self.buffer_backing_ids,unique=True))))


# Exported NIC payload ceilings are disjoint from local DMA/PCIe work and owned by the actual node.
@dataclass(frozen=True, slots=True, kw_only=True)
class NicSystem:
    dma: DmaSystem  # Local posted-write supply/drain service plus finite memory/topology.
    ports: tuple[NicPort, ...]  # Unique endpoint, device and external port inventory.
    constraints: tuple[BandwidthConstraint, ...]  # NIC TX/RX payload ceilings; each actual resource defined exactly once.
    source_ref: str  # Whole assembly version/assumptions.

    # Validate physical buffer ownership and reject parent/child or duplicate local/external service accounting.
    def __post_init__(self) -> None:
        if not isinstance(self.dma,DmaSystem):
            raise TypeError('expected DmaSystem')
        validate_identity('source_ref',self.source_ref)
        object.__setattr__(self,'ports',freeze_inventory('ports',self.ports,NicPort,'resource_id'))
        object.__setattr__(self,'constraints',freeze_inventory('constraints',self.constraints,BandwidthConstraint,'resource_id'))
        topology = self.dma.memory.node.topology
        resources = {r.instance_id:r for r in topology.resources}
        paths = ancestry(topology.resources)
        backings = {b.resource_id for b in self.dma.memory.backings}
        limits = {c.resource_id:c for c in self.constraints}
        used,buffers,endpoints,external_ports = set(),set(),set(),set()
        for port in self.ports:
            endpoint = port.endpoint
            if (port.resource_id not in resources or resources[port.resource_id].model_id is None
                    or endpoint.node_id!=topology.scope_id or endpoint.endpoint_id in endpoints or endpoint.port_id in external_ports):
                raise ValueError('invalid NIC resource/node or duplicate external endpoint/port')
            if endpoint.port_id in {p.port_id for p in topology.ports}:
                raise ValueError('external NIC port cannot alias a node-local PCIe port')
            endpoints.add(endpoint.endpoint_id)
            external_ports.add(endpoint.port_id)
            for key in port.buffer_backing_ids:
                if key not in backings or port.resource_id not in paths[key] or key in buffers:
                    raise ValueError('NIC buffer must uniquely belong to its declared device')
                buffers.add(key)
            for key in (*endpoint.tx_constraint_ids,*endpoint.rx_constraint_ids):
                limit = limits.get(key)
                if (limit is None or key not in resources or resources[key].parent_id!=endpoint.node_id
                        or limit.owner_id!=endpoint.node_id or limit.byte_basis!='payload' or limit.capacity_kind!='declared_ceiling'):
                    raise ValueError('NIC requires existing node-owned payload service ceilings')
                used.add(key)
        if used!=set(limits) or not self.ports:
            raise ValueError('NIC service roster contains missing or unused capacities')
        local = [e.resource_id for e in self.dma.engines]+[s.resource_id for s in self.dma.pcie_services]+[c.resource_id for c in topology.constraints]
        if used.intersection(local):
            raise ValueError('NIC service is already charged by local DMA/PCIe analysis')
        validate_model_selection(topology.resources,(*local,*sorted(used)))

    # Include every local and external declaration in immutable provenance.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)


# Registration authorizes one application's physical allocation subrange at explicit logical phases.
@dataclass(frozen=True, slots=True, kw_only=True)
class NicRegistration:
    registration_id: str  # Unique registration handle; no executable key or implicit remote authentication.
    endpoint_id: str  # NIC endpoint permitted to access this allocation.
    allocation_id: str  # Exact application allocation in the batch placement, not a replaceable address alias.
    offset_bytes: int  # Object-relative first registered byte [B], nonnegative.
    length_bytes: int  # Positive registered extent [B], within useful object data.
    begin_phase: int  # Inclusive registration lifetime phase, not target time.
    end_phase: int  # Exclusive lifetime phase, bounded by allocation lifetime.
    operations: tuple[Literal['read','write'], ...]  # Local source read or destination write grant.
    source_ref: str  # Registration/permission assumption provenance.

    # Validate interval shape; allocation identity and authority are checked against the actual copy evidence.
    def __post_init__(self) -> None:
        for name in ('registration_id','endpoint_id','allocation_id','source_ref'):
            validate_identity(name,getattr(self,name))
        for name in ('offset_bytes','begin_phase','end_phase'):
            validate_count(name,getattr(self,name))
        validate_count('length_bytes',self.length_bytes,minimum=1)
        object.__setattr__(self,'operations',string_tuple('operations',self.operations,unique=True))
        if self.end_phase<=self.begin_phase or not set(self.operations)<={'read','write'}:
            raise ValueError('invalid NIC registration lifetime/permissions')


# One logical flow binds exactly one local whole-buffer DMA chain to one fabric-facing direction.
@dataclass(frozen=True, slots=True, kw_only=True)
class NicFlow:
    flow_id: str  # Unique flow identity; upper composition maps it to a message and application rank.
    endpoint_id: str  # Installed NIC endpoint.
    chain_id: str  # Exactly one supply/drain CopyChain, counted once in the local batch.
    direction: Literal['tx','rx']  # TX finishes in NIC buffer; RX begins there.
    mode: Literal['send','rdma_write']  # Declared message semantic; RDMA requires explicit registration/capability.
    registration_id: str | None = None  # Mandatory for rdma_write, absent for ordinary buffered send.

    # Preserve unsupported capabilities as analysis failures but reject malformed direction/mode declarations.
    def __post_init__(self) -> None:
        for name in ('flow_id','endpoint_id','chain_id'):
            validate_identity(name,getattr(self,name))
        if self.direction not in ('tx','rx') or self.mode not in ('send','rdma_write'):
            raise ValueError('invalid NIC flow direction/mode')
        if self.registration_id is not None:
            validate_identity('registration_id',self.registration_id)


# Simultaneous flows share one placement and DMA batch so shared work and cross-flow hazards cannot be hidden.
@dataclass(frozen=True, slots=True, kw_only=True)
class NicBatch:
    copies: CopyBatch  # Explicit application, staging and NIC buffer allocations; no hidden receive capacity.
    flows: tuple[NicFlow, ...]  # One-to-one chain bindings.
    registrations: tuple[NicRegistration, ...] = ()  # Explicit immutable RDMA grants.

    # Freeze complete rosters without dropping infeasible flows.
    def __post_init__(self) -> None:
        if not isinstance(self.copies,CopyBatch):
            raise TypeError('expected CopyBatch')
        object.__setattr__(self,'flows',freeze_inventory('flows',self.flows,NicFlow,'flow_id'))
        object.__setattr__(self,'registrations',freeze_inventory('registrations',self.registrations,NicRegistration,'registration_id'))
        if len({f.chain_id for f in self.flows})!=len(self.flows) or {f.chain_id for f in self.flows}!={c.chain_id for c in self.copies.chains}:
            raise ValueError('every local chain must have exactly one NIC flow')


# Supply/drain evidence retains exact application data identity while leaving fabric completion and visibility unknown.
@dataclass(frozen=True, slots=True)
class NicFlowAnalysis:
    flow_id: str  # Original immutable flow identity.
    endpoint_id: str  # Selected network boundary.
    direction: str  # TX or RX.
    payload_bytes: int  # Exact useful application bytes [B].
    object_id: str  # Logical content identity from the allocation.
    content_version: str  # MemoryObject source reference; declaration, not a measured content checksum.
    object_offset_bytes: int  # Offset within the logical application object [B].
    application_allocation_id: str  # Registered/read/written application copy.
    buffer_allocation_id: str  # Explicit finite NIC staging copy.


# Local service and exported NIC service are separate ledgers; upper composition must charge each exactly once.
@dataclass(frozen=True, slots=True)
class NicAnalysis:
    system_identity: str  # Full sourced NIC/local assembly hash.
    dma: TransferAnalysis  # Local DMA/PCIe shared work only; excludes exported NIC wire capacities.
    flows: tuple[NicFlowAnalysis, ...]  # Exact validated application/buffer bindings.
    unknown_costs: tuple[str, ...]  # Fabric execution, NIC scheduling/visibility and physical costs remain unmodeled.


# Resolve all shared local work once, then validate buffer ownership, data continuity and explicit RDMA grants.
def analyze_nic(system: NicSystem, batch: NicBatch, *, saved_paths: tuple[SystemPath, ...] | None = None) -> NicAnalysis:
    if not isinstance(system,NicSystem) or not isinstance(batch,NicBatch):
        raise TypeError('expected NicSystem and NicBatch')
    dma = analyze_transfers(system.dma,batch.copies) if saved_paths is None else validate_transfers(system.dma,batch.copies,saved_paths)
    ports = {p.endpoint.endpoint_id:p for p in system.ports}
    allocations = {a.allocation_id:a for a in batch.copies.placement.allocations}
    objects = {o.object_id:o for o in batch.copies.placement.objects}
    grants = {r.registration_id:r for r in batch.registrations}
    for grant in batch.registrations:
        allocation = allocations.get(grant.allocation_id)
        if (grant.endpoint_id not in ports or allocation is None or grant.offset_bytes+grant.length_bytes>objects[allocation.object_id].size_bytes
                or grant.begin_phase<allocation.begin_phase or grant.end_phase>allocation.end_phase):
            raise ValueError('registration escapes actual object/allocation/lifetime')
    rows = []
    for flow in batch.flows:
        port = ports.get(flow.endpoint_id)
        if port is None:
            raise ValueError('unknown NIC endpoint')
        legs = [l for l in dma.legs if l.chain_id==flow.chain_id]
        application,buffer = (legs[0].source,legs[-1].target) if flow.direction=='tx' else (legs[-1].target,legs[0].source)
        offset = application.physical_offset_bytes-allocations[application.allocation_id].offset_bytes
        buffer_offset = buffer.physical_offset_bytes-allocations[buffer.allocation_id].offset_bytes
        if (buffer.backing_id not in port.buffer_backing_ids or application.backing_id in {b for p in system.ports for b in p.buffer_backing_ids}
                or application.object_id!=buffer.object_id or offset!=buffer_offset):
            raise ValueError('flow must preserve exact application data in its NIC buffer')
        if flow.mode=='rdma_write':
            grant = grants.get(flow.registration_id)
            operation = 'read' if flow.direction=='tx' else 'write'
            if (not port.rdma_write_enabled or grant is None or grant.endpoint_id!=flow.endpoint_id
                    or grant.allocation_id!=application.allocation_id or operation not in grant.operations
                    or not grant.begin_phase<=batch.copies.phase<grant.end_phase
                    or offset<grant.offset_bytes or offset+application.length_bytes>grant.offset_bytes+grant.length_bytes):
                raise ValueError('RDMA write requires enabled capability and exact live registration/permissions')
        elif flow.registration_id is not None:
            raise ValueError('ordinary send must not imply RDMA registration semantics')
        rows.append(NicFlowAnalysis(flow.flow_id,flow.endpoint_id,flow.direction,application.length_bytes,application.object_id,
                                   objects[application.object_id].source_ref,offset,application.allocation_id,buffer.allocation_id))
    return NicAnalysis(system.identity_hash,dma,tuple(rows),(*dma.unknown_costs,
        'Buffered NIC static feasibility; no remote authentication, packet scheduling, completion, coherent publication or calibrated energy'))
