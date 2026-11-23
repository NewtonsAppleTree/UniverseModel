"""Ordered logical groups and rank placement references, independent of collective algorithms."""

from dataclasses import dataclass

from contracts.hardware.network import string_tuple, validate_identity
from clustermodel.topology.graph import NetworkGraph, _freeze_records


# A rank references an existing node/NIC boundary; sharing this reference never creates bandwidth.
@dataclass(frozen=True, slots=True, kw_only=True)
class RankPlacement:
    rank_id: str  # Unique logical participant identity; no implicit numeric ordering.
    node_id: str  # Owning node identity, checked against the endpoint snapshot.
    endpoint_id: str  # Existing external NIC boundary; may be shared by many ranks.

    # Check lexical identities here and defer boundary existence to validate_groups.
    def __post_init__(self) -> None:
        for name in ("rank_id", "node_id", "endpoint_id"):
            validate_identity(name, getattr(self, name))


# Member order belongs to the application; overlap between distinct groups is permitted.
@dataclass(frozen=True, slots=True, kw_only=True)
class CommunicationGroup:
    group_id: str  # Logical group identity; not a physical resource or algorithm choice.
    rank_ids: tuple[str, ...]  # Nonempty ordered unique members; all must have placements.

    # Own the member sequence without sorting or inferring collective work.
    def __post_init__(self) -> None:
        validate_identity("group_id", self.group_id)
        object.__setattr__(self, "rank_ids", string_tuple("rank_ids", self.rank_ids, unique=True))


# Independently verify placement ownership and ordered group references against an existing graph.
def validate_groups(graph: NetworkGraph, placements: tuple[RankPlacement, ...],
                    groups: tuple[CommunicationGroup, ...]) -> None:
    if not isinstance(graph, NetworkGraph):
        raise TypeError("graph: expected NetworkGraph")
    placements = _freeze_records("placements", placements, RankPlacement, "rank_id")
    groups = _freeze_records("groups", groups, CommunicationGroup, "group_id")
    endpoints = {endpoint.endpoint_id: endpoint for endpoint in graph.endpoints}
    ranks = {placement.rank_id for placement in placements}
    for placement in placements:
        if placement.endpoint_id not in endpoints:
            raise ValueError(f"rank {placement.rank_id}: unknown endpoint")
        if endpoints[placement.endpoint_id].node_id != placement.node_id:
            raise ValueError(f"rank {placement.rank_id}: endpoint belongs to a different node")
    for group in groups:
        if not set(group.rank_ids).issubset(ranks):
            raise ValueError(f"group {group.group_id}: unknown rank")
