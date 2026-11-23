"""Immutable static connectivity outages; no fault timing, repair or automatic recovery simulation."""

from dataclasses import dataclass, replace
from typing import Literal

from contracts.hardware.network import string_tuple, validate_identity
from contracts.versions.json_codec import content_hash
from clustermodel.topology.graph import NetworkGraph, port_owners


# Outages identify unavailable directions or complete owners while retaining installed endpoint/resource identities.
@dataclass(frozen=True, slots=True, kw_only=True)
class NetworkOutage:
    source_ref: str  # Explicit scenario assumption or observed failure-source/version reference.
    disabled_link_ids: tuple[str, ...] = ()  # Selected directed channels; reverse direction is not implicitly disabled.
    disabled_node_ids: tuple[str, ...] = ()  # All incident channels of these nodes become unavailable.
    disabled_switch_ids: tuple[str, ...] = ()  # All incident channels of these switches become unavailable.
    schema_version: Literal["network-static-outage/v1"] = "network-static-outage/v1"  # Static availability semantics.

    # Own canonical selection sets without inventing probabilities, timers or replacement resources.
    def __post_init__(self) -> None:
        validate_identity("source_ref", self.source_ref)
        for name in ("disabled_link_ids", "disabled_node_ids", "disabled_switch_ids"):
            object.__setattr__(self, name, tuple(sorted(string_tuple(name, getattr(self, name), unique=True, allow_empty=True))))
        if self.schema_version != "network-static-outage/v1":
            raise ValueError("unsupported static outage schema_version")


# A static view retains its cause and original graph identity; preserved capacities are installed declarations.
@dataclass(frozen=True, slots=True, kw_only=True)
class OutageView:
    original_graph_hash: str  # Canonical identity of the graph before removing channels.
    outage: NetworkOutage  # Exact requested static availability change and its source.
    removed_link_ids: tuple[str, ...]  # Union of explicitly selected and owner-incident directions removed.
    graph: NetworkGraph  # Remaining active links; installed nodes/switches/constraints stay declared, with no traffic deletion.


# Remove directions from a fresh graph, preserving rank references so unavailable demands fail visibly.
def apply_outage(graph: NetworkGraph, outage: NetworkOutage) -> OutageView:
    if not isinstance(graph, NetworkGraph) or not isinstance(outage, NetworkOutage):
        raise TypeError("expected NetworkGraph and NetworkOutage")
    known = (("disabled_link_ids", {link.link_id for link in graph.links}),
             ("disabled_node_ids", set(graph.node_ids)),
             ("disabled_switch_ids", {switch.switch_id for switch in graph.switches}))
    for name, identities in known:
        missing = set(getattr(outage, name)) - identities
        if missing:
            raise ValueError(f"{name}: unknown identities {sorted(missing)}")
    owners = port_owners(graph)
    disabled = set(outage.disabled_node_ids) | set(outage.disabled_switch_ids)
    explicit = set(outage.disabled_link_ids)
    removed = tuple(link.link_id for link in graph.links if link.link_id in explicit
                    or owners[link.src_port_id] in disabled or owners[link.dst_port_id] in disabled)
    removed_set = set(removed)
    active = replace(graph, links=tuple(link for link in graph.links if link.link_id not in removed_set))
    return OutageView(original_graph_hash=content_hash(graph), outage=outage, removed_link_ids=removed, graph=active)
