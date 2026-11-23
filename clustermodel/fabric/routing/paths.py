"""Fixed directed paths and deterministic minimum-physical-hop routing."""

from dataclasses import dataclass
from collections import deque
import heapq
from typing import Literal

from contracts.hardware.network import NetworkEndpointSpec, string_tuple, validate_count, validate_identity
from clustermodel.fabric.switches.model import SwitchConnection
from clustermodel.topology.graph import NetworkGraph, _NetworkIndex


# A route records physical hops only; switch crossings are derived and validated between adjacent links.
@dataclass(frozen=True, slots=True, kw_only=True)
class Route:
    src_endpoint_id: str  # Source external NIC boundary.
    dst_endpoint_id: str  # Destination external NIC boundary on another node.
    link_ids: tuple[str, ...]  # Ordered nonempty physical hops; finite explicit walks may revisit fabric links.
    policy: Literal["explicit/v1", "shortest-hop-lex/v1"]  # Selection provenance; no dynamic balancing.

    # Own the route sequence and retain order, including deliberate repeated crossings.
    def __post_init__(self) -> None:
        validate_identity("src_endpoint_id", self.src_endpoint_id)
        validate_identity("dst_endpoint_id", self.dst_endpoint_id)
        object.__setattr__(self, "link_ids", string_tuple("link_ids", self.link_ids))
        if self.policy not in ("explicit/v1", "shortest-hop-lex/v1"):
            raise ValueError("unsupported route policy")


# Resolve the two external boundaries; node-internal messages require a future explicit systemmodel summary.
def _endpoints(index: _NetworkIndex, source: str, destination: str) -> tuple[NetworkEndpointSpec, NetworkEndpointSpec]:
    validate_identity("source endpoint", source)
    validate_identity("destination endpoint", destination)
    endpoints = index.endpoints
    if source not in endpoints or destination not in endpoints:
        raise ValueError("route references an unknown endpoint")
    src, dst = endpoints[source], endpoints[destination]
    if src.node_id == dst.node_id:
        raise ValueError("unsupported_local_path: node-internal service summary is not implemented")
    return src, dst


# Find an explicit forwarding relation; a shared owner alone does not permit traffic to cross ports.
def get_crossing(graph: NetworkGraph, ingress: str, egress: str) -> tuple[str, SwitchConnection, float]:
    for switch in graph.switches:
        for connection in switch.connections:
            if (connection.ingress_port_id, connection.egress_port_id) == (ingress, egress):
                return switch.switch_id, connection, switch.forwarding_latency_s
    raise ValueError(f"invalid_route: no switch crossing {ingress} -> {egress}; endpoint transit is forbidden")


# Check source/destination directions and every intermediate crossing, without requiring shortest paths.
def validate_route(graph: NetworkGraph, route: Route) -> None:
    _validate_route(_NetworkIndex(graph), route)


# Validate against one query-local index; explicit revisits retain every hop and crossing.
def _validate_route(index: _NetworkIndex, route: Route) -> None:
    if not isinstance(route, Route):
        raise TypeError("route: expected Route")
    src, dst = _endpoints(index, route.src_endpoint_id, route.dst_endpoint_id)
    links = tuple(index.get_link(identity) for identity in route.link_ids)
    if links[0].src_port_id != src.port_id or links[-1].dst_port_id != dst.port_id:
        raise ValueError("invalid_route: wrong source/destination direction")
    for first, second in zip(links, links[1:]):
        index.get_crossing(first.dst_port_id, second.src_port_id)


# Choose the fewest physical links, breaking ties by the entire lexicographic link-ID sequence.
def resolve_route(graph: NetworkGraph, src_endpoint_id: str, dst_endpoint_id: str, *,
                  explicit_link_ids: tuple[str, ...] | None = None,
                  policy: str = "shortest-hop-lex/v1") -> Route:
    return _resolve_route(_NetworkIndex(graph), src_endpoint_id, dst_endpoint_id,
                          explicit_link_ids=explicit_link_ids, policy=policy)


# Reuse adjacency for a batch without changing the heap ordering or whole-path lexicographic tie rule.
def _resolve_route(index: _NetworkIndex, src_endpoint_id: str, dst_endpoint_id: str, *,
                   explicit_link_ids: tuple[str, ...] | None = None,
                   policy: str = "shortest-hop-lex/v1") -> Route:
    src, dst = _endpoints(index, src_endpoint_id, dst_endpoint_id)
    if explicit_link_ids is not None:
        if policy != "explicit/v1":
            raise ValueError("explicit route requires policy explicit/v1")
        route = Route(src_endpoint_id=src_endpoint_id, dst_endpoint_id=dst_endpoint_id,
                      link_ids=explicit_link_ids, policy="explicit/v1")
        _validate_route(index, route)
        return route
    if policy != "shortest-hop-lex/v1":
        raise ValueError("selected route requires policy shortest-hop-lex/v1")
    first = index.departures.get(src.port_id)
    pending = [(1, (first.link_id,), first.dst_port_id)] if first is not None else []
    heapq.heapify(pending)
    visited = set()
    while pending:
        hops, path, port = heapq.heappop(pending)
        if port in visited:
            continue
        visited.add(port)
        if port == dst.port_id:
            return Route(src_endpoint_id=src_endpoint_id, dst_endpoint_id=dst_endpoint_id,
                         link_ids=path, policy="shortest-hop-lex/v1")
        for link in index.successors.get(port, ()):
            heapq.heappush(pending, (hops + 1, path + (link.link_id,), link.dst_port_id))
    raise ValueError(f"unreachable: {src_endpoint_id} -> {dst_endpoint_id}")


# Report structural route diversity separately from bandwidth or an actual multipath scheduling policy.
@dataclass(frozen=True, slots=True, kw_only=True)
class RouteChoices:
    src_endpoint_id: str  # Queried external source NIC.
    dst_endpoint_id: str  # Queried external destination on another node.
    minimum_hops: int  # Fewest directed physical link traversals [hop].
    total_shortest_paths: int  # Exact count of shortest link sequences; shared links/resources may overlap.
    routes: tuple[Route, ...]  # At most max_paths lexicographic candidates, ready for explicit/v1 selection.
    truncated: bool  # True iff valid shortest paths remain beyond the returned prefix.


# Count the shortest-path DAG without enumerating all paths, then materialize only the requested prefix.
def shortest_route_choices(graph: NetworkGraph, src_endpoint_id: str, dst_endpoint_id: str, *,
                           max_paths: int = 8) -> RouteChoices:
    index = _NetworkIndex(graph)
    src, dst = _endpoints(index, src_endpoint_id, dst_endpoint_id)
    validate_count("max_paths", max_paths, minimum=1)
    distance, parents = {src.port_id: 0}, {src.port_id: []}
    pending = deque((src.port_id,))
    while pending:
        port = pending.popleft()
        if dst.port_id in distance and distance[port] >= distance[dst.port_id]:
            continue
        first = index.departures.get(port) if port == src.port_id else None
        candidates = ((first,) if first is not None else ()) if port == src.port_id else index.successors.get(port, ())
        for link in candidates:
            target, depth = link.dst_port_id, distance[port] + 1
            if target not in distance:
                distance[target] = depth
                parents[target] = []
                pending.append(target)
            if distance[target] == depth:
                parents[target].append((port, link.link_id))
    if dst.port_id not in distance:
        raise ValueError(f"unreachable: {src_endpoint_id} -> {dst_endpoint_id}")
    ancestors, stack = set(), [dst.port_id]
    while stack:
        port = stack.pop()
        if port not in ancestors:
            ancestors.add(port)
            stack.extend(previous for previous, _ in parents[port])
    children = {port: [] for port in ancestors}
    counts = {src.port_id: 1}
    for port in sorted(ancestors, key=lambda item: (distance[item], item)):
        if port != src.port_id:
            counts[port] = sum(counts[previous] for previous, _ in parents[port])
        for previous, identity in parents[port]:
            children[previous].append((identity, port))
    paths, stack = [], [(src.port_id, ())]
    while stack and len(paths) < max_paths:
        port, path = stack.pop()
        if port == dst.port_id:
            paths.append(Route(src_endpoint_id=src_endpoint_id, dst_endpoint_id=dst_endpoint_id,
                               link_ids=path, policy="explicit/v1"))
        else:
            stack.extend((target, path + (identity,)) for identity, target in sorted(children[port], reverse=True))
    return RouteChoices(src_endpoint_id=src_endpoint_id, dst_endpoint_id=dst_endpoint_id,
                        minimum_hops=distance[dst.port_id], total_shortest_paths=counts[dst.port_id],
                        routes=tuple(paths), truncated=len(paths) < counts[dst.port_id])
