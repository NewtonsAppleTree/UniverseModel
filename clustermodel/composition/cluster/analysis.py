"""Exact fixed-path service accounting and conditional analytical communication bounds."""

from dataclasses import dataclass
from math import fsum

from contracts.hardware.network import BandwidthConstraint, finite_quantity
from clustermodel.composition.cluster.model import ClusterSpec, TrafficInput, validate_traffic_references
from clustermodel.fabric.links.model import LinkEstimate, estimate_link
from clustermodel.fabric.routing.paths import Route, _resolve_route
from clustermodel.topology.graph import CutCapacity, _NetworkIndex, cut_capacity


# One actual hop retains its profile result; repeated physical hops remain separate traversal entries.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinkTraversal:
    link_id: str  # Directed physical channel identity.
    estimate: LinkEstimate  # Exact per-hop work, including framing or its explicit unknown state.


# A charge limits existing work and is not an additional physical transfer to add to network wire totals.
@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceCharge:
    resource_id: str  # Unique graph service resource, either link or BandwidthConstraint.
    role: str  # source_tx, destination_rx, link, fabric_shared, or switch_forwarding.
    service_bytes: int  # Demand q_ir [B] in the referenced resource's declared byte basis.


# Each demand preserves its route and service evidence independently of aggregated resource limits.
@dataclass(frozen=True, slots=True, kw_only=True)
class MessageAnalysis:
    message_id: str  # Original P2P demand identity; data/version remain in immutable input.
    payload_bytes: int  # Original logical length D [B].
    route: Route  # Validated selected or explicit physical path.
    traversals: tuple[LinkTraversal, ...]  # Actual ordered hop work; no implicit multicast or reduction.
    charges: tuple[ResourceCharge, ...]  # NIC/link/switch/shared work; repeated crossings charged separately.
    dependency_time_lower_bound_s: float  # Sum of necessary propagation and switch processing delays [s].


# Resource work sums all ranks/groups using one physical capacity definition, with no replicated bandwidth.
@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceLoad:
    resource_id: str  # Unique service resource identity.
    owner_id: str  # Node, switch or graph owner; directional links are graph-owned.
    category: str  # link, nic, switch, or fabric_shared.
    byte_basis: str  # payload or frame, matching the capacity denominator.
    frame_format_id: str | None  # Representation identity for frame work; None for payload.
    capacity_Bps: float  # Conditional model service ceiling C_r [B/s].
    capacity_kind: str  # declared_ceiling or effective_service; fitted rates are conditional model assumptions.
    service_bytes: int  # Q_r=sum_i(q_ir) [B]; exact integer including repeated crossings.
    time_lower_bound_s: float  # Q_r/C_r [s]; no queueing or completion prediction.
    message_ids: tuple[str, ...]  # Unique contributors; per-message charge detail remains in MessageAnalysis.


# Link traffic totals count physical traversals only, independently of the number of service constraints.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinkTraffic:
    link_id: str  # Directed physical channel identity, including unused channels.
    payload_bytes: int  # Sum of logical bytes traversing this link [B], with repeated crossings.
    wire_bytes: int | None  # Sum of pre-PHY frame bytes [B]; None if a used profile omits framing.
    wire_unknown_reason: str | None  # Missing-framing reason; unused links have known zero work.


# A specified directed owner cut measures actual fixed-path crossings and a compatible link capacity sum.
@dataclass(frozen=True, slots=True, kw_only=True)
class CutAnalysis:
    cut_id: str  # Requested cut observation identity.
    capacity: CutCapacity  # Compatible directional link capacities, with selected owners and shared references.
    crossing_count: int  # Number of actual outgoing message traversals [crossing]; revisits count again.
    service_bytes: int  # Actual crossing work D_cut [B] in capacity.byte_basis; zero for no crossing.
    time_lower_bound_s: float  # D_cut/B_cut [s]; an empty unused cut is zero.
    message_ids: tuple[str, ...]  # Unique messages that cross this outgoing cut.


# Analytical output separates communication work, independent necessary bounds and unknown physical costs.
@dataclass(frozen=True, slots=True, kw_only=True)
class TrafficAnalysis:
    messages: tuple[MessageAnalysis, ...]  # Immutable per-message route and work evidence.
    links: tuple[LinkTraffic, ...]  # Every graph link, including zero-work channels.
    resources: tuple[ResourceLoad, ...]  # Every unique link/constraint, including unused limits.
    cuts: tuple[CutAnalysis, ...]  # Requested directed cuts only; no global min-cut claim.
    logical_payload_bytes: int  # Sum of original P2P lengths [B], before path replication.
    total_link_wire_bytes: int | None  # Sum of actual pre-PHY link frame work [B]; not constraint demand sum.
    wire_unknown_reason: str | None  # Why a used link's framing prevents a complete physical-work total.
    resource_time_lower_bound_s: float  # max_r(Q_r/C_r) [s].
    dependency_time_lower_bound_s: float  # Maximum necessary path propagation/processing delay [s].
    cut_time_lower_bound_s: float  # Maximum requested D_cut/B_cut [s]; normally redundant with link bounds.
    communication_time_lower_bound_s: float  # max(resource, dependency, cut) [s], never their sum.
    bottleneck_resource_ids: tuple[str, ...]  # All positive-work resources exactly attaining max_r(Q_r/C_r).
    total_energy_j: float | None  # Complete network energy [J]; unknown without dynamic/leakage characterization.
    energy_unknown_reason: str | None  # Missing physical-cost coverage, including duration-dependent leakage.
    coverage: tuple[str, ...]  # Model assumptions/omissions; no target execution or AI quality claim.


# Evaluate Q/C with exact integer work and reject numerical overflow or positive-work underflow.
def _service_time(work: int, capacity: float) -> float:
    try:
        return finite_quantity("service time", work / capacity, positive=work > 0)
    except OverflowError as exc:
        raise ValueError("service time exceeds finite binary64 range") from exc


# Sum sequential first-data delays only; link startup estimates are not assumed additive across pipelined hops.
def _dependency_time(delays: list[float]) -> float:
    try:
        return finite_quantity("dependency time", fsum(delays))
    except OverflowError as exc:
        raise ValueError("dependency time exceeds finite binary64 range") from exc


# Match payload/frame quantities to one declared constraint; graph validation checks frame-format compatibility.
def _charge(resource: BandwidthConstraint, payload: int, estimate: LinkEstimate, role: str) -> ResourceCharge:
    work = payload if resource.byte_basis == "payload" else estimate.wire_bytes
    if work is None:
        raise ValueError(f"unknown_frame_work: {resource.resource_id} requires explicit framing")
    return ResourceCharge(resource_id=resource.resource_id, role=role, service_bytes=work)


# Resolve each message, count each crossing once, aggregate shared service, and combine independent bounds by max.
def analyze_traffic(cluster: ClusterSpec, traffic: TrafficInput) -> TrafficAnalysis:
    validate_traffic_references(cluster, traffic)
    graph = cluster.graph
    index = _NetworkIndex(graph)
    route_cache, estimate_cache = {}, {}
    endpoints = {endpoint.endpoint_id: endpoint for endpoint in graph.endpoints}
    placements = {placement.rank_id: placement for placement in cluster.placements}
    constraints = {resource.resource_id: resource for resource in graph.constraints}
    messages = []
    for message in traffic.messages:
        src = endpoints[placements[message.src_rank].endpoint_id]
        dst = endpoints[placements[message.dst_rank].endpoint_id]
        key = (src.endpoint_id, dst.endpoint_id, message.explicit_link_ids, message.route_policy)
        if key not in route_cache:
            route_cache[key] = _resolve_route(index, src.endpoint_id, dst.endpoint_id,
                                              explicit_link_ids=message.explicit_link_ids, policy=message.route_policy)
        route = route_cache[key]
        hops = tuple(index.get_link(identity) for identity in route.link_ids)
        traversals = []
        for hop in hops:
            estimate_key = (hop.link_id, message.payload_bytes)
            if estimate_key not in estimate_cache:
                estimate_cache[estimate_key] = estimate_link(hop, message.payload_bytes)
            traversals.append(LinkTraversal(link_id=hop.link_id, estimate=estimate_cache[estimate_key]))
        traversals = tuple(traversals)
        charges, delays = [], [hop.propagation_s for hop in hops]
        for references, estimate, role in ((src.tx_constraint_ids, traversals[0].estimate, "source_tx"),
                                            (dst.rx_constraint_ids, traversals[-1].estimate, "destination_rx")):
            charges.extend(_charge(constraints[ref], message.payload_bytes, estimate, role) for ref in references)
        for position, (hop, traversal) in enumerate(zip(hops, traversals)):
            charges.append(ResourceCharge(resource_id=hop.link_id, role="link", service_bytes=traversal.estimate.service_bytes))
            charges.extend(_charge(constraints[ref], message.payload_bytes, traversal.estimate, "fabric_shared")
                           for ref in hop.shared_constraint_ids)
            if position:
                _, connection, latency = index.get_crossing(hops[position - 1].dst_port_id, hop.src_port_id)
                delays.append(latency)
                charges.extend(_charge(constraints[ref], message.payload_bytes, traversal.estimate, "switch_forwarding")
                               for ref in connection.constraint_ids)
        messages.append(MessageAnalysis(message_id=message.message_id, payload_bytes=message.payload_bytes, route=route,
                                        traversals=traversals, charges=tuple(charges),
                                        dependency_time_lower_bound_s=_dependency_time(delays)))
    work = {identity: 0 for identity in tuple(constraints) + tuple(hop.link_id for hop in graph.links)}
    contributors = {identity: set() for identity in work}
    link_payload = {hop.link_id: 0 for hop in graph.links}
    link_wire = {hop.link_id: 0 for hop in graph.links}
    link_crossings = {hop.link_id: 0 for hop in graph.links}
    for message in messages:
        for charge in message.charges:
            work[charge.resource_id] += charge.service_bytes
            contributors[charge.resource_id].add(message.message_id)
        for traversal in message.traversals:
            identity, estimate = traversal.link_id, traversal.estimate
            link_payload[identity] += estimate.payload_bytes
            link_crossings[identity] += 1
            link_wire[identity] = (link_wire[identity] + estimate.wire_bytes
                                   if link_wire[identity] is not None and estimate.wire_bytes is not None else None)
    resources = []
    node_ids = set(graph.node_ids)
    for resource in graph.constraints:
        category = "nic" if resource.owner_id in node_ids else "fabric_shared" if resource.owner_id == graph.graph_id else "switch"
        resources.append(ResourceLoad(resource_id=resource.resource_id, owner_id=resource.owner_id, category=category,
                                      byte_basis=resource.byte_basis, frame_format_id=resource.frame_format_id,
                                      capacity_Bps=resource.capacity_Bps, capacity_kind=resource.capacity_kind,
                                      service_bytes=work[resource.resource_id],
                                      time_lower_bound_s=_service_time(work[resource.resource_id], resource.capacity_Bps),
                                      message_ids=tuple(sorted(contributors[resource.resource_id]))))
    for hop in graph.links:
        resources.append(ResourceLoad(resource_id=hop.link_id, owner_id=graph.graph_id, category="link",
                                      byte_basis=hop.service_byte_basis, frame_format_id=hop.frame_format_id,
                                      capacity_Bps=hop.service_capacity_Bps, capacity_kind=hop.capacity_kind,
                                      service_bytes=work[hop.link_id],
                                      time_lower_bound_s=_service_time(work[hop.link_id], hop.service_capacity_Bps),
                                      message_ids=tuple(sorted(contributors[hop.link_id]))))
    resources.sort(key=lambda item: item.resource_id)
    cuts = []
    for request in traffic.requested_cuts:
        capacity = cut_capacity(graph, request.node_ids, switch_ids=request.switch_ids)
        ids = set(capacity.link_ids)
        demand = sum(work[identity] for identity in ids)
        if demand and capacity.empty:
            raise ValueError("infeasible_cut: positive demand across an empty cut")
        cuts.append(CutAnalysis(cut_id=request.cut_id, capacity=capacity, crossing_count=sum(link_crossings[identity] for identity in ids),
                                service_bytes=demand, time_lower_bound_s=_service_time(demand, capacity.capacity_Bps) if demand else 0.0,
                                message_ids=tuple(sorted({message_id for identity in ids for message_id in contributors[identity]}))))
    reason = "used effective-payload profile omits packetization and pre-PHY frame bytes"
    links = tuple(LinkTraffic(link_id=hop.link_id, payload_bytes=link_payload[hop.link_id], wire_bytes=link_wire[hop.link_id],
                              wire_unknown_reason=reason if link_wire[hop.link_id] is None else None) for hop in graph.links)
    unknown_links = tuple(item.link_id for item in links if item.wire_bytes is None)
    resource_bound = max((resource.time_lower_bound_s for resource in resources), default=0.0)
    dependency_bound = max((message.dependency_time_lower_bound_s for message in messages), default=0.0)
    cut_bound = max((cut.time_lower_bound_s for cut in cuts), default=0.0)
    return TrafficAnalysis(messages=tuple(messages), links=links, resources=tuple(resources), cuts=tuple(cuts),
                           logical_payload_bytes=sum(message.payload_bytes for message in messages),
                           total_link_wire_bytes=None if unknown_links else sum(item.wire_bytes for item in links),
                           wire_unknown_reason=f"{reason}: {', '.join(unknown_links)}" if unknown_links else None,
                           resource_time_lower_bound_s=resource_bound, dependency_time_lower_bound_s=dependency_bound,
                           cut_time_lower_bound_s=cut_bound,
                           communication_time_lower_bound_s=max(resource_bound, dependency_bound, cut_bound),
                           bottleneck_resource_ids=tuple(resource.resource_id for resource in resources
                                                         if resource.service_bytes and resource.time_lower_bound_s == resource_bound),
                           total_energy_j=None, energy_unknown_reason="No network dynamic/leakage characterization or execution duration supplied",
                           coverage=("All fixed positive-length P2P messages ready at origin; no local-node service",
                                     "Bounds conditional on declared capacities, profiles and fixed routes; effective rates are not physical guarantees",
                                     "Switch payload/outgoing-frame work charged once per explicit crossing",
                                     "Dependency bound includes propagation/processing only; isolated startup and serialization are not summed over hops",
                                     "No queues, achieved throughput, completion/visibility, collective numerics, AI quality or physical calibration"))
