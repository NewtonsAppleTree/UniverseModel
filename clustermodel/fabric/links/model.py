"""Independent directional link analysis with explicit frame/payload accounting."""

from dataclasses import dataclass
from typing import Literal

from contracts.hardware.network import finite_quantity, string_tuple, validate_count, validate_identity
from contracts.versions.json_codec import content_hash


# A directed link selects exactly one rate representation; physical assumptions are always explicit.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinkParams:
    link_id: str  # Unique directed physical channel identity; reverse direction is another link.
    src_port_id: str  # Source port identity; graph construction validates ownership and attachment.
    dst_port_id: str  # Destination port identity; cannot equal src_port_id.
    rate_basis: Literal["raw_line", "effective_payload"]  # Mutually exclusive rate/profile interpretation.
    startup_s: float  # Per-message isolated startup latency [s]; nonnegative, excludes software launch.
    propagation_s: float  # One-way propagation latency [s]; nonnegative, no queue delay.
    capacity_kind: Literal["declared_ceiling", "effective_service"]  # Declared model ceiling or fitted service rate.
    source_ref: str  # Explicit source/profile version or manual assumption identity.
    coverage: tuple[str, ...]  # Immutable profile applicability and omitted mechanisms.
    line_rate_bps: float | None = None  # Raw branch: aggregated line rate R [bit/s], positive.
    coding_efficiency: float | None = None  # Raw branch: remaining PHY efficiency eta in (0,1].
    max_payload_bytes: int | None = None  # Raw branch: maximum per-packet payload M [B], positive integer.
    header_bytes: int | None = None  # Raw branch: header h [B/packet], nonnegative integer.
    trailer_bytes: int | None = None  # Raw branch: trailer t [B/packet], nonnegative integer.
    alignment_bytes: int | None = None  # Raw branch: entire frame alignment a [B], positive integer.
    payload_bandwidth_Bps: float | None = None  # Effective branch: already adjusted payload capacity [B/s].
    profile_min_payload_bytes: int = 1  # Smallest supported nonempty message [B]; zero is a no-op query.
    profile_max_payload_bytes: int | None = None  # Largest supported message [B]; None declares no upper limit.
    shared_constraint_ids: tuple[str, ...] = ()  # Additional fabric-owned resources, e.g. half-duplex medium.
    schema_version: Literal["network-link/v1"] = "network-link/v1"  # Link/profile accounting semantics.

    # Reject mixed rate branches, impossible identities, invalid units/ranges and nonfinite derived capacity.
    def __post_init__(self) -> None:
        for name in ("link_id", "src_port_id", "dst_port_id", "source_ref"):
            validate_identity(name, getattr(self, name))
        if self.src_port_id == self.dst_port_id:
            raise ValueError("link endpoints: a physical link cannot be a self-loop")
        for name in ("startup_s", "propagation_s"):
            object.__setattr__(self, name, finite_quantity(name, getattr(self, name)))
        finite_quantity("isolated fixed latency", self.startup_s + self.propagation_s)
        object.__setattr__(self, "coverage", string_tuple("coverage", self.coverage))
        object.__setattr__(self, "shared_constraint_ids", string_tuple(
            "shared_constraint_ids", self.shared_constraint_ids, unique=True, allow_empty=True))
        validate_count("profile_min_payload_bytes", self.profile_min_payload_bytes, minimum=1)
        if self.profile_max_payload_bytes is not None:
            validate_count("profile_max_payload_bytes", self.profile_max_payload_bytes,
                           minimum=self.profile_min_payload_bytes)
        raw_fields = ("line_rate_bps", "coding_efficiency", "max_payload_bytes", "header_bytes",
                      "trailer_bytes", "alignment_bytes")
        if self.rate_basis == "raw_line":
            if self.payload_bandwidth_Bps is not None or any(getattr(self, name) is None for name in raw_fields):
                raise ValueError("raw_line requires all raw fields and forbids payload_bandwidth_Bps")
            for name in ("line_rate_bps", "coding_efficiency"):
                object.__setattr__(self, name, finite_quantity(name, getattr(self, name), positive=True))
            if self.coding_efficiency > 1:
                raise ValueError("coding_efficiency must be <= 1")
            for name in ("max_payload_bytes", "alignment_bytes"):
                validate_count(name, getattr(self, name), minimum=1)
            for name in ("header_bytes", "trailer_bytes"):
                validate_count(name, getattr(self, name))
        elif self.rate_basis == "effective_payload":
            if any(getattr(self, name) is not None for name in raw_fields):
                raise ValueError("effective_payload forbids raw line/packet fields; do not charge overhead twice")
            object.__setattr__(self, "payload_bandwidth_Bps", finite_quantity(
                "payload_bandwidth_Bps", self.payload_bandwidth_Bps, positive=True))
        else:
            raise ValueError("unsupported rate_basis")
        if self.capacity_kind not in ("declared_ceiling", "effective_service"):
            raise ValueError("unsupported capacity_kind")
        if self.schema_version != "network-link/v1":
            raise ValueError("unsupported network link schema_version")
        finite_quantity("service_capacity_Bps", self.service_capacity_Bps, positive=True)

    # Capacity C [B/s] uses pre-PHY frame bytes for raw profiles and payload bytes for effective profiles.
    @property
    def service_capacity_Bps(self) -> float:
        if self.rate_basis == "raw_line":
            return (self.line_rate_bps / 8) * self.coding_efficiency
        return self.payload_bandwidth_Bps

    # Bind service quantities to their accounting representation, preventing wire/payload mixing.
    @property
    def service_byte_basis(self) -> str:
        return "frame" if self.rate_basis == "raw_line" else "payload"

    # Frame identity depends on packetization and padding, not line speed or PHY coding efficiency.
    @property
    def frame_format_id(self) -> str | None:
        if self.rate_basis == "effective_payload":
            return None
        return content_hash({"schema": "network-frame/v1", "max_payload_bytes": self.max_payload_bytes,
                             "header_bytes": self.header_bytes, "trailer_bytes": self.trailer_bytes,
                             "alignment_bytes": self.alignment_bytes})


# Immutable query result separates actual service work from unknown framing and isolated latency.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinkEstimate:
    payload_bytes: int  # Original logical message size D [B]; zero means no work.
    packet_count: int | None  # Number of frames; unknown for nonempty effective-payload profiles.
    wire_bytes: int | None  # Pre-PHY frame bytes W [B], including headers/trailers/padding; may be unknown.
    wire_unknown_reason: str | None  # Explanation when frame count/wire bytes cannot be derived.
    service_bytes: int  # Resource service demand [B] in service_byte_basis.
    service_byte_basis: str  # Frame or payload representation, matching the denominator capacity.
    serialization_s: float  # Isolated service duration Q/C [s]; excludes startup/propagation.
    isolated_time_s: float  # Startup + propagation + serialization [s] for D>0; zero for no work.

    # An empty arithmetic query is not a zero-payload control packet or a synchronization operation.
    @property
    def empty(self) -> bool:
        return self.payload_bytes == 0


# Align one complete frame using exact integer arithmetic; no packet list is allocated.
def _aligned_frame(payload_bytes: int, params: LinkParams) -> int:
    total = payload_bytes + params.header_bytes + params.trailer_bytes
    return ((total + params.alignment_bytes - 1) // params.alignment_bytes) * params.alignment_bytes


# Estimate one isolated message in O(1) packet-count space; T=L_start+L_prop+Q/C, never a queue simulation.
def estimate_link(params: LinkParams, payload_bytes: int) -> LinkEstimate:
    if not isinstance(params, LinkParams):
        raise TypeError("params: expected LinkParams")
    validate_count("payload_bytes", payload_bytes)
    if payload_bytes == 0:
        return LinkEstimate(payload_bytes=0, packet_count=0, wire_bytes=0, wire_unknown_reason=None,
                            service_bytes=0, service_byte_basis=params.service_byte_basis,
                            serialization_s=0.0, isolated_time_s=0.0)
    if payload_bytes < params.profile_min_payload_bytes or (
            params.profile_max_payload_bytes is not None and payload_bytes > params.profile_max_payload_bytes):
        raise ValueError("out_of_domain: payload_bytes is outside the declared link profile")
    if params.rate_basis == "raw_line":
        full, tail = divmod(payload_bytes, params.max_payload_bytes)
        packets = full + int(tail != 0)
        wire = full * _aligned_frame(params.max_payload_bytes, params)
        if tail:
            wire += _aligned_frame(tail, params)
        service = wire
        reason = None
    else:
        packets, wire = None, None
        service = payload_bytes
        reason = "effective_payload profile does not specify packetization or pre-PHY frame bytes"
    try:
        serialization = finite_quantity("serialization_s", service / params.service_capacity_Bps, positive=True)
        elapsed = finite_quantity("isolated_time_s", params.startup_s + params.propagation_s + serialization,
                                  positive=True)
    except OverflowError as exc:
        raise ValueError("link estimate exceeds finite binary64 time range") from exc
    return LinkEstimate(payload_bytes=payload_bytes, packet_count=packets, wire_bytes=wire,
                        wire_unknown_reason=reason, service_bytes=service,
                        service_byte_basis=params.service_byte_basis,
                        serialization_s=serialization, isolated_time_s=elapsed)
