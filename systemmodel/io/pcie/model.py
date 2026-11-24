"""Conventional PCIe posted-write accounting; explicit assumed framing and streaming coding efficiency."""

from dataclasses import dataclass
from fractions import Fraction

from chipmodel.common import finite_fraction
from contracts.hardware.network import finite_quantity, string_tuple, validate_count, validate_identity


# One conventional TLP format binds every modeled path; this excludes FLIT mode, PAM4 and read completions.
@dataclass(frozen=True, slots=True, kw_only=True)
class PcieProfile:
    profile_id: str  # Framing/coding identity used by frame-basis shared constraints.
    protocol: str  # Exact SystemPortSpec protocol; labels alone grant no permissions.
    max_payload_bytes: int  # Negotiated MPS [B]: 128/256/512/1024/2048/4096, including DWORD payload padding.
    tlp_overhead_bytes: int  # Assumed complete header/sequence/CRC/framing bytes per TLP [B], positive.
    coding_data_bits: int  # Useful bits per coding block [bit], e.g. 128; stream-average ceiling only.
    coding_wire_bits: int  # Encoded bits per block [bit], e.g. 130; at least coding_data_bits.
    source_ref: str  # Source for protocol assumptions, not an implicit PCI-SIG compliance assertion.
    coverage: tuple[str, ...]  # Declared accounting scope and omitted control/physical traffic.

    # Conventional non-FLIT MPS and explicit coding/framing prevent accidental reuse across incompatible generations.
    def __post_init__(self) -> None:
        for name in ('profile_id','protocol','source_ref'):
            validate_identity(name,getattr(self,name))
        for name in ('max_payload_bytes','tlp_overhead_bytes','coding_data_bits','coding_wire_bits'):
            validate_count(name,getattr(self,name),minimum=1)
        if self.max_payload_bytes not in (128,256,512,1024,2048,4096) or self.coding_wire_bits<self.coding_data_bits:
            raise ValueError('invalid conventional MPS/coding ratio')
        object.__setattr__(self,'coverage',string_tuple('coverage',self.coverage))


# A unique physical service can constrain several directed links, e.g. an explicitly shared half-duplex resource.
@dataclass(frozen=True, slots=True, kw_only=True)
class PcieService:
    resource_id: str  # Unique modeled service resource in the topology ownership tree.
    link_ids: tuple[str, ...]  # Directed wires consuming this same capacity; references do not create more lanes.
    lane_count: int  # Positive NRZ lane count [lane] in the explicitly modeled service direction/group.
    lane_rate_transfers_s: float  # Raw NRZ transfer rate per lane [transfer/s]; one raw bit per transfer.
    source_ref: str  # Lane/rate/shared-direction assumption or device profile provenance.

    # Freeze wire attachments and validate a finite positive raw line rate.
    def __post_init__(self) -> None:
        for name in ('resource_id','source_ref'):
            validate_identity(name,getattr(self,name))
        validate_count('lane_count',self.lane_count,minimum=1)
        object.__setattr__(self,'link_ids',tuple(sorted(string_tuple('link_ids',self.link_ids,unique=True))))
        object.__setattr__(self,'lane_rate_transfers_s',finite_quantity('lane_rate_transfers_s',self.lane_rate_transfers_s,positive=True))

    # Frame-byte ceiling = lanes * NRZ bit rate * data_bits/wire_bits / 8; packet overhead is counted in demand.
    def frame_capacity_Bps(self, profile: PcieProfile) -> float:
        if not isinstance(profile,PcieProfile):
            raise TypeError('expected PcieProfile')
        rate = Fraction(self.lane_count)*Fraction(self.lane_rate_transfers_s)*profile.coding_data_bits/(8*profile.coding_wire_bits)
        value = finite_fraction('PCIe frame-byte rate',rate)
        return finite_quantity('PCIe frame-byte rate',value,positive=True)


# Exact TLP byte accounting separates useful bytes, DWORD padding and fixed per-packet protocol bytes.
@dataclass(frozen=True, slots=True)
class PcieTraffic:
    payload_bytes: int  # Useful copied bytes [B], positive.
    packet_count: int  # Conventional memory-write TLP count [packet].
    padded_payload_bytes: int  # Sum of DWORD-rounded TLP payload fields [B].
    padding_bytes: int  # padded_payload_bytes - payload_bytes [B].
    protocol_bytes: int  # packet_count * tlp_overhead_bytes [B].
    frame_bytes: int  # padded_payload_bytes + protocol_bytes [B], before physical coding.


# Split writes at MPS and 4 KiB boundaries, respecting first/last DWORD byte enables; bulk full pages in O(1).
def packetize_write(profile: PcieProfile, address: int, payload_bytes: int) -> PcieTraffic:
    if not isinstance(profile,PcieProfile):
        raise TypeError('expected PcieProfile')
    validate_count('address',address)
    validate_count('payload_bytes',payload_bytes,minimum=1)
    if address+payload_bytes>1<<64:
        raise ValueError('posted write exceeds 64-bit address range')
    remaining,current,packets,padded = payload_bytes,address,0,0
    while remaining:
        if current%4096==0 and remaining>=4096:
            pages = remaining//4096
            packets += pages*(4096//profile.max_payload_bytes)
            padded += pages*4096
            current += pages*4096
            remaining -= pages*4096
        else:
            size = min(remaining,profile.max_payload_bytes-current%4,4096-current%4096)
            padded += ((current%4+size+3)//4)*4
            packets += 1
            current += size
            remaining -= size
    protocol = packets*profile.tlp_overhead_bytes
    return PcieTraffic(payload_bytes,packets,padded,padded-payload_bytes,protocol,padded+protocol)
