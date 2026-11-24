"""Contiguous logical KV append and Attention input binding; no target memory allocator."""

from contracts.workload.attention import AttentionInputs, AttentionSpec, KvCacheState, attention_buffer, validate_attention
from contracts.workload.linear import positive_int


# Append token slices within each B/head group; a flat old+new concatenation would corrupt multihead/batch layout.
def append_kv(state: KvCacheState, *, k: tuple[float, ...], v: tuple[float, ...], tokens: int,
              expected_identity: str, max_elements: int = 1_000_000) -> KvCacheState:
    if not isinstance(state, KvCacheState):
        raise TypeError('state must be KvCacheState')
    if expected_identity != state.identity_hash:
        raise ValueError('KV append source identity mismatch')
    positive_int('tokens', tokens)
    positive_int('max_elements', max_elements)
    p = state.spec
    total = state.tokens + tokens
    if total > p.max_tokens:
        raise ValueError('KV logical token capacity exceeded')
    groups = p.batch_size * p.kv_heads
    if groups * total * (p.key_dim + p.value_dim) > max_elements:
        raise ValueError('KV snapshot materialization exceeds max_elements')
    result = {}
    for name, raw, dim in (('k', k, p.key_dim), ('v', v, p.value_dim)):
        added = attention_buffer(name, raw)
        if len(added) != groups * tokens * dim:
            raise ValueError(f'appended {name} length does not match token slice')
        old = getattr(state, name)
        result[name] = tuple(value for group in range(groups) for value in
                             (*old[group * state.tokens * dim:(group + 1) * state.tokens * dim],
                              *added[group * tokens * dim:(group + 1) * tokens * dim]))
    return KvCacheState(spec=p, version=state.version + 1, tokens=total, **result)


# Bind an explicit query to resident KV; caller selects causal query positions, preserving the cache snapshot.
def attention_from_cache(spec: AttentionSpec, state: KvCacheState, q: tuple[float, ...]) -> AttentionInputs:
    if not isinstance(spec, AttentionSpec) or not isinstance(state, KvCacheState):
        raise TypeError('expected AttentionSpec and KvCacheState')
    p = state.spec
    if (spec.batch_size, spec.kv_heads, spec.key_dim, spec.value_dim, spec.kv_length) != (
            p.batch_size, p.kv_heads, p.key_dim, p.value_dim, state.tokens):
        raise ValueError('Attention/cache shape or token extent mismatch')
    result = AttentionInputs(q=q, k=state.k, v=state.v)
    validate_attention(spec, result)
    return result
