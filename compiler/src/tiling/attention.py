"""Bounded Attention query blocking and independent exact coverage validation."""

from contracts.plan.attention import AttentionBlock, AttentionPlan
from contracts.workload.attention import AttentionSpec
from contracts.workload.linear import positive_int


# Each query/head owner retains full-key reduction semantics, using real query tails without padded arithmetic.
def build_attention_plan(spec: AttentionSpec, *, query_tile: int, score_policy: str = 'fused',
                         kv_layout: str = 'shared', max_blocks: int = 100_000) -> AttentionPlan:
    if not isinstance(spec, AttentionSpec):
        raise TypeError('spec must be AttentionSpec')
    positive_int('query_tile', query_tile)
    positive_int('max_blocks', max_blocks)
    count = spec.batch_size * spec.query_heads * ((spec.query_length + query_tile - 1) // query_tile)
    if count > max_blocks:
        raise ValueError('Attention plan exceeds max_blocks')
    blocks = tuple(AttentionBlock(batch=b, head=h, query_start=q, rows=min(query_tile, spec.query_length-q))
                   for b in range(spec.batch_size) for h in range(spec.query_heads) for q in range(0, spec.query_length, query_tile))
    return AttentionPlan(workload_hash=spec.identity_hash, query_tile=query_tile,
                         score_policy=score_policy, kv_layout=kv_layout, blocks=blocks)


# Check coverage with a linear row cursor, independently of builder enumeration; duplicates and gaps both fail.
def validate_attention_plan(spec: AttentionSpec, plan: AttentionPlan) -> None:
    if not isinstance(spec, AttentionSpec) or not isinstance(plan, AttentionPlan) or plan.workload_hash != spec.identity_hash:
        raise ValueError('Attention plan workload identity mismatch')
    cursor = 0
    for block in plan.blocks:
        start = (block.batch * spec.query_heads + block.head) * spec.query_length + block.query_start
        if (block.batch >= spec.batch_size or block.head >= spec.query_heads or block.query_start >= spec.query_length
                or block.query_start % plan.query_tile or start != cursor
                or block.rows != min(plan.query_tile, spec.query_length-block.query_start)):
            raise ValueError('Attention block order/coverage/grid mismatch')
        cursor += block.rows
    if cursor != spec.batch_size * spec.query_heads * spec.query_length:
        raise ValueError('incomplete Attention output row coverage')
