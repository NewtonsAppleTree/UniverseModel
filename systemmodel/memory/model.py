"""Static physical memory, NUMA membership and explicit object/allocation/address-view declarations."""

from dataclasses import dataclass
from typing import Literal

from chipmodel.composition.die.topology import ancestry
from chipmodel.composition.graph import validate_model_selection
from contracts.hardware.network import string_tuple, validate_count, validate_identity
from contracts.versions.json_codec import content_hash
from systemmodel.composition.node.model import NodeSpec
from systemmodel.topology.graph import freeze_inventory


# A backing resource owns finite allocatable bytes; address aliases never duplicate this capacity.
@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryBacking:
    resource_id: str  # Unique modeled storage instance in the node's resource inventory.
    capacity_bytes: int  # Allocatable physical storage [B], positive, excluding any unmodeled metadata.
    allocation_granule_bytes: int  # Positive reservation granule [B]; capacity and offsets are multiples.
    access_port_ids: tuple[str, ...]  # Explicit address-terminal ingress ports serving this backing.
    source_ref: str  # Capacity/granule/attachment provenance or manual modeling assumption.

    # Enforce exact byte counts and freeze port references; derived reservations round object sizes upward.
    def __post_init__(self) -> None:
        for name in ('resource_id','source_ref'):
            validate_identity(name,getattr(self,name))
        for name in ('capacity_bytes','allocation_granule_bytes'):
            validate_count(name,getattr(self,name),minimum=1)
        if self.capacity_bytes%self.allocation_granule_bytes:
            raise ValueError('backing capacity must contain whole allocation granules')
        object.__setattr__(self,'access_port_ids',tuple(sorted(string_tuple('access_port_ids',self.access_port_ids,unique=True))))


# NUMA groups explicitly place initiators and backings; hierarchy or hop count does not infer locality.
@dataclass(frozen=True, slots=True, kw_only=True)
class NumaDomain:
    numa_id: str  # Node-local locality label; not an implicit latency or distance value.
    member_ids: tuple[str, ...]  # Exact resource instances assigned to this group, without descendant inheritance.
    source_ref: str  # Locality placement evidence or explicit assumption.

    # Freeze exact membership; overlapping or unknown members are rejected by MemorySystem.
    def __post_init__(self) -> None:
        for name in ('numa_id','source_ref'):
            validate_identity(name,getattr(self,name))
        object.__setattr__(self,'member_ids',tuple(sorted(string_tuple('member_ids',self.member_ids,unique=True))))


# Static memory capacity/attachment/NUMA state refers to one immutable node; it contains no allocation or data contents.
@dataclass(frozen=True, slots=True, kw_only=True)
class MemorySystem:
    node: NodeSpec  # Authoritative node topology and device ownership.
    backings: tuple[MemoryBacking, ...]  # Unique finite storage resources, not views or logical memory devices.
    numa_domains: tuple[NumaDomain, ...]  # Optional exact membership; absent members have unknown locality.
    source_ref: str  # Whole-memory-system provenance/version.
    coverage: tuple[str, ...]  # Explicit storage/access scope and omitted mechanisms.
    schema_version: Literal['system-memory/v1'] = 'system-memory/v1'  # Static capacity, mapping and locality only.

    # Bind backing ports to real owners, reject duplicate storage summaries and keep NUMA membership disjoint.
    def __post_init__(self) -> None:
        if not isinstance(self.node,NodeSpec) or self.schema_version!='system-memory/v1':
            raise ValueError('invalid memory system node/schema')
        validate_identity('source_ref',self.source_ref)
        object.__setattr__(self,'coverage',string_tuple('coverage',self.coverage))
        object.__setattr__(self,'backings',freeze_inventory('backings',self.backings,MemoryBacking,'resource_id'))
        object.__setattr__(self,'numa_domains',freeze_inventory('numa_domains',self.numa_domains,NumaDomain,'numa_id'))
        if not self.backings:
            raise ValueError('memory system requires a physical backing')
        topology = self.node.topology
        resources = {r.instance_id:r for r in topology.resources}
        paths = ancestry(topology.resources)
        ports = {p.port_id:p for p in topology.ports}
        validate_model_selection(topology.resources,tuple(b.resource_id for b in self.backings))
        for backing in self.backings:
            for key in backing.access_port_ids:
                port = ports.get(key)
                if port is None or port.direction!='ingress' or port.domain_id is None or port.owner_id not in paths[backing.resource_id]:
                    raise ValueError('backing port must be an address ingress owned by its resource or an ancestor')
        members = set()
        for domain in self.numa_domains:
            for key in domain.member_ids:
                if key not in resources or key in members:
                    raise ValueError('unknown or multiply assigned NUMA member')
                members.add(key)

    # Include all capacity, topology, NUMA placement and provenance in the physical-system identity.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)


# An object is a logical storage demand, without allocating bytes or asserting any tensor contents.
@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryObject:
    object_id: str  # Logical data identity; multiple allocations can hold separate copies.
    size_bytes: int  # Logical extent [B], positive, excluding allocation padding.
    source_ref: str  # Origin of this explicit storage demand.

    # Validate exact demand bytes; no data type, task quality or compression is inferred.
    def __post_init__(self) -> None:
        validate_identity('object_id',self.object_id)
        validate_identity('source_ref',self.source_ref)
        validate_count('size_bytes',self.size_bytes,minimum=1)


# An allocation owns one whole object copy and reserves a rounded physical interval during declared logical phases.
@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryAllocation:
    allocation_id: str  # Unique storage-copy identity; aliases must refer to this same ID.
    object_id: str  # Existing complete logical object to reserve.
    backing_id: str  # Existing physical storage resource.
    offset_bytes: int  # Physical start [B], aligned to the backing granule.
    begin_phase: int  # Inclusive logical liveness boundary [phase], nonnegative; not target time.
    end_phase: int  # Exclusive boundary [phase], strictly after begin_phase.

    # Permit reuse at equal end/start phases while rejecting empty or ambiguous lifetime declarations.
    def __post_init__(self) -> None:
        for name in ('allocation_id','object_id','backing_id'):
            validate_identity(name,getattr(self,name))
        for name in ('offset_bytes','begin_phase','end_phase'):
            validate_count(name,getattr(self,name))
        if self.end_phase<=self.begin_phase:
            raise ValueError('allocation lifetime must be a nonempty half-open phase interval')


# An address view maps a logical subrange of one allocation; it grants only its explicitly declared operations.
@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryRegion:
    region_id: str  # Unique address-view identity, not another allocation.
    allocation_id: str  # Physical allocation this view aliases.
    access_port_id: str  # One ingress from the backing's declared access ports; fixes the address domain.
    base_address: int  # Start in that port's byte-address domain [B].
    object_offset_bytes: int  # First exposed byte within the logical object [B].
    length_bytes: int  # Exposed logical bytes [B], positive; allocation padding is inaccessible.
    permissions: tuple[Literal['read','write'], ...]  # Explicit address-view permissions; also limited by the port/path.

    # Freeze permissions; object/backing/domain references and live overlaps are checked against MemorySystem.
    def __post_init__(self) -> None:
        for name in ('region_id','allocation_id','access_port_id'):
            validate_identity(name,getattr(self,name))
        for name in ('base_address','object_offset_bytes'):
            validate_count(name,getattr(self,name))
        validate_count('length_bytes',self.length_bytes,minimum=1)
        permissions = string_tuple('permissions',self.permissions,unique=True)
        if not set(permissions)<= {'read','write'}:
            raise ValueError('memory region permits read/write operations only')
        object.__setattr__(self,'permissions',tuple(sorted(permissions)))


# A candidate plan owns demands/copies/views; cross-object infeasibility is reported during placement analysis.
@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryPlan:
    memory_identity: str  # Complete MemorySystem SHA256; stale hardware/NUMA bindings are rejected.
    objects: tuple[MemoryObject, ...]  # Logical demand roster; each object needs an allocation; empty workload is legal.
    allocations: tuple[MemoryAllocation, ...]  # Explicit copies and phase intervals, including unmapped reservations.
    regions: tuple[MemoryRegion, ...]  # Address aliases; unexposed reservations remain valid and consume capacity.
    source_ref: str  # Plan provenance or fixed placement-policy declaration.
    schema_version: Literal['system-memory-plan/v1'] = 'system-memory-plan/v1'  # Static placement, no allocator/scheduler inference.

    # Freeze canonical inventories; local parameter failures are distinct from legal declarations with infeasible placement.
    def __post_init__(self) -> None:
        if type(self.memory_identity) is not str or len(self.memory_identity)!=64 or any(c not in '0123456789abcdef' for c in self.memory_identity):
            raise ValueError('memory_identity must be lowercase SHA256')
        validate_identity('source_ref',self.source_ref)
        if self.schema_version!='system-memory-plan/v1':
            raise ValueError('unsupported memory plan schema')
        for name,kind,key in (('objects',MemoryObject,'object_id'),('allocations',MemoryAllocation,'allocation_id'),('regions',MemoryRegion,'region_id')):
            object.__setattr__(self,name,freeze_inventory(name,getattr(self,name),kind,key))

    # Plan identity includes actual object sizes, phases, placements, aliases, permissions and source.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)
