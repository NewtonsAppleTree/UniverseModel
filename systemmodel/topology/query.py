"""Deterministic, permission-aware node paths; connectivity does not imply transfer execution or visibility."""

from collections import deque
from dataclasses import dataclass

from contracts.hardware.network import string_tuple, validate_count, validate_identity
from contracts.hardware.system import AccessOperation, access_operations
from systemmodel.topology.graph import SystemTopology


# Requests explicitly choose terminal port directions and one operation; optional links fix a reproducible route.
@dataclass(frozen=True, slots=True, kw_only=True)
class PathRequest:
    source_port_id: str  # Terminal egress in the source address domain.
    target_port_id: str  # Terminal ingress in the target address domain.
    operation: AccessOperation  # Required permission on every visited port/link/crossing.
    link_ids: tuple[str, ...] | None = None  # Explicit nonempty simple path, or None for deterministic minimum-hop search.
    max_hops: int = 256  # Host traversal/path-length guard [link]; never hardware latency.

    # Invalid shape fails before search; unsupported paths remain ordinary research outcomes at the experiment boundary.
    def __post_init__(self) -> None:
        for name in ('source_port_id','target_port_id'):
            validate_identity(name,getattr(self,name))
        access_operations((self.operation,))
        validate_count('max_hops',self.max_hops,minimum=1)
        if self.link_ids is not None:
            links = string_tuple('link_ids',self.link_ids,unique=True)
            if len(links)>self.max_hops:
                raise ValueError('explicit path exceeds max_hops')
            object.__setattr__(self,'link_ids',links)


# Results preserve every service reference visit; repeated use is distinct from duplicated physical capacity.
@dataclass(frozen=True, slots=True)
class SystemPath:
    topology_identity: str  # Identity of the full immutable topology and provenance.
    source_domain_id: str  # Actual source terminal address namespace.
    target_domain_id: str  # Actual target terminal address namespace.
    operation: AccessOperation  # Operation checked on the entire path.
    link_ids: tuple[str, ...]  # Ordered directed connections.
    forwarding_ids: tuple[str, ...]  # Ordered internal crossings, exactly one between consecutive links.
    constraint_visits: tuple[str, ...]  # Ordered references at ports/wires/crossings; no byte count or bandwidth sum implied.

    # Freeze result arrays; global path legality remains tied to the topology checked by validate_path.
    def __post_init__(self) -> None:
        if type(self.topology_identity) is not str or len(self.topology_identity)!=64 or any(c not in '0123456789abcdef' for c in self.topology_identity):
            raise ValueError('path topology identity must be lowercase SHA256')
        for name in ('source_domain_id','target_domain_id'):
            validate_identity(name,getattr(self,name))
        access_operations((self.operation,))
        for name,unique,empty in (('link_ids',True,False),('forwarding_ids',True,True),('constraint_visits',False,True)):
            object.__setattr__(self,name,string_tuple(name,getattr(self,name),unique=unique,allow_empty=empty))
        if len(self.forwarding_ids)!=len(self.link_ids)-1:
            raise ValueError('one explicit crossing is required between consecutive links')

    # Unique limits describe which resources constrain a route; their capacities are not summed along the path.
    @property
    def constraint_ids(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.constraint_visits)))


# Resolve endpoints strictly; same owner/protocol does not establish a free route or bypass an access policy.
def _endpoints(topology: SystemTopology, request: PathRequest) -> tuple:
    if not isinstance(topology,SystemTopology) or not isinstance(request,PathRequest):
        raise TypeError('expected SystemTopology and PathRequest')
    ports = {p.port_id:p for p in topology.ports}
    if request.source_port_id not in ports or request.target_port_id not in ports:
        raise ValueError('unknown requested terminal port')
    source,target = ports[request.source_port_id],ports[request.target_port_id]
    if source.direction!='egress' or target.direction!='ingress' or source.domain_id is None or target.domain_id is None:
        raise ValueError('path requires source egress and target ingress address terminals')
    if request.operation not in source.operations or request.operation not in target.operations:
        raise ValueError('operation denied by terminal capability')
    return ports,source,target


# Validate an explicit simple route and retain each visited resource; no runtime, memory access or service model executes.
def validate_path(topology: SystemTopology, request: PathRequest, link_ids: tuple[str, ...]) -> SystemPath:
    ports,source,target = _endpoints(topology,request)
    link_ids = string_tuple('link_ids',link_ids,unique=True)
    if len(link_ids)>request.max_hops or (request.link_ids is not None and link_ids!=request.link_ids):
        raise ValueError('path disagrees with request or hop budget')
    links = {link.link_id:link for link in topology.links}
    crossings = {(f.ingress_port_id,f.egress_port_id):f for f in topology.forwardings}
    current,visits,used_crossings = source.port_id,list(source.constraint_ids),[]
    for i,key in enumerate(link_ids):
        if key not in links:
            raise ValueError('path references unknown link')
        link = links[key]
        if i:
            crossing = crossings.get((current,link.source_port_id))
            if crossing is None or request.operation not in crossing.operations:
                raise ValueError('path lacks an allowed explicit forwarding relation')
            visits.extend(crossing.constraint_ids)
            visits.extend(ports[link.source_port_id].constraint_ids)
            used_crossings.append(crossing.forwarding_id)
        elif link.source_port_id!=current:
            raise ValueError('path starts at the wrong source')
        if request.operation not in link.operations:
            raise ValueError('operation denied by link capability')
        current = link.target_port_id
        visits.extend(link.constraint_ids)
        visits.extend(ports[current].constraint_ids)
    if current!=target.port_id:
        raise ValueError('path does not reach the requested target')
    return SystemPath(topology.identity_hash,source.domain_id,target.domain_id,request.operation,link_ids,tuple(used_crossings),tuple(visits))


# Breadth-first search minimizes link count; link-ID ordered branches break ties, not latency/capacity optimization.
def find_path(topology: SystemTopology, request: PathRequest) -> SystemPath:
    ports,source,target = _endpoints(topology,request)
    if request.link_ids is not None:
        return validate_path(topology,request,request.link_ids)
    outgoing = {link.source_port_id:link for link in topology.links if request.operation in link.operations}
    next_ports = {}
    for crossing in topology.forwardings:
        if request.operation in crossing.operations and crossing.egress_port_id in outgoing:
            next_ports.setdefault(crossing.ingress_port_id,[]).append(crossing.egress_port_id)
    for choices in next_ports.values():
        choices.sort(key=lambda port:outgoing[port].link_id)
    queue,visited = deque([(source.port_id,())]),{source.port_id}
    while queue:
        egress,path = queue.popleft()
        link = outgoing.get(egress)
        if link is None or len(path)>=request.max_hops:
            continue
        path = (*path,link.link_id)
        if link.target_port_id==target.port_id:
            return validate_path(topology,request,path)
        for port in next_ports.get(link.target_port_id,()):
            if port not in visited:
                visited.add(port)
                queue.append((port,path))
    raise ValueError('no admissible path within max_hops; no implicit staging or endpoint transit')
