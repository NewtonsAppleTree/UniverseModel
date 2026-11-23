"""Explicit switch forwarding capabilities without queues or collective semantics."""

from dataclasses import dataclass
from typing import Literal

from contracts.hardware.network import finite_quantity, string_tuple, validate_identity


# Each permitted ingress-to-egress crossing charges its listed resources exactly once.
@dataclass(frozen=True, slots=True, kw_only=True)
class SwitchConnection:
    ingress_port_id: str  # Owned receiving port identity.
    egress_port_id: str  # Owned transmitting port identity; different from ingress.
    constraint_ids: tuple[str, ...]  # Nonempty switch-owned limits; payload or outgoing-frame work per crossing.

    # Freeze references and reject reflexive forwarding or duplicate capacity charges.
    def __post_init__(self) -> None:
        validate_identity("ingress_port_id", self.ingress_port_id)
        validate_identity("egress_port_id", self.egress_port_id)
        if self.ingress_port_id == self.egress_port_id:
            raise ValueError("switch connection cannot reflect to the same port")
        object.__setattr__(self, "constraint_ids", string_tuple("constraint_ids", self.constraint_ids, unique=True))


# A switch owns ports and forwarding relations; bandwidth definitions live once in the graph resource table.
@dataclass(frozen=True, slots=True, kw_only=True)
class SwitchParams:
    switch_id: str  # Unique fabric device owner identity, distinct from nodes and graph.
    port_ids: tuple[str, ...]  # Unique physical ports; sorted as an unordered resource set.
    connections: tuple[SwitchConnection, ...]  # Explicit allowed directed crossings, including shared limits.
    forwarding_latency_s: float  # Necessary per-crossing first-data processing latency [s]; no queue/startup time.
    source_ref: str  # Source/version for declared forwarding and latency assumptions.
    coverage: tuple[str, ...]  # Applicability and omitted switching/physical behavior.
    schema_version: Literal["network-switch/v1"] = "network-switch/v1"  # Static switch capability schema.

    # Validate port ownership and canonicalize connections without inventing an all-to-all crossbar.
    def __post_init__(self) -> None:
        for name in ("switch_id", "source_ref"):
            validate_identity(name, getattr(self, name))
        object.__setattr__(self, "port_ids", tuple(sorted(string_tuple("port_ids", self.port_ids, unique=True))))
        object.__setattr__(self, "coverage", string_tuple("coverage", self.coverage))
        object.__setattr__(self, "forwarding_latency_s", finite_quantity("forwarding_latency_s", self.forwarding_latency_s))
        if not isinstance(self.connections, (tuple, list)) or any(
                not isinstance(item, SwitchConnection) for item in self.connections):
            raise TypeError("connections: expected SwitchConnection sequence")
        connections = tuple(sorted(self.connections, key=lambda item: (item.ingress_port_id, item.egress_port_id)))
        pairs = tuple((item.ingress_port_id, item.egress_port_id) for item in connections)
        if len(set(pairs)) != len(pairs):
            raise ValueError("duplicate switch connection")
        if any(port not in self.port_ids for pair in pairs for port in pair):
            raise ValueError("switch connection references an unowned port")
        object.__setattr__(self, "connections", connections)
        if self.schema_version != "network-switch/v1":
            raise ValueError("unsupported switch schema_version")
