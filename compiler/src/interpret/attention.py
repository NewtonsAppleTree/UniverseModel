"""Binary64 Attention plan interpreter independent of workloads' Fraction/Decimal reference."""

from math import exp, isfinite

from compiler.src.memplan.attention import plan_attention_memory
from contracts.plan.attention import AttentionPlan
from contracts.workload.attention import AttentionInputs, AttentionSpec, validate_attention
from contracts.workload.linear import positive_int


# Reject intermediate overflow; finite binary64 arithmetic is part of this interpreter's declared domain.
def _finite(value: float) -> float:
    if not isfinite(value):
        raise ValueError('nonfinite Attention binary64 intermediate')
    return value


# Execute visible QK, stable scalar softmax and AV; policies control actual copies and intermediate persistence.
def execute_attention_plan(spec: AttentionSpec, inputs: AttentionInputs, plan: AttentionPlan, *,
                           scratch_capacity_bytes: int, backing_capacity_bytes: int,
                           max_macs: int = 1_000_000, max_elements: int = 1_000_000) -> tuple[float, ...]:
    validate_attention(spec, inputs)
    memory = plan_attention_memory(spec, plan, scratch_capacity_bytes=scratch_capacity_bytes, backing_capacity_bytes=backing_capacity_bytes)
    positive_int('max_macs', max_macs)
    positive_int('max_elements', max_elements)
    if spec.visible_pairs*(spec.key_dim+spec.value_dim) > max_macs or (memory.backing_bytes+memory.scratch_bytes)//8 > max_elements:
        raise ValueError('Attention interpreter exceeds max_macs/max_elements')
    b, h, hk, sq, sk, d, dv = spec.batch_size, spec.query_heads, spec.kv_heads, spec.query_length, spec.kv_length, spec.key_dim, spec.value_dim
    keys, values = inputs.k, inputs.v
    if plan.kv_layout == 'expanded':
        expanded = []
        for source, dim in ((keys, d), (values, dv)):
            expanded.append(tuple(value for batch in range(b) for head in range(h)
                                  for value in source[(batch*hk+head//(h//hk))*sk*dim:(batch*hk+head//(h//hk)+1)*sk*dim]))
        keys, values = expanded
    output = [0.0] * (b*h*sq*dv)
    backing = [0.0] * spec.score_pairs if plan.score_policy == 'spill' else None
    for block in plan.blocks:
        group = block.batch * (h if plan.kv_layout == 'expanded' else hk) + (block.head if plan.kv_layout == 'expanded' else block.head//(h//hk))
        row0 = (block.batch*h+block.head)*sq+block.query_start
        local_q = inputs.q[row0*d:(row0+block.rows)*d]
        local_k = keys[group*sk*d:(group+1)*sk*d]
        scores = [0.0] * (block.rows*sk)
        for row in range(block.rows):
            visible = spec.query_start+block.query_start+row+1 if spec.causal else sk
            for key in range(visible):
                total = 0.0
                for feature in range(d):
                    total = _finite(total+_finite(local_q[row*d+feature]*local_k[key*d+feature]))
                scores[row*sk+key] = _finite(total*spec.scale)
        if backing is not None:
            backing[row0*sk:(row0+block.rows)*sk] = scores
            scores = backing[row0*sk:(row0+block.rows)*sk]
        for row in range(block.rows):
            visible = spec.query_start+block.query_start+row+1 if spec.causal else sk
            largest = max(scores[row*sk:row*sk+visible])
            exps = [exp(_finite(value-largest)) for value in scores[row*sk:row*sk+visible]]
            denominator = sum(exps)
            scores[row*sk:row*sk+visible] = [value/denominator for value in exps]
        if backing is not None:
            backing[row0*sk:(row0+block.rows)*sk] = scores
            scores = backing[row0*sk:(row0+block.rows)*sk]
        local_v = values[group*sk*dv:(group+1)*sk*dv]
        for row in range(block.rows):
            visible = spec.query_start+block.query_start+row+1 if spec.causal else sk
            for feature in range(dv):
                total = 0.0
                for key in range(visible):
                    total = _finite(total+_finite(scores[row*sk+key]*local_v[key*dv+feature]))
                output[(row0+row)*dv+feature] = total
    return tuple(output)
