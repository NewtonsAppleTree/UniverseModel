"""Explicit query-block Attention plans; no hidden context tiling or online-softmax semantics."""

from dataclasses import dataclass
from typing import Literal

from contracts.workload.attention import nonnegative_int
from contracts.workload.linear import positive_int


# A block owns complete output rows for one batch/query head; each row reduces over its visible keys.
@dataclass(frozen=True, slots=True, kw_only=True)
class AttentionBlock:
    batch: int  # Batch index [sample index].
    head: int  # Query head index [head index], not KV head.
    query_start: int  # Local row start in Q [token index], distinct from the spec's absolute causal origin.
    rows: int  # Consecutive complete output rows [token], positive.

    # Local extents exclude bool; global coverage belongs to compiler validation.
    def __post_init__(self) -> None:
        for name in ('batch', 'head', 'query_start'):
            nonnegative_int(name, getattr(self, name))
        positive_int('rows', self.rows)


# Plans fix head-major query blocking, score residency and explicit KV replication; arithmetic remains binary64.
@dataclass(frozen=True, slots=True, kw_only=True)
class AttentionPlan:
    workload_hash: str  # Full AttentionSpec identity, including causal origin and scale.
    query_tile: int  # Maximum rows per block [token].
    score_policy: Literal['fused', 'spill']  # Local score/probability reuse, or four external intermediate transfers.
    kv_layout: Literal['shared', 'expanded']  # Hkv backing, or an explicit Hq-replicated temporary backing.
    blocks: tuple[AttentionBlock, ...]  # Complete ordered row owners; no implicit parallel execution.
    schema_version: Literal['attention-plan/v1'] = 'attention-plan/v1'  # Full-key reductions, no context partition.

    # Freeze a bounded producer roster and reject unknown policy/schema before consumption.
    def __post_init__(self) -> None:
        if type(self.workload_hash) is not str or len(self.workload_hash) != 64 or any(c not in '0123456789abcdef' for c in self.workload_hash):
            raise ValueError('workload_hash must be lowercase SHA256')
        positive_int('query_tile', self.query_tile)
        if self.score_policy not in ('fused', 'spill') or self.kv_layout not in ('shared', 'expanded') or self.schema_version != 'attention-plan/v1':
            raise ValueError('unsupported Attention plan policy/schema')
        if not isinstance(self.blocks, (list, tuple)) or not self.blocks or any(not isinstance(b, AttentionBlock) for b in self.blocks):
            raise ValueError('blocks must be a nonempty AttentionBlock list/tuple')
        object.__setattr__(self, 'blocks', tuple(self.blocks))
