"""Bind static migration snapshots to native host CXL.mem copies or compatible existing PCIe/DMA copy chains."""

from dataclasses import dataclass
from typing import Literal

from chipmodel.composition.die.topology import ancestry
from contracts.hardware.network import validate_count, validate_identity
from systemmodel.io.cxl.model import CxlAccessAnalysis, CxlAccessRequest, CxlMemorySystem, analyze_cxl_access, validate_cxl_access
from systemmodel.io.dma.analysis import TransferAnalysis, analyze_transfers, validate_transfers
from systemmodel.io.dma.model import CopyBatch, DmaSystem
from systemmodel.memory.access import MemoryAccessRequest, ResolvedSpan, resolve_span
from systemmodel.memory.tiering import MigrationAnalysis, TieredMemorySystem, TierMigration, analyze_migration
from systemmodel.topology.query import SystemPath


# A host copy pairs one remote CXL.mem request with an explicitly named host-local memory view.
@dataclass(frozen=True, slots=True, kw_only=True)
class CxlCopyRequest:
    request: CxlAccessRequest  # Read for remote-to-local promotion; write for local-to-remote demotion.
    local_region_id: str  # Local destination for read, or local source for write.
    local_address: int  # First host-local useful byte in that view's address domain [B].

    # Keep host-local addressing explicit; no hidden buffer, CPU throughput or DMA capability is inferred.
    def __post_init__(self) -> None:
        if not isinstance(self.request,CxlAccessRequest):
            raise TypeError('expected CxlAccessRequest')
        validate_identity('local_region_id',self.local_region_id)
        validate_count('local_address',self.local_address)


# Successful static transport checks do not execute the copy or authorize publication of the proposed after snapshot.
@dataclass(frozen=True, slots=True)
class MigrationEvidence:
    transition: MigrationAnalysis  # Before/overlap/after feasibility and exact full-object demand.
    method: Literal['host-cxl.mem','dma']  # Actual modeled data-movement semantics; no PCIe/CXL framing substitution.
    cxl_access: CxlAccessAnalysis | None  # Native CXL line-access evidence for a host copy, otherwise None.
    dma: TransferAnalysis | None  # Existing compatible S3 copy-chain evidence, otherwise None.
    local_span: ResolvedSpan | None  # Resolved host-local endpoint for native CXL copy.
    transport_data_bytes: int  # Native line data or sum of useful per-leg DMA data [B]; method-specific, not a shared frame metric.
    known_service_lower_bound_s: float | None  # S3 partial bound [s], or unknown for uncalibrated native CXL/host service.
    unknown_costs: tuple[str, ...]  # Unmodeled service, coherence/publication and physical-cost obligations.


# Match the whole logical object in the named allocation, not a same-sized different object or an arbitrary subrange.
def _check_span(migration: TierMigration, allocation_id: str, span: ResolvedSpan, size: int) -> None:
    allocation = next(a for a in migration.during.allocations if a.allocation_id==allocation_id)
    if (span.allocation_id,span.object_id,span.backing_id,span.physical_offset_bytes,span.length_bytes)!=(
            allocation.allocation_id,allocation.object_id,allocation.backing_id,allocation.offset_bytes,size):
        raise ValueError('migration transport endpoint must cover the named whole-object allocation')


# Native CXL copies check decoder/path and host-local ownership while leaving their target service time unknown.
def _cxl_migration(system: TieredMemorySystem, migration: TierMigration, phase: int, cxl: CxlMemorySystem,
                   copy: CxlCopyRequest, saved_path: SystemPath | None) -> MigrationEvidence:
    if not isinstance(system,TieredMemorySystem) or not isinstance(cxl,CxlMemorySystem) or not isinstance(copy,CxlCopyRequest) or cxl.memory.identity_hash!=system.memory.identity_hash:
        raise ValueError('CXL migration must use the same memory hardware and a CxlCopyRequest')
    transition = analyze_migration(system,migration,phase)
    query = copy.request.access
    if query.phase!=phase or query.length_bytes!=transition.payload_bytes:
        raise ValueError('CXL migration phase/extent must match the complete transition')
    remote = analyze_cxl_access(cxl,migration.during,copy.request) if saved_path is None else validate_cxl_access(cxl,migration.during,copy.request,saved_path)
    promoting = query.operation=='read'
    local_operation = 'write' if promoting else 'read'
    local = resolve_span(system.memory,migration.during,MemoryAccessRequest(source_port_id=query.source_port_id,region_id=copy.local_region_id,
                         address=copy.local_address,length_bytes=transition.payload_bytes,phase=phase,operation=local_operation))
    source,target = (remote.access.span,local) if promoting else (local,remote.access.span)
    _check_span(migration,migration.source_allocation_id,source,transition.payload_bytes)
    _check_span(migration,migration.target_allocation_id,target,transition.payload_bytes)
    policies = {key:t.access_kind for t in system.tiers for key in t.backing_ids}
    if policies[remote.access.span.backing_id]!='cxl.mem' or policies[local.backing_id]!='local':
        raise ValueError('native CXL migration requires cxl.mem and host-local tiers')
    host = next(p for p in system.memory.node.topology.ports if p.port_id==query.source_port_id)
    if host.owner_id not in ancestry(system.memory.node.topology.resources)[local.backing_id] or local.domain_id!=host.domain_id:
        raise ValueError('host copy cannot treat a foreign backing/domain as local memory')
    unknown = (*remote.unknown_costs,'Host local read/write/copy service and migration completion are unknown; after snapshot is conditional, not published')
    return MigrationEvidence(transition,'host-cxl.mem',remote,None,local,remote.data_bytes,None,unknown)


# Independently analyze a complete object promotion/demotion through native CXL.mem and host-local memory.
def analyze_cxl_migration(system: TieredMemorySystem, migration: TierMigration, phase: int, cxl: CxlMemorySystem,
                          copy: CxlCopyRequest) -> MigrationEvidence:
    return _cxl_migration(system,migration,phase,cxl,copy,None)


# Replay the saved CXL path and static migration declaration without performing a new route search.
def validate_cxl_migration(system: TieredMemorySystem, migration: TierMigration, phase: int, cxl: CxlMemorySystem,
                           copy: CxlCopyRequest, saved_path: SystemPath) -> MigrationEvidence:
    if not isinstance(saved_path,SystemPath):
        raise TypeError('expected saved SystemPath')
    return _cxl_migration(system,migration,phase,cxl,copy,saved_path)


# Existing DMA chains apply only to non-CXL.mem tiers; their exact overlap reservation and endpoints must match migration.
def _dma_migration(system: TieredMemorySystem, migration: TierMigration, phase: int, dma: DmaSystem,
                   batch: CopyBatch, saved_paths: tuple[SystemPath, ...] | None) -> MigrationEvidence:
    if not isinstance(system,TieredMemorySystem) or not isinstance(dma,DmaSystem) or not isinstance(batch,CopyBatch) or dma.memory.identity_hash!=system.memory.identity_hash:
        raise ValueError('DMA migration must use the same memory hardware and a CopyBatch')
    transition = analyze_migration(system,migration,phase)
    if batch.placement!=migration.during or batch.phase!=phase or len(batch.chains)!=1 or batch.chains[0].payload_bytes!=transition.payload_bytes:
        raise ValueError('DMA migration requires one full-object chain bound to the during snapshot and phase')
    analysis = analyze_transfers(dma,batch) if saved_paths is None else validate_transfers(dma,batch,saved_paths)
    _check_span(migration,migration.source_allocation_id,analysis.legs[0].source,transition.payload_bytes)
    _check_span(migration,migration.target_allocation_id,analysis.legs[-1].target,transition.payload_bytes)
    policies = {key:t.access_kind for t in system.tiers for key in t.backing_ids}
    if any(policies[span.backing_id]=='cxl.mem' for leg in analysis.legs for span in (leg.source,leg.target)):
        raise ValueError('PCIe posted-write accounting cannot stand in for native CXL.mem migration')
    unknown = (*analysis.unknown_costs,'Migration completion/coherence/publication are unmodeled; after snapshot is conditional')
    return MigrationEvidence(transition,'dma',None,analysis,None,sum(l.traffic.payload_bytes for l in analysis.legs),analysis.bounds.lower_bound_s,unknown)


# Reuse S3's explicit transfer service only after checking the complete before/overlap/after migration contract.
def analyze_dma_migration(system: TieredMemorySystem, migration: TierMigration, phase: int, dma: DmaSystem,
                          batch: CopyBatch) -> MigrationEvidence:
    return _dma_migration(system,migration,phase,dma,batch,None)


# Reanalyze compatible saved DMA routes and work without searching or executing the transfer producer.
def validate_dma_migration(system: TieredMemorySystem, migration: TierMigration, phase: int, dma: DmaSystem,
                           batch: CopyBatch, saved_paths: tuple[SystemPath, ...]) -> MigrationEvidence:
    if not isinstance(saved_paths,(tuple,list)):
        raise TypeError('expected saved path roster')
    return _dma_migration(system,migration,phase,dma,batch,saved_paths)
