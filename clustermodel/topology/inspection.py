"""Installed network inventory and explicitly scoped directed reachability observations."""

from dataclasses import dataclass

from contracts.hardware.network import string_tuple
from clustermodel.topology.graph import NetworkGraph, _NetworkIndex


# Reachability concerns remote NIC boundaries only; same-node service is a separate systemmodel responsibility.
@dataclass(frozen=True, slots=True, kw_only=True)
class EndpointReachability:
    source_endpoint_id: str  # Queried source boundary.
    reachable_remote_ids: tuple[str, ...]  # Other-node endpoints reachable by declared switch crossings.
    unreachable_remote_ids: tuple[str, ...]  # Other-node endpoints lacking an outgoing valid forwarding path.
    same_node_ids: tuple[str, ...]  # Other endpoints on this source node; excluded from remote connectivity claims.


# Counts describe the supplied graph view, never a sum of attainable bandwidth or capacity duplicated by rank.
@dataclass(frozen=True, slots=True, kw_only=True)
class NetworkOverview:
    node_count: int  # Installed endpoint-owning nodes [node], including isolated owners after static outages.
    endpoint_count: int  # Installed NIC boundary ports [endpoint].
    switch_count: int  # Installed declared switches [switch], including isolated switches.
    constraint_count: int  # Unique shared capacity declarations [resource]; independent of reference count.
    directed_link_count: int  # Currently present physical directions [link].
    physical_connection_count: int  # Distinct unordered physical port pairs with at least one present direction [connection].
    bidirectional_connection_count: int  # Port pairs with both directions present [connection]; shared duplex limits still apply.
    one_way_connection_count: int  # Port pairs having only one direction present [connection].
    unattached_endpoint_ids: tuple[str, ...]  # Endpoints with neither an input nor output physical link.
    reachability: tuple[EndpointReachability, ...]  # Only explicitly requested source queries; empty means not queried.


# Inspect inventory in linear graph space; perform forwarding traversal only for caller-selected source endpoints.
def inspect_network(graph: NetworkGraph, *, source_endpoint_ids: tuple[str, ...] = ()) -> NetworkOverview:
    if not isinstance(graph, NetworkGraph):
        raise TypeError("graph: expected NetworkGraph")
    sources = tuple(sorted(string_tuple("source_endpoint_ids", source_endpoint_ids, unique=True, allow_empty=True)))
    endpoints = {endpoint.endpoint_id: endpoint for endpoint in graph.endpoints}
    if not set(sources).issubset(endpoints):
        raise ValueError("source_endpoint_ids: unknown endpoint")
    pairs, attached = {}, set()
    for link in graph.links:
        pair = tuple(sorted((link.src_port_id, link.dst_port_id)))
        pairs[pair] = pairs.get(pair, 0) + 1
        attached.update(pair)
    queries = []
    index = _NetworkIndex(graph) if sources else None
    for identity in sources:
        owner = endpoints[identity].node_id
        reachable = set(index.reachable_endpoints(identity))
        remote = {endpoint.endpoint_id for endpoint in graph.endpoints if endpoint.node_id != owner}
        local = tuple(endpoint.endpoint_id for endpoint in graph.endpoints if endpoint.node_id == owner and endpoint.endpoint_id != identity)
        queries.append(EndpointReachability(source_endpoint_id=identity,
                                            reachable_remote_ids=tuple(sorted(remote & reachable)),
                                            unreachable_remote_ids=tuple(sorted(remote - reachable)), same_node_ids=local))
    return NetworkOverview(node_count=len(graph.node_ids), endpoint_count=len(endpoints), switch_count=len(graph.switches),
                           constraint_count=len(graph.constraints), directed_link_count=len(graph.links),
                           physical_connection_count=len(pairs), bidirectional_connection_count=sum(count == 2 for count in pairs.values()),
                           one_way_connection_count=sum(count == 1 for count in pairs.values()),
                           unattached_endpoint_ids=tuple(endpoint.endpoint_id for endpoint in graph.endpoints if endpoint.port_id not in attached),
                           reachability=tuple(queries))
