"""Validated directed physical wiring with explicit switch crossings and owner cuts."""

from dataclasses import dataclass
from math import fsum
from types import MappingProxyType
from collections.abc import Mapping
from typing import Literal, TypeVar

from contracts.hardware.network import (
    BandwidthConstraint, NetworkEndpointSpec, finite_quantity, string_tuple, validate_identity,
)
from clustermodel.fabric.links.model import LinkParams
from clustermodel.fabric.switches.model import SwitchConnection, SwitchParams


T = TypeVar("T")  # Immutable graph record type; preserves endpoint/link/constraint types when freezing.


# Own, type-check and sort each resource collection; duplicate IDs never silently overwrite records.
def _freeze_records(name: str, values: tuple[T, ...], expected: type[T], identity: str) -> tuple[T, ...]:
    if not isinstance(values, (list, tuple)) or any(not isinstance(value, expected) for value in values):
        raise TypeError(f"{name}: expected a list/tuple of {expected.__name__}")
    records = tuple(sorted(values, key=lambda value: getattr(value, identity)))
    ids = tuple(getattr(value, identity) for value in records)
    if len(set(ids)) != len(ids):
        raise ValueError(f"{name}: duplicate {identity}")
    return records


# A graph references NIC boundaries and explicit fabric forwarding capabilities without creating execution state.
@dataclass(frozen=True, slots=True, kw_only=True)
class NetworkGraph:
    graph_id: str  # Fabric owner identity; must be distinct from every node_id.
    endpoints: tuple[NetworkEndpointSpec, ...]  # Immutable external NIC ports; at least one endpoint.
    links: tuple[LinkParams, ...]  # Directed channels between different node/switch owners; disconnected graphs are valid.
    constraints: tuple[BandwidthConstraint, ...]  # Unique node/switch/fabric limits referenced by endpoints, crossings and links.
    switches: tuple[SwitchParams, ...] = ()  # Unique fabric switches; endpoints never act as forwarding devices.
    schema_version: Literal["direct-network-graph/v1", "routed-network-graph/v1"] = "direct-network-graph/v1"  # Explicit graph semantics.

    # Canonicalize unordered resource sets, then validate references, ownership and physical attachments.
    def __post_init__(self) -> None:
        validate_identity("graph_id", self.graph_id)
        if self.schema_version not in ("direct-network-graph/v1", "routed-network-graph/v1"):
            raise ValueError("unsupported network graph schema_version")
        if self.switches and self.schema_version != "routed-network-graph/v1":
            raise ValueError("switches require routed-network-graph/v1")
        for name, expected, identity in (("endpoints", NetworkEndpointSpec, "endpoint_id"),
                                         ("links", LinkParams, "link_id"),
                                         ("constraints", BandwidthConstraint, "resource_id"),
                                         ("switches", SwitchParams, "switch_id")):
            object.__setattr__(self, name, _freeze_records(name, getattr(self, name), expected, identity))
        if not self.endpoints:
            raise ValueError("endpoints: a network graph requires at least one endpoint")
        validate_graph(self)

    # Node membership is derived from endpoint ownership; it is not an independently editable count.
    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(sorted({endpoint.node_id for endpoint in self.endpoints}))


# Index one immutable graph for a batch of queries; derived lookup state never enters graph identity or artifacts.
class _NetworkIndex:
    # Use O(ports + links + crossings) storage and sorted adjacency without allocating hardware resources.
    def __init__(self, graph: NetworkGraph) -> None:
        if not isinstance(graph, NetworkGraph):
            raise TypeError("graph: expected NetworkGraph")
        self.endpoints: Mapping[str, NetworkEndpointSpec] = MappingProxyType({
            endpoint.endpoint_id: endpoint for endpoint in graph.endpoints})  # External NIC boundaries keyed by identity.
        self.links: Mapping[str, LinkParams] = MappingProxyType({
            link.link_id: link for link in graph.links})  # Directed physical channels, each stored once.
        self.departures: Mapping[str, LinkParams] = MappingProxyType({
            link.src_port_id: link for link in graph.links})  # At most one outgoing channel per physical port.
        self.endpoint_ports: Mapping[str, str] = MappingProxyType({
            endpoint.port_id: endpoint.endpoint_id for endpoint in graph.endpoints})  # Terminal ports; never forwarding nodes.
        crossings, successors = {}, {}
        for switch in graph.switches:
            for connection in switch.connections:
                crossings[connection.ingress_port_id, connection.egress_port_id] = (
                    switch.switch_id, connection, switch.forwarding_latency_s)
                link = self.departures.get(connection.egress_port_id)
                if link is not None:
                    successors.setdefault(connection.ingress_port_id, []).append(link)
        self.crossings: Mapping[tuple[str, str], tuple[str, SwitchConnection, float]] = MappingProxyType(
            crossings)  # Declared forwarding relation and necessary processing delay [s].
        self.successors: Mapping[str, tuple[LinkParams, ...]] = MappingProxyType({
            port: tuple(sorted(links, key=lambda item: item.link_id)) for port, links in successors.items()
        })  # Legal next channels in link-ID order; unavailable egress directions are omitted.

    # Resolve a directed channel in expected O(1) time, preserving diagnostics for an unknown identity.
    def get_link(self, link_id: str) -> LinkParams:
        validate_identity("link_id", link_id)
        if link_id not in self.links:
            raise ValueError(f"unknown link_id: {link_id}")
        return self.links[link_id]

    # Only a declared switch relation allows transit; sharing a node or owner is insufficient.
    def get_crossing(self, ingress: str, egress: str) -> tuple[str, SwitchConnection, float]:
        crossing = self.crossings.get((ingress, egress))
        if crossing is None:
            raise ValueError(f"invalid_route: no switch crossing {ingress} -> {egress}; endpoint transit is forbidden")
        return crossing

    # Traverse active directed channels, stopping at all receiving NIC ports, including other NICs of the source node.
    def reachable_endpoints(self, endpoint_id: str) -> tuple[str, ...]:
        validate_identity("endpoint_id", endpoint_id)
        if endpoint_id not in self.endpoints:
            raise ValueError(f"unknown endpoint_id: {endpoint_id}")
        first = self.departures.get(self.endpoints[endpoint_id].port_id)
        pending = [first] if first is not None else []
        visited, found = set(), set()
        while pending:
            link = pending.pop()
            if link.link_id in visited:
                continue
            visited.add(link.link_id)
            destination = self.endpoint_ports.get(link.dst_port_id)
            if destination is not None:
                if destination != endpoint_id:
                    found.add(destination)
            else:
                pending.extend(self.successors.get(link.dst_port_id, ()))
        return tuple(sorted(found))


# Require the referenced resource to exist and be owned by the declared node/fabric boundary.
def _check_reference(resource_id: str, owner_id: str,
                     constraints: dict[str, BandwidthConstraint], context: str) -> None:
    if resource_id not in constraints:
        raise ValueError(f"{context}: missing bandwidth constraint {resource_id}")
    if constraints[resource_id].owner_id != owner_id:
        raise ValueError(f"{context}: constraint {resource_id} belongs to a different owner")


# Validate wiring, ownership and byte representations; NICs cannot implicitly bridge ports.
def validate_graph(graph: NetworkGraph) -> None:
    if not isinstance(graph, NetworkGraph):
        raise TypeError("graph: expected NetworkGraph")
    if graph.graph_id in graph.node_ids:
        raise ValueError("graph_id must be distinct from node ownership IDs")
    switch_ids = {switch.switch_id for switch in graph.switches}
    if switch_ids & (set(graph.node_ids) | {graph.graph_id}):
        raise ValueError("switch owner IDs must be distinct from graph_id and nodes")
    ports = port_owners(graph)
    if len(ports) != len(graph.endpoints) + sum(len(switch.port_ids) for switch in graph.switches):
        raise ValueError("endpoints: duplicate physical port_id")
    constraints = {resource.resource_id: resource for resource in graph.constraints}
    if set(constraints) & {link.link_id for link in graph.links}:
        raise ValueError("duplicate resource identity between link and bandwidth constraint")
    owners = set(graph.node_ids) | {graph.graph_id} | switch_ids
    for resource in graph.constraints:
        if resource.owner_id not in owners:
            raise ValueError(f"constraint {resource.resource_id}: unknown owner_id {resource.owner_id}")
    for endpoint in graph.endpoints:
        for reference in endpoint.tx_constraint_ids + endpoint.rx_constraint_ids:
            _check_reference(reference, endpoint.node_id, constraints, endpoint.endpoint_id)
    egress_references = {}
    for switch in graph.switches:
        for connection in switch.connections:
            for reference in connection.constraint_ids:
                _check_reference(reference, switch.switch_id, constraints, switch.switch_id)
            egress_references.setdefault(connection.egress_port_id, set()).update(connection.constraint_ids)
    endpoints = {endpoint.port_id: endpoint for endpoint in graph.endpoints}
    outgoing, incoming, peers = set(), set(), {}
    for link in graph.links:
        if link.src_port_id not in ports or link.dst_port_id not in ports:
            raise ValueError(f"link {link.link_id}: missing endpoint port or switch port")
        src, dst = ports[link.src_port_id], ports[link.dst_port_id]
        if src == dst:
            raise ValueError(f"link {link.link_id}: unsupported_local_path; node-internal links require systemmodel")
        if link.src_port_id in outgoing or link.dst_port_id in incoming:
            raise ValueError(f"link {link.link_id}: physical port direction already connected")
        outgoing.add(link.src_port_id)
        incoming.add(link.dst_port_id)
        for port, peer in ((link.src_port_id, link.dst_port_id), (link.dst_port_id, link.src_port_id)):
            if port in peers and peers[port] != peer:
                raise ValueError(f"link {link.link_id}: a physical port cannot attach to different peers")
            peers[port] = peer
        for reference in link.shared_constraint_ids:
            _check_reference(reference, graph.graph_id, constraints, link.link_id)
        references = list(link.shared_constraint_ids)
        if link.src_port_id in endpoints:
            references.extend(endpoints[link.src_port_id].tx_constraint_ids)
        if link.dst_port_id in endpoints:
            references.extend(endpoints[link.dst_port_id].rx_constraint_ids)
        references.extend(sorted(egress_references.get(link.src_port_id, ())))
        frame_references = [reference for reference in references if constraints[reference].byte_basis == "frame"]
        frame_format = link.frame_format_id if frame_references else None
        for reference in frame_references:
            resource = constraints[reference]
            if resource.frame_format_id != frame_format:
                raise ValueError(f"link {link.link_id}: incompatible frame basis for constraint {reference}")


# Map physical ports to their node or switch owner; validate_graph detects overwritten duplicate ports.
def port_owners(graph: NetworkGraph) -> dict[str, str]:
    return {**{endpoint.port_id: endpoint.node_id for endpoint in graph.endpoints},
            **{port: switch.switch_id for switch in graph.switches for port in switch.port_ids}}


# Enumerate legal next physical links from a switch ingress, never from a receiving NIC endpoint.
def next_links(graph: NetworkGraph, ingress_port_id: str) -> tuple[LinkParams, ...]:
    egress = {connection.egress_port_id for switch in graph.switches for connection in switch.connections
              if connection.ingress_port_id == ingress_port_id}
    return tuple(link for link in graph.links if link.src_port_id in egress)


# Resolve a declared link by identity; missing links are errors, never a zero-capacity placeholder.
def get_link(graph: NetworkGraph, link_id: str) -> LinkParams:
    if not isinstance(graph, NetworkGraph):
        raise TypeError("graph: expected NetworkGraph")
    validate_identity("link_id", link_id)
    for link in graph.links:
        if link.link_id == link_id:
            return link
    raise ValueError(f"unknown link_id: {link_id}")


# Traverse declared switch crossings, stopping at endpoint ports; preserve direct-graph reachability semantics.
def reachable_endpoints(graph: NetworkGraph, endpoint_id: str) -> tuple[str, ...]:
    return _NetworkIndex(graph).reachable_endpoints(endpoint_id)


# An outgoing node cut reports only a link capacity sum; shared resources can further restrict service.
@dataclass(frozen=True, slots=True, kw_only=True)
class CutCapacity:
    node_ids: tuple[str, ...]  # Selected complete nodes S; all NIC ports of a node move together.
    link_ids: tuple[str, ...]  # Directed links from S to its complement; reverse links excluded.
    capacity_Bps: float  # Sum of matching link service capacities [B/s]; not attainable aggregate throughput.
    byte_basis: str | None  # Common frame/payload representation; None for an empty outgoing cut.
    frame_format_id: str | None  # Common frame representation identity, if applicable.
    capacity_kind: str | None  # effective_service if any contributing rate is fitted; None for empty cuts.
    shared_constraint_ids: tuple[str, ...]  # Fabric constraints still applicable beyond the link sum.
    switch_ids: tuple[str, ...] = ()  # Selected whole switches in S; all their ports move together.

    # No outgoing links means no network service across this direction, not proof that any demand is feasible.
    @property
    def empty(self) -> bool:
        return not self.link_ids


# Sum only a specified directed cut in a compatible byte basis; this is not a min-cut or routing solver.
def cut_capacity(graph: NetworkGraph, node_ids: tuple[str, ...], *, switch_ids: tuple[str, ...] = ()) -> CutCapacity:
    if not isinstance(graph, NetworkGraph):
        raise TypeError("graph: expected NetworkGraph")
    selected = tuple(sorted(string_tuple("cut node_ids", node_ids, unique=True, allow_empty=True)))
    if not set(selected).issubset(graph.node_ids):
        raise ValueError("cut node_ids: unknown node")
    switches = tuple(sorted(string_tuple("cut switch_ids", switch_ids, unique=True, allow_empty=True)))
    if not set(switches).issubset(switch.switch_id for switch in graph.switches):
        raise ValueError("cut switch_ids: unknown switch")
    ports = port_owners(graph)
    members = set(selected) | set(switches)
    links = tuple(link for link in graph.links
                  if ports[link.src_port_id] in members and ports[link.dst_port_id] not in members)
    bases = {(link.service_byte_basis, link.frame_format_id) for link in links}
    if len(bases) > 1:
        raise ValueError("incompatible_byte_basis: cut mixes payload or different frame representations")
    basis, frame_format = next(iter(bases)) if bases else (None, None)
    try:
        capacity = finite_quantity("cut capacity_Bps", fsum(link.service_capacity_Bps for link in links))
    except OverflowError as exc:
        raise ValueError("cut capacity exceeds finite binary64 range") from exc
    kind = ("effective_service" if any(link.capacity_kind == "effective_service" for link in links)
            else "declared_ceiling") if links else None
    return CutCapacity(node_ids=selected, switch_ids=switches, link_ids=tuple(link.link_id for link in links),
                       capacity_Bps=capacity, byte_basis=basis, frame_format_id=frame_format,
                       capacity_kind=kind,
                       shared_constraint_ids=tuple(sorted({ref for link in links for ref in link.shared_constraint_ids})))
