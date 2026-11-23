"""Versioned, immutable network boundary values; no NIC state or hardware imports."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal


# Identities and provenance strings must be nonempty and have no surrounding whitespace.
def validate_identity(name: str, value: str) -> None:
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError(f"{name}: expected a nonempty, trimmed string")


# Normalize a finite nonnegative/positive binary64 quantity; bool and numeric strings are invalid.
def finite_quantity(name: str, value: float, *, positive: bool = False) -> float:
    if type(value) not in (int, float):
        raise TypeError(f"{name}: expected int/float, excluding bool")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name}: exceeds binary64 range") from exc
    if not isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError(f"{name}: expected finite {'positive' if positive else 'nonnegative'} value")
    return result


# Byte counts and discrete extents remain exact integers; no implicit bool/float coercion.
def validate_count(name: str, value: int, *, minimum: int = 0) -> None:
    if type(value) is not int:
        raise TypeError(f"{name}: expected an integer, excluding bool")
    if value < minimum:
        raise ValueError(f"{name}: must be >= {minimum}")


# Own an immutable sequence of identities/statements and optionally reject duplicates or emptiness.
def string_tuple(name: str, values: tuple[str, ...], *, unique: bool = False,
                 allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise TypeError(f"{name}: expected a list/tuple of strings")
    result = tuple(values)
    if not result and not allow_empty:
        raise ValueError(f"{name}: must not be empty")
    for value in result:
        validate_identity(name, value)
    if unique and len(set(result)) != len(result):
        raise ValueError(f"{name}: duplicate identity")
    return result


# A unique resource supplies C [B/s] in a declared byte representation; references do not add capacity.
@dataclass(frozen=True, slots=True, kw_only=True)
class BandwidthConstraint:
    resource_id: str  # Unique shared service resource identity; not a logical group ID.
    owner_id: str  # Resource owner identity; a node, switch or fabric graph, validated by the consuming topology.
    capacity_Bps: float  # Positive service capacity C [B/s] in byte_basis, not raw bit/s.
    byte_basis: Literal["payload", "frame"]  # Logical payload or pre-PHY-encoding frame bytes.
    capacity_kind: Literal["declared_ceiling", "effective_service"]  # Model ceiling or conditional fitted service.
    source_ref: str  # Explicit source/version reference, including an identity for manual assumptions.
    coverage: tuple[str, ...]  # Immutable applicability and accounting boundary statements.
    frame_format_id: str | None = None  # Required for frame basis; binds packetization/overhead representation.
    schema_version: Literal["network-bandwidth/v1"] = "network-bandwidth/v1"  # Serialized resource semantics.

    # Freeze metadata and reject ambiguous byte bases, invalid capacities, or unsupported versions.
    def __post_init__(self) -> None:
        for name in ("resource_id", "owner_id", "source_ref"):
            validate_identity(name, getattr(self, name))
        object.__setattr__(self, "capacity_Bps", finite_quantity("capacity_Bps", self.capacity_Bps, positive=True))
        object.__setattr__(self, "coverage", string_tuple("coverage", self.coverage))
        if self.byte_basis not in ("payload", "frame"):
            raise ValueError("byte_basis: unsupported representation")
        if self.capacity_kind not in ("declared_ceiling", "effective_service"):
            raise ValueError("capacity_kind: unsupported service interpretation")
        if self.byte_basis == "frame":
            validate_identity("frame_format_id", self.frame_format_id)
        elif self.frame_format_id is not None:
            raise ValueError("frame_format_id: payload capacity must not declare a frame format")
        if self.schema_version != "network-bandwidth/v1":
            raise ValueError("unsupported network bandwidth schema_version")


# Read-only external NIC boundary; tx/rx reference owner-defined capacities and contain no queue state.
@dataclass(frozen=True, slots=True, kw_only=True)
class NetworkEndpointSpec:
    endpoint_id: str  # Unique network endpoint identity, independent of rank/group membership.
    node_id: str  # Owning systemmodel node identity; multiple endpoints may share one node.
    port_id: str  # Globally unique physical NIC port identity in one graph.
    tx_constraint_ids: tuple[str, ...]  # Required injection capacity references; duplicates are invalid.
    rx_constraint_ids: tuple[str, ...]  # Required receive capacity references; may overlap tx for shared duplex.
    source_ref: str  # Endpoint capability source/version, or explicit manual assumption identity.
    coverage: tuple[str, ...]  # Boundary conditions; does not grant device-memory visibility or RDMA semantics.
    schema_version: Literal["network-endpoint/v1"] = "network-endpoint/v1"  # Serialized endpoint semantics.

    # Require explicit tx/rx limits and freeze references; cross-object ownership is checked by the graph.
    def __post_init__(self) -> None:
        for name in ("endpoint_id", "node_id", "port_id", "source_ref"):
            validate_identity(name, getattr(self, name))
        for name in ("tx_constraint_ids", "rx_constraint_ids"):
            object.__setattr__(self, name, string_tuple(name, getattr(self, name), unique=True))
        object.__setattr__(self, "coverage", string_tuple("coverage", self.coverage))
        if self.schema_version != "network-endpoint/v1":
            raise ValueError("unsupported network endpoint schema_version")
