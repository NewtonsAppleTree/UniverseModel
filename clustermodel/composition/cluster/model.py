"""Frozen cluster assembly and simultaneous fixed P2P demands."""

from dataclasses import dataclass
from typing import Literal

from contracts.hardware.network import string_tuple, validate_count, validate_identity
from clustermodel.composition.groups.model import CommunicationGroup, RankPlacement, validate_groups
from clustermodel.topology.graph import NetworkGraph, _freeze_records


# Compose physical boundaries and logical placements without duplicating node or switch resources.
@dataclass(frozen=True, slots=True, kw_only=True)
class ClusterSpec:
    cluster_id: str  # Assembly identity; graph remains the unique physical resource table.
    graph: NetworkGraph  # Validated NIC/fabric snapshots with explicit ownership.
    placements: tuple[RankPlacement, ...]  # Unique ranks referencing graph endpoints; empty is legal.
    groups: tuple[CommunicationGroup, ...] = ()  # Optional ordered logical communication groups.
    schema_version: Literal["cluster/v1"] = "cluster/v1"  # Static assembly schema identity.

    # Canonicalize resource references and reject dangling or conflicting ownership at assembly time.
    def __post_init__(self) -> None:
        validate_identity("cluster_id", self.cluster_id)
        object.__setattr__(self, "placements", _freeze_records("placements", self.placements, RankPlacement, "rank_id"))
        object.__setattr__(self, "groups", _freeze_records("groups", self.groups, CommunicationGroup, "group_id"))
        validate_groups(self.graph, self.placements, self.groups)
        if self.schema_version != "cluster/v1":
            raise ValueError("unsupported cluster schema_version")


# A positive message is a complete logical transfer; data metadata does not prove numerical correctness.
@dataclass(frozen=True, slots=True, kw_only=True)
class P2PMessage:
    message_id: str  # Unique demand identity within one analysis.
    src_rank: str  # Existing source logical rank.
    dst_rank: str  # Existing destination logical rank.
    payload_bytes: int  # Logical message length D [B]; positive, excludes control-only messages.
    data_id: str  # Application data identity retained for provenance.
    content_version: str  # Data content/version reference; does not assert availability or values.
    group_id: str | None = None  # If supplied, both ranks must be members of this group.
    explicit_link_ids: tuple[str, ...] | None = None  # Ordered fixed route; None invokes route_policy.
    route_policy: Literal["shortest-hop-lex/v1", "explicit/v1"] = "shortest-hop-lex/v1"  # Versioned selection rule.

    # Freeze route input and reject ambiguous selection or unsupported zero-payload communication semantics.
    def __post_init__(self) -> None:
        for name in ("message_id", "src_rank", "dst_rank", "data_id", "content_version"):
            validate_identity(name, getattr(self, name))
        validate_count("payload_bytes", self.payload_bytes, minimum=1)
        if self.group_id is not None:
            validate_identity("group_id", self.group_id)
        if self.explicit_link_ids is not None:
            object.__setattr__(self, "explicit_link_ids", string_tuple("explicit_link_ids", self.explicit_link_ids))
            if self.route_policy != "explicit/v1":
                raise ValueError("explicit route requires explicit/v1 policy")
        elif self.route_policy != "shortest-hop-lex/v1":
            raise ValueError("selected route requires shortest-hop-lex/v1 policy")


# A cut selects complete owners and one outgoing direction; it is not an optimization request.
@dataclass(frozen=True, slots=True, kw_only=True)
class CutRequest:
    cut_id: str  # Unique requested observation identity.
    node_ids: tuple[str, ...]  # Selected complete nodes S, possibly empty.
    switch_ids: tuple[str, ...] = ()  # Selected complete switches S, possibly empty.

    # Canonicalize owner sets; graph membership and byte compatibility are checked during analysis.
    def __post_init__(self) -> None:
        validate_identity("cut_id", self.cut_id)
        for name in ("node_ids", "switch_ids"):
            object.__setattr__(self, name, tuple(sorted(string_tuple(name, getattr(self, name), unique=True, allow_empty=True))))


# Every message is ready at the analysis origin; no temporal dependencies or arrival trace are silently projected.
@dataclass(frozen=True, slots=True, kw_only=True)
class TrafficInput:
    messages: tuple[P2PMessage, ...]  # Fixed P2P demands; an empty set is zero communication work.
    requested_cuts: tuple[CutRequest, ...] = ()  # Optional compatible directed owner cuts.
    schema_version: Literal["cluster-traffic/v1"] = "cluster-traffic/v1"  # Simultaneous-demand input semantics.

    # Message order has no scheduling meaning, so canonicalize IDs while retaining route/member order.
    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", _freeze_records("messages", self.messages, P2PMessage, "message_id"))
        object.__setattr__(self, "requested_cuts", _freeze_records("requested_cuts", self.requested_cuts, CutRequest, "cut_id"))
        if self.schema_version != "cluster-traffic/v1":
            raise ValueError("unsupported traffic schema_version")


# Validate logical demand references independently of path feasibility, profile domains or target execution.
def validate_traffic_references(cluster: ClusterSpec, traffic: TrafficInput) -> None:
    if not isinstance(cluster, ClusterSpec) or not isinstance(traffic, TrafficInput):
        raise TypeError("expected ClusterSpec and TrafficInput")
    ranks = {placement.rank_id for placement in cluster.placements}
    groups = {group.group_id: group for group in cluster.groups}
    for message in traffic.messages:
        if message.src_rank not in ranks or message.dst_rank not in ranks:
            raise ValueError(f"message {message.message_id}: unknown rank")
        if message.group_id is not None:
            if message.group_id not in groups:
                raise ValueError(f"message {message.message_id}: unknown group")
            if not {message.src_rank, message.dst_rank}.issubset(groups[message.group_id].rank_ids):
                raise ValueError(f"message {message.message_id}: rank is not a group member")
