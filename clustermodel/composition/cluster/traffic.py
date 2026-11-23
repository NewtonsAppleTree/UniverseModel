"""Logical demand inventories, independent of routing, timing and physical service feasibility."""

from dataclasses import dataclass

from clustermodel.composition.cluster.model import ClusterSpec, TrafficInput, validate_traffic_references


# One rank/node/endpoint row describes logical sends and receives; it does not own additional bandwidth.
@dataclass(frozen=True, slots=True, kw_only=True)
class ParticipantTraffic:
    participant_id: str  # Identity within the enclosing rank, node or endpoint table.
    sent_payload_bytes: int  # Sum of original outgoing logical payloads [B], without hop replication.
    received_payload_bytes: int  # Sum of original incoming logical payloads [B].
    sent_message_count: int  # Number of outgoing P2P demands [message].
    received_message_count: int  # Number of incoming P2P demands [message].


# Each message contributes once to its source-node/destination-node pair, including explicit local demands.
@dataclass(frozen=True, slots=True, kw_only=True)
class NodePairTraffic:
    src_node_id: str  # Source node identity derived from rank placement.
    dst_node_id: str  # Destination node identity; may equal source in this logical description.
    payload_bytes: int  # Sum of original message lengths for this ordered pair [B].
    message_count: int  # Number of demands for this pair [message].


# Group attribution follows the declared message group only; overlapping membership never replicates work.
@dataclass(frozen=True, slots=True, kw_only=True)
class GroupTraffic:
    group_id: str | None  # Explicit message group; None is the ungrouped bucket.
    payload_bytes: int  # Logical payload assigned to this group [B].
    message_count: int  # Demands explicitly assigned to this group [message].


# Describe logical communication across every placement scope without claiming any route is feasible.
@dataclass(frozen=True, slots=True, kw_only=True)
class TrafficDescription:
    message_count: int  # Number of fixed positive-length P2P demands [message].
    logical_payload_bytes: int  # Sum of original P2P sizes [B].
    local_payload_bytes: int  # Same-node logical work [B]; its service still requires a systemmodel summary.
    inter_node_payload_bytes: int  # Cross-node logical work [B] = total minus local.
    per_rank: tuple[ParticipantTraffic, ...]  # Every declared rank, including idle participants.
    per_node: tuple[ParticipantTraffic, ...]  # Every installed endpoint-owning node, with shared ranks aggregated.
    per_endpoint: tuple[ParticipantTraffic, ...]  # Every installed endpoint, with shared ranks aggregated.
    per_group: tuple[GroupTraffic, ...]  # All declared groups plus the ungrouped bucket; no membership expansion.
    node_matrix: tuple[NodePairTraffic, ...]  # Sparse directed matrix containing only positive demand pairs.


# Freeze participant counters in identity order; entries retain exact integer bytes and counts.
def _rows(counters: dict[str, list[int]]) -> tuple[ParticipantTraffic, ...]:
    return tuple(ParticipantTraffic(participant_id=identity, sent_payload_bytes=values[0], received_payload_bytes=values[1],
                                    sent_message_count=values[2], received_message_count=values[3])
                 for identity, values in sorted(counters.items()))


# Describe valid references before route analysis, retaining local/unreachable demand rather than dropping it.
def describe_traffic(cluster: ClusterSpec, traffic: TrafficInput) -> TrafficDescription:
    validate_traffic_references(cluster, traffic)
    placements = {placement.rank_id: placement for placement in cluster.placements}
    rank_counts = {identity: [0, 0, 0, 0] for identity in placements}
    node_counts = {identity: [0, 0, 0, 0] for identity in cluster.graph.node_ids}
    endpoint_counts = {endpoint.endpoint_id: [0, 0, 0, 0] for endpoint in cluster.graph.endpoints}
    group_counts = {group.group_id: [0, 0] for group in cluster.groups}
    group_counts[None] = [0, 0]
    pairs, local_bytes = {}, 0
    for message in traffic.messages:
        src, dst = placements[message.src_rank], placements[message.dst_rank]
        for counters, source, destination in ((rank_counts, src.rank_id, dst.rank_id),
                                               (node_counts, src.node_id, dst.node_id),
                                               (endpoint_counts, src.endpoint_id, dst.endpoint_id)):
            counters[source][0] += message.payload_bytes
            counters[source][2] += 1
            counters[destination][1] += message.payload_bytes
            counters[destination][3] += 1
        pair = pairs.setdefault((src.node_id, dst.node_id), [0, 0])
        pair[0] += message.payload_bytes
        pair[1] += 1
        group_counts[message.group_id][0] += message.payload_bytes
        group_counts[message.group_id][1] += 1
        if src.node_id == dst.node_id:
            local_bytes += message.payload_bytes
    total = sum(message.payload_bytes for message in traffic.messages)
    return TrafficDescription(message_count=len(traffic.messages), logical_payload_bytes=total,
                              local_payload_bytes=local_bytes, inter_node_payload_bytes=total - local_bytes,
                              per_rank=_rows(rank_counts), per_node=_rows(node_counts), per_endpoint=_rows(endpoint_counts),
                              per_group=tuple(GroupTraffic(group_id=identity, payload_bytes=group_counts[identity][0],
                                                            message_count=group_counts[identity][1])
                                              for identity in tuple(sorted(group.group_id for group in cluster.groups)) + (None,)),
                              node_matrix=tuple(NodePairTraffic(src_node_id=src, dst_node_id=dst,
                                                                 payload_bytes=values[0], message_count=values[1])
                                                for (src, dst), values in sorted(pairs.items())))
