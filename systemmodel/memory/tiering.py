"""Disjoint physical memory tiers and explicit before/copy-overlap/after reservation transitions."""

from dataclasses import dataclass
from typing import Literal

from contracts.hardware.network import string_tuple, validate_count, validate_identity
from contracts.versions.json_codec import content_hash
from systemmodel.memory.model import MemoryPlan, MemorySystem
from systemmodel.memory.placement import analyze_placement
from systemmodel.topology.graph import freeze_inventory


# A tier groups actual backings by access policy; a name/order does not imply latency, bandwidth or coherent access.
@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryTier:
    tier_id: str  # Unique policy group, independent of physical ownership and NUMA group.
    backing_ids: tuple[str, ...]  # Disjoint physical backing references; no copied capacity fields.
    access_kind: Literal['local','cxl.mem','dma_only']  # Declared access policy, checked by the appropriate transport adapter.
    source_ref: str  # Tier/policy assignment provenance, not a performance ranking.

    # Freeze exact membership and preserve policy without granting path or protocol capability.
    def __post_init__(self) -> None:
        for name in ('tier_id','source_ref'):
            validate_identity(name,getattr(self,name))
        object.__setattr__(self,'backing_ids',tuple(sorted(string_tuple('backing_ids',self.backing_ids,unique=True))))
        if self.access_kind not in ('local','cxl.mem','dma_only'):
            raise ValueError('unsupported tier access policy')


# Every physical backing belongs to one tier; total capacities are derived from the authoritative memory inventory.
@dataclass(frozen=True, slots=True, kw_only=True)
class TieredMemorySystem:
    memory: MemorySystem  # Unique backing/owner/capacity/source inventory.
    tiers: tuple[MemoryTier, ...]  # Complete disjoint assignment, without inherited membership.
    source_ref: str  # Whole-tier organization assumption/version.

    # Reject missing/duplicate/foreign membership rather than summing the same physical storage twice.
    def __post_init__(self) -> None:
        if not isinstance(self.memory,MemorySystem):
            raise TypeError('expected MemorySystem')
        validate_identity('source_ref',self.source_ref)
        object.__setattr__(self,'tiers',freeze_inventory('tiers',self.tiers,MemoryTier,'tier_id'))
        members = [key for tier in self.tiers for key in tier.backing_ids]
        if len(set(members))!=len(members) or set(members)!={b.resource_id for b in self.memory.backings}:
            raise ValueError('tiers must partition all physical backings exactly once')

    # Include complete backing, tier policy and provenance in the immutable tier-system identity.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)


# Capacity and simultaneous occupancy are different observations; multiple copies count even for one logical object.
@dataclass(frozen=True, slots=True)
class TierUsage:
    tier_id: str  # Exact tier identity.
    capacity_bytes: int  # Sum of uniquely assigned backing capacity [B], not proof of host reachability.
    reserved_bytes: int  # Simultaneous rounded reservations at the queried phase [B].
    logical_bytes: int  # Sum of live physical copies' useful object sizes [B].
    padding_bytes: int  # reserved_bytes - logical_bytes [B].
    allocation_ids: tuple[str, ...]  # Live physical copies counted at this phase.


# An observation at one shared logical phase can be summed across tiers; independent historical peaks cannot.
@dataclass(frozen=True, slots=True)
class ResidencyAnalysis:
    system_identity: str  # Complete tier-system identity.
    plan_identity: str  # Exact object/allocation/view/source identity.
    phase: int  # Shared logical liveness phase, not a target timestamp.
    tiers: tuple[TierUsage, ...]  # Simultaneous usage of every tier, including unused capacity.


# Validate full interval feasibility, then aggregate live copies at one phase without per-byte/time enumeration.
def analyze_residency(system: TieredMemorySystem, plan: MemoryPlan, phase: int) -> ResidencyAnalysis:
    if not isinstance(system,TieredMemorySystem):
        raise TypeError('expected TieredMemorySystem')
    validate_count('phase',phase)
    analyze_placement(system.memory,plan)
    objects = {o.object_id:o for o in plan.objects}
    backings = {b.resource_id:b for b in system.memory.backings}
    rows = []
    for tier in system.tiers:
        live = tuple(a for a in plan.allocations if a.backing_id in tier.backing_ids and a.begin_phase<=phase<a.end_phase)
        logical = sum(objects[a.object_id].size_bytes for a in live)
        reserved = sum(((objects[a.object_id].size_bytes+backings[a.backing_id].allocation_granule_bytes-1)//backings[a.backing_id].allocation_granule_bytes)
                       *backings[a.backing_id].allocation_granule_bytes for a in live)
        rows.append(TierUsage(tier.tier_id,sum(backings[key].capacity_bytes for key in tier.backing_ids),reserved,logical,reserved-logical,tuple(a.allocation_id for a in live)))
    return ResidencyAnalysis(system.identity_hash,plan.identity_hash,phase,tuple(rows))


# Three candidate snapshots make transient duplicate storage explicit; none is mutated or published by analysis.
@dataclass(frozen=True, slots=True, kw_only=True)
class TierMigration:
    before: MemoryPlan  # Existing authoritative object/copy/view roster.
    during: MemoryPlan  # Before plus one new full-object target reservation/views; source remains live.
    after: MemoryPlan  # During, optionally removing exactly the source copy/views for a move.
    source_allocation_id: str  # Existing full logical object copy to read.
    target_allocation_id: str  # New whole-object copy identity; must not already exist in before.
    operation: Literal['copy','move']  # Copy retains source; move retires source only after hypothetical completion.
    source_ref: str  # Explicit migration policy/declaration provenance.

    # Local type validation permits infeasible overlap/capacity transitions to be retained as failed research candidates.
    def __post_init__(self) -> None:
        for name in ('source_allocation_id','target_allocation_id','source_ref'):
            validate_identity(name,getattr(self,name))
        if any(not isinstance(getattr(self,name),MemoryPlan) for name in ('before','during','after')) or self.operation not in ('copy','move'):
            raise ValueError('invalid migration snapshots/operation')
        if self.source_allocation_id==self.target_allocation_id:
            raise ValueError('migration requires a distinct target copy identity')

    # Bind all intermediate reservations, views and operation choices rather than just the final placement.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)


# Transition feasibility is a reservation proof under declared liveness, not data-copy completion or coherent publication.
@dataclass(frozen=True, slots=True)
class MigrationAnalysis:
    migration_identity: str  # Full before/during/after source-bound migration declaration.
    before: ResidencyAnalysis  # Simultaneous pre-copy usage.
    during: ResidencyAnalysis  # Source and target coexist at the same logical phase.
    after: ResidencyAnalysis  # Candidate post-copy usage, conditional on successful external completion.
    object_id: str  # Preserved logical object identity.
    payload_bytes: int  # One complete logical object extent [B], independent of different tier allocation granules.
    source_tier_id: str  # Source backing's exact tier.
    target_tier_id: str  # Destination backing's exact tier.
    additional_reserved_bytes: int  # During minus before simultaneous reserved storage [B].


# Permit exactly one new target and optional source retirement; forbid hidden source drops, resized objects or unrelated changes.
def analyze_migration(system: TieredMemorySystem, migration: TierMigration, phase: int) -> MigrationAnalysis:
    if not isinstance(migration,TierMigration):
        raise TypeError('expected TierMigration')
    before = analyze_residency(system,migration.before,phase)
    during = analyze_residency(system,migration.during,phase)
    after = analyze_residency(system,migration.after,phase)
    if migration.before.objects!=migration.during.objects or migration.before.objects!=migration.after.objects:
        raise ValueError('migration must preserve the complete logical object roster and sizes')
    old = {a.allocation_id:a for a in migration.before.allocations}
    overlap = {a.allocation_id:a for a in migration.during.allocations}
    final = {a.allocation_id:a for a in migration.after.allocations}
    source,target = old.get(migration.source_allocation_id),overlap.get(migration.target_allocation_id)
    if source is None or target is None or target.allocation_id in old or source.object_id!=target.object_id:
        raise ValueError('migration needs an existing source and one new copy of the same object')
    if not source.begin_phase<=phase<source.end_phase or not target.begin_phase<=phase<target.end_phase:
        raise ValueError('source and target must both be live during migration')
    if overlap!={**old,target.allocation_id:target}:
        raise ValueError('during snapshot must retain all prior allocations and add only the target')
    expected = dict(overlap)
    if migration.operation=='move':
        del expected[source.allocation_id]
    if final!=expected:
        raise ValueError('after snapshot changes unrelated allocations or violates copy/move retention')
    old_views = {r.region_id:r for r in migration.before.regions}
    overlap_views = {r.region_id:r for r in migration.during.regions}
    if any(overlap_views.get(key)!=value for key,value in old_views.items()) or any(r.allocation_id!=target.allocation_id for key,r in overlap_views.items() if key not in old_views):
        raise ValueError('during snapshot must preserve old views and add target views only')
    expected_views = tuple(r for r in migration.during.regions if migration.operation=='copy' or r.allocation_id!=source.allocation_id)
    if migration.after.regions!=expected_views:
        raise ValueError('after snapshot changes unrelated views or retains retired source views')
    memberships = {key:t.tier_id for t in system.tiers for key in t.backing_ids}
    size = next(o.size_bytes for o in migration.before.objects if o.object_id==source.object_id)
    extra = sum(t.reserved_bytes for t in during.tiers)-sum(t.reserved_bytes for t in before.tiers)
    return MigrationAnalysis(migration.identity_hash,before,during,after,source.object_id,size,memberships[source.backing_id],memberships[target.backing_id],extra)
