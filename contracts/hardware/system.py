"""Static node address/port contracts; standard library only, with no implicit access or coherence."""

from dataclasses import dataclass
from typing import Literal

from contracts.hardware.network import string_tuple, validate_count, validate_identity


AccessOperation = Literal['copy', 'read', 'write']  # Static permission query; read/write do not model request/response timing.


# Freeze a nonempty set of supported operations; protocol names never grant additional permissions.
def access_operations(values: tuple[AccessOperation, ...]) -> tuple[AccessOperation, ...]:
    values = string_tuple('operations',values,unique=True)
    if any(value not in ('copy','read','write') for value in values):
        raise ValueError('unsupported access operation')
    return tuple(sorted(values))


# An address domain names an integer address space, not physical memory capacity or residency.
@dataclass(frozen=True, slots=True, kw_only=True)
class AddressDomainSpec:
    domain_id: str  # Unique address-space identity in one topology.
    owner_id: str  # Resource instance owning this address namespace.
    address_bits: int  # Unsigned byte-address width [bit], 1..64; valid addresses are [0,2**address_bits).
    source_ref: str  # Source/profile or explicit modeling assumption.
    schema_version: Literal['system-address-domain/v1'] = 'system-address-domain/v1'  # Namespace only; no allocation/coherence claim.

    # Reject ambiguous widths and unknown schemas; ownership is checked by the composing topology.
    def __post_init__(self) -> None:
        for name in ('domain_id','owner_id','source_ref'):
            validate_identity(name,getattr(self,name))
        validate_count('address_bits',self.address_bits,minimum=1)
        if self.address_bits>64 or self.schema_version!='system-address-domain/v1':
            raise ValueError('unsupported address width/schema')

    # Check a nonempty half-open byte span; this proves address validity, not allocated backing or access permission.
    def validate_span(self, address: int, length_bytes: int) -> None:
        validate_count('address',address)
        validate_count('length_bytes',length_bytes,minimum=1)
        if address+length_bytes>1<<self.address_bits:
            raise ValueError('span exceeds address domain')


# Separate directed ports make attachment, terminal address ownership and permissions explicit.
@dataclass(frozen=True, slots=True, kw_only=True)
class SystemPortSpec:
    port_id: str  # Unique directed port identity; ingress/egress halves are separate declarations.
    owner_id: str  # Owning resource instance; does not imply forwarding between its ports.
    direction: Literal['ingress','egress']  # Direction of the modeled path relative to the owner.
    protocol: str  # Explicit protocol/profile identity; peers and forwarding ports must agree.
    operations: tuple[AccessOperation, ...]  # Allowed static operations; no implicit RDMA/P2P/coherence.
    source_ref: str  # Capability provenance or explicit assumption.
    domain_id: str | None = None  # Terminal address namespace; None denotes a transit-only port.
    constraint_ids: tuple[str, ...] = ()  # Shared resource references charged once at this port visit; no copied capacity.
    schema_version: Literal['system-port/v1'] = 'system-port/v1'  # Static direction/permission boundary.

    # Own immutable permissions/references; topology validates domain ownership, attachment and resource existence.
    def __post_init__(self) -> None:
        for name in ('port_id','owner_id','protocol','source_ref'):
            validate_identity(name,getattr(self,name))
        if self.domain_id is not None:
            validate_identity('domain_id',self.domain_id)
        if self.direction not in ('ingress','egress') or self.schema_version!='system-port/v1':
            raise ValueError('unsupported system port direction/schema')
        object.__setattr__(self,'operations',access_operations(self.operations))
        object.__setattr__(self,'constraint_ids',string_tuple('constraint_ids',self.constraint_ids,unique=True,allow_empty=True))
