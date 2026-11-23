"""Small pure topology builders; caller profiles and NIC resource ownership stay explicit."""

from dataclasses import replace
from collections.abc import Mapping

from contracts.hardware.network import BandwidthConstraint, NetworkEndpointSpec, string_tuple
from clustermodel.fabric.links.model import LinkParams
from clustermodel.fabric.switches.model import SwitchConnection, SwitchParams
from clustermodel.topology.graph import NetworkGraph, _freeze_records


# Copy a declared directional profile into two independent directions; no duplex sharing is inferred.
def _duplex(profile: LinkParams, a: str, b: str, a_port: str, b_port: str) -> tuple[LinkParams, ...]:
    if not isinstance(profile, LinkParams):
        raise TypeError("profile: expected LinkParams")
    return (replace(profile, link_id=f"{a}->{b}", src_port_id=a_port, dst_port_id=b_port),
            replace(profile, link_id=f"{b}->{a}", src_port_id=b_port, dst_port_id=a_port))


# Declare an all-port crossbar explicitly with payload counted once per ingress-to-egress crossing.
def _switch(identity: str, ports: tuple[str, ...], capacity_Bps: float, latency_s: float,
            source_ref: str) -> tuple[SwitchParams, BandwidthConstraint]:
    resource = BandwidthConstraint(resource_id=f"{identity}.internal", owner_id=identity,
                                   capacity_Bps=capacity_Bps, byte_basis="payload", capacity_kind="declared_ceiling",
                                   source_ref=source_ref, coverage=("one payload charge per switch crossing",))
    switch = SwitchParams(switch_id=identity, port_ids=ports, forwarding_latency_s=latency_s,
                          source_ref=source_ref, coverage=("explicit crossbar; no queue or multicast reduction",),
                          connections=tuple(SwitchConnection(ingress_port_id=ingress, egress_port_id=egress,
                                                             constraint_ids=(resource.resource_id,))
                                            for ingress in ports for egress in ports if ingress != egress))
    return switch, resource


# Build two directly attached NIC boundaries, preserving caller-supplied node/shared bandwidth constraints.
def direct_network(*, graph_id: str, endpoints: tuple[NetworkEndpointSpec, ...],
                   constraints: tuple[BandwidthConstraint, ...], link_profile: LinkParams) -> NetworkGraph:
    if len(endpoints) != 2:
        raise ValueError("direct_network requires two endpoints")
    src, dst = endpoints
    return NetworkGraph(graph_id=graph_id, endpoints=endpoints, constraints=constraints,
                        links=_duplex(link_profile, src.endpoint_id, dst.endpoint_id, src.port_id, dst.port_id))


# Build one full-duplex access attachment per endpoint and one explicitly shared switch service resource.
def single_switch_network(*, graph_id: str, endpoints: tuple[NetworkEndpointSpec, ...],
                          constraints: tuple[BandwidthConstraint, ...], access_profile: LinkParams,
                          switch_capacity_Bps: float, forwarding_latency_s: float, source_ref: str,
                          switch_id: str = "s0") -> NetworkGraph:
    ports = tuple(f"{switch_id}:{endpoint.endpoint_id}" for endpoint in endpoints)
    switch, resource = _switch(switch_id, ports, switch_capacity_Bps, forwarding_latency_s, source_ref)
    links = tuple(link for endpoint, port in zip(endpoints, ports)
                  for link in _duplex(access_profile, endpoint.endpoint_id, switch_id, endpoint.port_id, port))
    return NetworkGraph(graph_id=graph_id, endpoints=endpoints, constraints=tuple(constraints) + (resource,),
                        links=links, switches=(switch,), schema_version="routed-network-graph/v1")


# Join two explicit endpoint partitions through independent uplink directions; shared duplex needs a supplied constraint.
def two_partition_network(*, graph_id: str, left: tuple[NetworkEndpointSpec, ...],
                          right: tuple[NetworkEndpointSpec, ...], constraints: tuple[BandwidthConstraint, ...],
                          access_profile: LinkParams, uplink_profile: LinkParams, switch_capacity_Bps: float,
                          forwarding_latency_s: float, source_ref: str,
                          left_switch_id: str = "sL", right_switch_id: str = "sR") -> NetworkGraph:
    if not left or not right:
        raise ValueError("both partitions require endpoints")
    if left_switch_id == right_switch_id:
        raise ValueError("partition switches must have distinct identities")
    links, switches, resources = [], [], list(constraints)
    for identity, other, endpoints in ((left_switch_id, right_switch_id, left),
                                        (right_switch_id, left_switch_id, right)):
        ports = tuple(f"{identity}:{endpoint.endpoint_id}" for endpoint in endpoints) + (f"{identity}:{other}",)
        switch, resource = _switch(identity, ports, switch_capacity_Bps, forwarding_latency_s, source_ref)
        switches.append(switch)
        resources.append(resource)
        for endpoint, port in zip(endpoints, ports):
            links.extend(_duplex(access_profile, endpoint.endpoint_id, identity, endpoint.port_id, port))
    links.extend(_duplex(uplink_profile, left_switch_id, right_switch_id,
                         f"{left_switch_id}:{right_switch_id}", f"{right_switch_id}:{left_switch_id}"))
    return NetworkGraph(graph_id=graph_id, endpoints=tuple(left) + tuple(right), constraints=tuple(resources),
                        links=tuple(links), switches=tuple(switches), schema_version="routed-network-graph/v1")


# Build a complete leaf-to-spine fabric with explicit endpoint partitions and independent full-duplex uplinks.
def leaf_spine_network(*, graph_id: str, leaves: Mapping[str, tuple[NetworkEndpointSpec, ...]],
                       spine_ids: tuple[str, ...], constraints: tuple[BandwidthConstraint, ...],
                       access_profile: LinkParams, uplink_profile: LinkParams,
                       leaf_capacity_Bps: float, spine_capacity_Bps: float,
                       leaf_forwarding_latency_s: float, spine_forwarding_latency_s: float,
                       source_ref: str) -> NetworkGraph:
    if not isinstance(leaves, Mapping) or not leaves:
        raise ValueError("leaves: expected a nonempty switch-to-endpoints mapping")
    leaf_ids = tuple(sorted(string_tuple("leaf IDs", tuple(leaves), unique=True)))
    spines = tuple(sorted(string_tuple("spine_ids", spine_ids, unique=True)))
    if set(leaf_ids) & set(spines):
        raise ValueError("leaf and spine identities must be distinct")
    partitions = {identity: _freeze_records("leaf endpoints", leaves[identity], NetworkEndpointSpec, "endpoint_id")
                  for identity in leaf_ids}
    if any(not endpoints for endpoints in partitions.values()):
        raise ValueError("each leaf partition requires at least one endpoint")
    endpoints = _freeze_records("endpoints", tuple(endpoint for values in partitions.values() for endpoint in values),
                                NetworkEndpointSpec, "endpoint_id")
    if {endpoint.endpoint_id for endpoint in endpoints} & (set(leaf_ids) | set(spines)):
        raise ValueError("builder endpoint IDs must be distinct from switch IDs")
    links, switches, resources = [], [], list(constraints)
    for leaf, attached in partitions.items():
        ports = tuple(f"{leaf}:access:{endpoint.endpoint_id}" for endpoint in attached) + tuple(f"{leaf}:spine:{spine}" for spine in spines)
        switch, resource = _switch(leaf, ports, leaf_capacity_Bps, leaf_forwarding_latency_s, source_ref)
        switches.append(switch)
        resources.append(resource)
        for endpoint in attached:
            links.extend(_duplex(access_profile, endpoint.endpoint_id, leaf, endpoint.port_id, f"{leaf}:access:{endpoint.endpoint_id}"))
        for spine in spines:
            links.extend(_duplex(uplink_profile, leaf, spine, f"{leaf}:spine:{spine}", f"{spine}:leaf:{leaf}"))
    for spine in spines:
        switch, resource = _switch(spine, tuple(f"{spine}:leaf:{leaf}" for leaf in leaf_ids),
                                   spine_capacity_Bps, spine_forwarding_latency_s, source_ref)
        switches.append(switch)
        resources.append(resource)
    return NetworkGraph(graph_id=graph_id, endpoints=endpoints, constraints=tuple(resources), links=tuple(links),
                        switches=tuple(switches), schema_version="routed-network-graph/v1")
