"""Explicit CXL capabilities and flat address windows; line traffic is not a coherence/packet simulator."""

from dataclasses import dataclass
from typing import Literal

from chipmodel.composition.die.topology import ancestry
from contracts.hardware.network import string_tuple, validate_count, validate_identity
from contracts.versions.json_codec import content_hash
from systemmodel.memory.access import MemoryAccessAnalysis, MemoryAccessRequest, analyze_access, validate_access
from systemmodel.memory.model import MemoryPlan, MemorySystem
from systemmodel.topology.graph import freeze_inventory
from systemmodel.topology.query import SystemPath


# A line-granular memory-access abstraction declares its flat decoder granule instead of claiming register-level HDM fidelity.
@dataclass(frozen=True, slots=True, kw_only=True)
class CxlMemProfile:
    profile_id: str  # Sourced abstraction identity, independent of PCIe TLP framing.
    mem_protocol: str  # Exact protocol label on CXL.mem request ports/wires.
    line_bytes: int  # Power-of-two memory transaction quantum [B]; conventional examples use 64 B.
    decoder_granule_bytes: int  # Positive flat-window alignment/size granule [B], multiple of line_bytes.
    source_ref: str  # Abstraction/parameter provenance, not an implicit CXL revision certification.
    coverage: tuple[str, ...]  # Explicit capabilities and omitted protocol/coherence/timing mechanisms.

    # Require aligned whole-line decoder windows; tiny synthetic granules must remain explicit assumptions.
    def __post_init__(self) -> None:
        for name in ('profile_id','mem_protocol','source_ref'):
            validate_identity(name,getattr(self,name))
        for name in ('line_bytes','decoder_granule_bytes'):
            validate_count(name,getattr(self,name),minimum=1)
        if self.line_bytes & (self.line_bytes-1) or self.decoder_granule_bytes%self.line_bytes:
            raise ValueError('CXL line must be power-of-two and decoder granule must contain whole lines')
        object.__setattr__(self,'coverage',string_tuple('coverage',self.coverage))


# Enabled protocols are negotiated declarations; device type only restricts which modes can be enabled.
@dataclass(frozen=True, slots=True, kw_only=True)
class CxlAttachment:
    attachment_id: str  # One explicit host/device attachment identity.
    device_id: str  # Modeled device owning the memory-side terminal and backing subtree.
    device_type: Literal['type1','type2','type3']  # Type 1: io/cache; type 2: io/cache/mem; type 3: io/mem.
    host_port_id: str  # Host address-terminal egress for memory requests.
    device_port_id: str  # Device address-terminal ingress serving the decoded memory view.
    enabled_protocols: tuple[Literal['io','cache','mem'], ...]  # Explicit enabled modes; io is required, type alone grants nothing.
    source_ref: str  # Capability/negotiation/attachment source or manual assumption.

    # Reject impossible type/mode combinations without interpreting enabled cache as implemented coherence behavior.
    def __post_init__(self) -> None:
        for name in ('attachment_id','device_id','host_port_id','device_port_id','source_ref'):
            validate_identity(name,getattr(self,name))
        allowed = {'type1':{'io','cache'},'type2':{'io','cache','mem'},'type3':{'io','mem'}}
        modes = string_tuple('enabled_protocols',self.enabled_protocols,unique=True)
        if self.device_type not in allowed or 'io' not in modes or not set(modes)<=allowed[self.device_type]:
            raise ValueError('invalid CXL device type/enabled protocol combination')
        object.__setattr__(self,'enabled_protocols',tuple(sorted(modes)))


# A flat decoder maps one noninterleaved host-visible aperture to one contiguous physical backing interval.
@dataclass(frozen=True, slots=True, kw_only=True)
class CxlWindow:
    window_id: str  # Unique decoder aperture identity.
    attachment_id: str  # Existing host/device attachment; no implicit multi-host sharing.
    backing_id: str  # Existing physical storage under the attached device.
    base_address: int  # Host-visible aperture start in the device terminal address view [B].
    backing_offset_bytes: int  # First decoded physical backing byte [B].
    length_bytes: int  # Positive aperture extent [B]; does not create additional capacity.
    source_ref: str  # Mapping source, excluding unmodeled HDM register programming/interleaving.

    # Validate exact byte spans locally; resource, alignment and alias collisions are checked by CxlMemorySystem.
    def __post_init__(self) -> None:
        for name in ('window_id','attachment_id','backing_id','source_ref'):
            validate_identity(name,getattr(self,name))
        for name in ('base_address','backing_offset_bytes'):
            validate_count(name,getattr(self,name))
        validate_count('length_bytes',self.length_bytes,minimum=1)


# CXL capability/mapping declarations refer to the same finite backing inventory used by independent memory placement.
@dataclass(frozen=True, slots=True, kw_only=True)
class CxlMemorySystem:
    memory: MemorySystem  # Authoritative node/physical capacity and NUMA identity.
    profile: CxlMemProfile  # Flat decoder and memory transaction abstraction.
    attachments: tuple[CxlAttachment, ...]  # Explicit endpoint modes, independent of path reachability.
    windows: tuple[CxlWindow, ...]  # Nonoverlapping host apertures and physical decoder ranges.
    source_ref: str  # Whole CXL assembly provenance.

    # Validate device ownership, window capacity/alignment and host-global aperture uniqueness without adding capacity.
    def __post_init__(self) -> None:
        if not isinstance(self.memory,MemorySystem) or not isinstance(self.profile,CxlMemProfile):
            raise TypeError('expected MemorySystem and CxlMemProfile')
        validate_identity('source_ref',self.source_ref)
        object.__setattr__(self,'attachments',freeze_inventory('attachments',self.attachments,CxlAttachment,'attachment_id'))
        object.__setattr__(self,'windows',freeze_inventory('windows',self.windows,CxlWindow,'window_id'))
        topology = self.memory.node.topology
        ports = {p.port_id:p for p in topology.ports}
        domains = {d.domain_id:d for d in topology.domains}
        backings = {b.resource_id:b for b in self.memory.backings}
        paths = ancestry(topology.resources)
        attachments = {a.attachment_id:a for a in self.attachments}
        for attachment in self.attachments:
            host,device = ports.get(attachment.host_port_id),ports.get(attachment.device_port_id)
            if (host is None or device is None or host.direction!='egress' or device.direction!='ingress'
                    or host.domain_id is None or device.domain_id is None or host.owner_id==device.owner_id
                    or device.owner_id!=attachment.device_id or host.protocol!=self.profile.mem_protocol or device.protocol!=self.profile.mem_protocol):
                raise ValueError('invalid CXL memory attachment ownership/terminal/protocol')
        ranges = {}
        for window in self.windows:
            attachment,backing = attachments.get(window.attachment_id),backings.get(window.backing_id)
            if attachment is None or backing is None or attachment.device_id not in paths[backing.resource_id]:
                raise ValueError('CXL window references unknown or foreign backing/attachment')
            if attachment.device_type=='type1' or attachment.device_port_id not in backing.access_port_ids:
                raise ValueError('CXL decoder requires a memory-capable device backing port')
            granule = self.profile.decoder_granule_bytes
            if any(value%granule for value in (window.base_address,window.backing_offset_bytes,window.length_bytes)) or backing.allocation_granule_bytes%self.profile.line_bytes:
                raise ValueError('CXL decoder/backing reservation alignment incompatible with memory line profile')
            if window.backing_offset_bytes+window.length_bytes>backing.capacity_bytes:
                raise ValueError('CXL decoder exceeds physical backing capacity')
            host_domain = ports[attachment.host_port_id].domain_id
            domains[host_domain].validate_span(window.base_address,window.length_bytes)
            domains[ports[attachment.device_port_id].domain_id].validate_span(window.base_address,window.length_bytes)
            for key,start in ((('host',host_domain),window.base_address),(('backing',backing.resource_id),window.backing_offset_bytes)):
                ranges.setdefault(key,[]).append((start,start+window.length_bytes))
        for intervals in ranges.values():
            ordered = sorted(intervals)
            if any(first[1]>second[0] for first,second in zip(ordered,ordered[1:])):
                raise ValueError('overlapping host apertures or physical CXL decoder windows')

    # Include all endpoint modes, mapping granules, decoder intervals and source in the immutable CXL identity.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)


# A memory request explicitly selects its decoded window and requested protocol semantics.
@dataclass(frozen=True, slots=True, kw_only=True)
class CxlAccessRequest:
    window_id: str  # Existing flat decoder window.
    access: MemoryAccessRequest  # Host source, region/address, operation, liveness phase and requested route.
    protocol: Literal['io','cache','mem'] = 'mem'  # Only mem provides this model's host memory-access behavior.

    # Preserve unsupported-but-well-formed protocol requests as query failures rather than silently upgrading them.
    def __post_init__(self) -> None:
        validate_identity('window_id',self.window_id)
        if not isinstance(self.access,MemoryAccessRequest) or self.protocol not in ('io','cache','mem'):
            raise ValueError('invalid CXL access request')


# Line traffic is separate from unmodeled CXL packet/credit/coherence costs and complete target service time.
@dataclass(frozen=True, slots=True)
class CxlAccessAnalysis:
    system_identity: str  # Full CXL capability/decoder/source identity.
    window_id: str  # Checked flat decoder identity.
    access: MemoryAccessAnalysis  # Validated placement, physical address, path and NUMA label.
    line_count: int  # Number of covered memory-line transactions [line].
    data_bytes: int  # line_count * line_bytes [B]; read response or aligned full-line write data.
    extra_data_bytes: int  # data_bytes - useful requested bytes [B], not PCIe padding or header.
    unknown_costs: tuple[str, ...]  # Coherence execution, protocol framing/service and physical cost remain unknown.


# Gate semantics and flat decoding before reporting native CXL line traffic; saved path validation performs no search.
def _analyze(system: CxlMemorySystem, plan: MemoryPlan, request: CxlAccessRequest, saved_path: SystemPath | None) -> CxlAccessAnalysis:
    if not isinstance(system,CxlMemorySystem) or not isinstance(request,CxlAccessRequest):
        raise TypeError('expected CxlMemorySystem and CxlAccessRequest')
    window = next((w for w in system.windows if w.window_id==request.window_id),None)
    if window is None:
        raise ValueError('unknown CXL decoder window')
    attachment = next(a for a in system.attachments if a.attachment_id==window.attachment_id)
    if request.protocol!='mem' or 'mem' not in attachment.enabled_protocols:
        raise ValueError('host memory access requires explicitly enabled CXL.mem; io/cache do not grant it')
    query = request.access
    if query.source_port_id!=attachment.host_port_id or query.address<window.base_address or query.address+query.length_bytes>window.base_address+window.length_bytes:
        raise ValueError('CXL request host/address outside selected attachment/window')
    if saved_path is None:
        access = analyze_access(system.memory,plan,query)
    else:
        if not isinstance(saved_path,SystemPath):
            raise TypeError('expected saved SystemPath')
        access = validate_access(system.memory,plan,query,saved_path.link_ids)
        if access.path!=saved_path:
            raise ValueError('saved CXL path observations disagree')
    span = access.span
    expected_offset = window.backing_offset_bytes+query.address-window.base_address
    if span.access_port_id!=attachment.device_port_id or span.backing_id!=window.backing_id or span.physical_offset_bytes!=expected_offset:
        raise ValueError('memory view disagrees with CXL flat decoder mapping')
    ports = {p.port_id:p for p in system.memory.node.topology.ports}
    allocations = {a.allocation_id:a for a in plan.allocations}
    host_domain = ports[attachment.host_port_id].domain_id
    for region in plan.regions:
        allocation = allocations[region.allocation_id]
        if (ports[region.access_port_id].domain_id==host_domain and allocation.begin_phase<=query.phase<allocation.end_phase
                and region.base_address<window.base_address+window.length_bytes and window.base_address<region.base_address+region.length_bytes):
            raise ValueError('host-local address view collides with the selected CXL host aperture')
    line = system.profile.line_bytes
    if query.operation=='write' and (query.address%line or query.length_bytes%line):
        raise ValueError('this CXL abstraction requires aligned full-line writes; masked/RMW writes unmodeled')
    count = (query.address%line+query.length_bytes+line-1)//line
    return CxlAccessAnalysis(system.identity_hash,window.window_id,access,count,count*line,count*line-query.length_bytes,(
        'CXL.mem request/response data quanta only; no PCIe TLP framing, FLIT/credit/arbitration or complete memory service',
        'Host cache coherence, snoop/directory/atomic/ordering, visibility and physical energy are unmodeled'))


# Independently query enabled CXL.mem capability, flat address mapping and declared request reachability.
def analyze_cxl_access(system: CxlMemorySystem, plan: MemoryPlan, request: CxlAccessRequest) -> CxlAccessAnalysis:
    return _analyze(system,plan,request,None)


# Recheck saved static access/line observations without producer execution or a replacement path search.
def validate_cxl_access(system: CxlMemorySystem, plan: MemoryPlan, request: CxlAccessRequest, saved_path: SystemPath) -> CxlAccessAnalysis:
    return _analyze(system,plan,request,saved_path)
