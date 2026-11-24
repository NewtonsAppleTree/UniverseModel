"""Node-local directed wiring, explicit forwarding and references to uniquely owned resources."""

from dataclasses import dataclass
from typing import Literal, TypeVar

from chipmodel.composition.graph import ResourceNode, validate_graph as validate_resource_graph, validate_model_selection
from chipmodel.composition.die.topology import ancestry
from contracts.hardware.network import BandwidthConstraint, string_tuple, validate_identity
from contracts.hardware.system import AccessOperation, AddressDomainSpec, SystemPortSpec, access_operations
from contracts.versions.json_codec import content_hash


T = TypeVar('T')  # Preserves immutable model record type when canonicalizing unordered inventories.


# Freeze/sort an inventory and reject duplicate IDs before a dictionary can hide conflicting resources.
def freeze_inventory(name: str, values: tuple[T, ...], expected: type[T], key: str) -> tuple[T, ...]:
    if not isinstance(values,(tuple,list)) or any(not isinstance(value,expected) for value in values):
        raise TypeError(f'{name} requires {expected.__name__} records')
    ordered = tuple(sorted(values,key=lambda value:getattr(value,key)))
    if len({getattr(value,key) for value in ordered})!=len(ordered):
        raise ValueError(f'duplicate {name} identity')
    return ordered


# A wire joins one egress to one ingress; shared service is referenced separately from connectivity.
@dataclass(frozen=True, slots=True, kw_only=True)
class SystemLink:
    link_id: str  # Unique directed connection identity, not an additional bandwidth resource.
    source_port_id: str  # Existing egress port.
    target_port_id: str  # Existing ingress port of a different component.
    operations: tuple[AccessOperation, ...]  # Operations supported by this link and both endpoint ports.
    source_ref: str  # Wiring/permission evidence or manual assumption.
    constraint_ids: tuple[str, ...] = ()  # Unique service references for one crossing; empty means service remains unmodeled.

    # Validate local values; protocol compatibility and endpoint/resource ownership belong to SystemTopology.
    def __post_init__(self) -> None:
        for name in ('link_id','source_port_id','target_port_id','source_ref'):
            validate_identity(name,getattr(self,name))
        object.__setattr__(self,'operations',access_operations(self.operations))
        object.__setattr__(self,'constraint_ids',string_tuple('constraint_ids',self.constraint_ids,unique=True,allow_empty=True))


# Only an explicit ingress-to-egress relation permits transit within a switch/root complex.
@dataclass(frozen=True, slots=True, kw_only=True)
class PortForwarding:
    forwarding_id: str  # Unique crossing identity; no automatic all-to-all forwarding.
    ingress_port_id: str  # Transit ingress; terminal address ports cannot forward.
    egress_port_id: str  # Transit egress owned by the same component.
    operations: tuple[AccessOperation, ...]  # Allowed operations for this exact crossing.
    source_ref: str  # Explicit forwarding/permission assumption or evidence.
    constraint_ids: tuple[str, ...] = ()  # Shared resource references for this internal crossing.

    # Freeze an explicit relation; direction, same-owner and terminal restrictions are checked in composition.
    def __post_init__(self) -> None:
        for name in ('forwarding_id','ingress_port_id','egress_port_id','source_ref'):
            validate_identity(name,getattr(self,name))
        object.__setattr__(self,'operations',access_operations(self.operations))
        object.__setattr__(self,'constraint_ids',string_tuple('constraint_ids',self.constraint_ids,unique=True,allow_empty=True))


# One immutable node/board topology owns a containment tree; links and crossings may form cycles.
@dataclass(frozen=True, slots=True, kw_only=True)
class SystemTopology:
    scope_id: str  # Sole root container in the resource inventory.
    resources: tuple[ResourceNode, ...]  # Reused chipmodel ownership nodes; models are references, never cloned state.
    domains: tuple[AddressDomainSpec, ...]  # Explicit terminal address namespaces; no backing capacity inferred.
    ports: tuple[SystemPortSpec, ...]  # Node-level ports; separate from any chip-internal port graph.
    links: tuple[SystemLink, ...]  # Directed physical attachment relations, at most one link per port direction.
    forwardings: tuple[PortForwarding, ...]  # Explicit switch/root-complex transit permission.
    constraints: tuple[BandwidthConstraint, ...]  # Existing resource IDs with one sourced service declaration each.
    source_ref: str  # Whole-topology origin/version or manual fixture identity.
    coverage: tuple[str, ...]  # Scope, assumptions and omitted mechanisms.
    schema_version: Literal['system-topology/v1'] = 'system-topology/v1'  # Static wiring and permissions, not target execution.

    # Canonicalize sets so declaration order cannot change identity, then validate all cross-object references.
    def __post_init__(self) -> None:
        for name in ('scope_id','source_ref'):
            validate_identity(name,getattr(self,name))
        if self.schema_version!='system-topology/v1':
            raise ValueError('unsupported system topology schema')
        for name,kind,key in (('resources',ResourceNode,'instance_id'),('domains',AddressDomainSpec,'domain_id'),
                              ('ports',SystemPortSpec,'port_id'),('links',SystemLink,'link_id'),
                              ('forwardings',PortForwarding,'forwarding_id'),('constraints',BandwidthConstraint,'resource_id')):
            object.__setattr__(self,name,freeze_inventory(name,getattr(self,name),kind,key))
        object.__setattr__(self,'coverage',string_tuple('coverage',self.coverage))
        validate_topology(self)

    # Hash the complete sourced structure and shared-capacity declarations; no runtime state enters this identity.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)


# Enforce unique scope/ownership, same-protocol wiring, explicit transit and nonduplicated per-stage charges.
def validate_topology(topology: SystemTopology) -> None:
    if not isinstance(topology,SystemTopology):
        raise TypeError('expected SystemTopology')
    validate_resource_graph(topology.resources,())
    paths = ancestry(topology.resources)
    resources = {r.instance_id:r for r in topology.resources}
    if (topology.scope_id not in resources or resources[topology.scope_id].parent_id is not None
            or resources[topology.scope_id].model_id is not None
            or any(topology.scope_id not in path for path in paths.values())):
        raise ValueError('all resources must belong to one noncharging scope root')
    if any(r.ports for r in topology.resources):
        raise ValueError('node inventory references chip models; declare node ports only in SystemTopology.ports')
    domains = {d.domain_id:d for d in topology.domains}
    ports = {p.port_id:p for p in topology.ports}
    constraints = {c.resource_id:c for c in topology.constraints}
    for domain in topology.domains:
        if domain.owner_id not in resources:
            raise ValueError('address domain has unknown owner')
    for constraint in topology.constraints:
        resource = resources.get(constraint.resource_id)
        if resource is None or resource.model_id is None or resource.parent_id!=constraint.owner_id:
            raise ValueError('constraint must reference an existing modeled resource with its actual parent owner')
    validate_model_selection(topology.resources,tuple(constraints))
    for port in topology.ports:
        if port.owner_id not in resources:
            raise ValueError('port has unknown owner')
        if port.domain_id is not None and (port.domain_id not in domains or domains[port.domain_id].owner_id!=port.owner_id):
            raise ValueError('terminal port must use its own address domain')
        _validate_constraints(port.constraint_ids,(port.owner_id,),constraints,paths)
    used_ports,pairs = set(),set()
    for link in topology.links:
        source,target = _ports(ports,link.source_port_id,link.target_port_id,'egress','ingress')
        if source.owner_id==target.owner_id or source.port_id in used_ports or target.port_id in used_ports:
            raise ValueError('link requires distinct owners and uniquely attached directed ports')
        used_ports.update((source.port_id,target.port_id))
        _validate_operations(link.operations,source,target)
        _validate_constraints(link.constraint_ids,(source.owner_id,target.owner_id),constraints,paths)
        if set(source.constraint_ids)&set(target.constraint_ids) or set(link.constraint_ids)&set((*source.constraint_ids,*target.constraint_ids)):
            raise ValueError('same resource charged at both wire and its endpoint')
    for forwarding in topology.forwardings:
        source,target = _ports(ports,forwarding.ingress_port_id,forwarding.egress_port_id,'ingress','egress')
        pair = (source.port_id,target.port_id)
        if source.owner_id!=target.owner_id or source.domain_id is not None or target.domain_id is not None or pair in pairs:
            raise ValueError('forwarding requires a unique same-owner transit-only port pair')
        pairs.add(pair)
        _validate_operations(forwarding.operations,source,target)
        _validate_constraints(forwarding.constraint_ids,(source.owner_id,),constraints,paths)
        if set(source.constraint_ids)&set(target.constraint_ids) or set(forwarding.constraint_ids)&set((*source.constraint_ids,*target.constraint_ids)):
            raise ValueError('same resource charged at both forwarding and its port')


# Resolve directional peers without interpreting protocol strings as implicit adapters or capabilities.
def _ports(ports: dict, first: str, second: str, first_direction: str, second_direction: str) -> tuple:
    if first not in ports or second not in ports:
        raise ValueError('connection references unknown port')
    source,target = ports[first],ports[second]
    if (source.direction,target.direction)!=(first_direction,second_direction) or source.protocol!=target.protocol:
        raise ValueError('port direction/protocol mismatch')
    return source,target


# A crossing can restrict endpoint permissions but cannot invent an operation absent from either port.
def _validate_operations(operations: tuple[str, ...], source: SystemPortSpec, target: SystemPortSpec) -> None:
    if not set(operations)<=set(source.operations)&set(target.operations):
        raise ValueError('connection grants an operation unsupported by its ports')


# Shared resources must be owned within a common ancestor scope; numerical capacity is never copied to references.
def _validate_constraints(references: tuple[str, ...], owners: tuple[str, ...], constraints: dict, paths: dict) -> None:
    for key in references:
        if key not in constraints or any(constraints[key].owner_id not in paths[owner] for owner in owners):
            raise ValueError('unknown shared resource or incompatible owner scope')
