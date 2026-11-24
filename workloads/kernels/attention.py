"""Attention task generation and logical accounting, independent of mapping/hardware."""

from dataclasses import dataclass
from hashlib import sha256

from contracts.workload.attention import AttentionInputs, AttentionSpec
from contracts.workload.linear import positive_int


# Keep complete rectangular demand, visible pairs, unique data and materialized intermediates separate.
@dataclass(frozen=True, slots=True)
class AttentionWork:
    dense_qk_macs: int  # B*Hq*Sq*Skv*D [MAC], full rectangular QK contraction.
    dense_av_macs: int  # B*Hq*Sq*Skv*Dv [MAC], full rectangular probability/value contraction.
    visible_pairs: int  # P valid query/key pairs [pair]; mask-aware algorithm opportunity, not executed work.
    visible_pair_macs: int  # P*(D+Dv) [MAC]; exact mask exploitation must be justified by the mapping.
    softmax_rows: int  # B*Hq*Sq [row], all nonempty by the contract.
    reference_scale_multiplications: int  # P [multiply] for explicitly scaled visible logits.
    reference_max_comparisons: int  # P-softmax_rows [comparison] for row maxima.
    reference_subtractions: int  # P [subtract] for stable row shifts.
    reference_exp_evaluations: int  # P [exp]; the reference excludes masked scores before normalization.
    reference_sum_additions: int  # P-softmax_rows [add], denominator reduction over valid exponentials.
    reference_divisions: int  # P [divide] to normalize probabilities; no reciprocal-fusion assumption.
    q_bytes: int  # B*Hq*Sq*D*8 [B], unique query payload.
    kv_bytes: int  # B*Hkv*Skv*(D+Dv)*8 [B], unique K/V payload without GQA replication.
    output_bytes: int  # B*Hq*Sq*Dv*8 [B], output payload.
    materialized_score_bytes: int  # B*Hq*Sq*Skv*8 [B] for one full matrix; not compulsory scratch or traffic.


# Counts are shape/semantics dependent; no assumed cache reuse, bandwidth, scalar-to-MAC conversion or execution time.
def describe_attention(spec: AttentionSpec) -> AttentionWork:
    if not isinstance(spec, AttentionSpec):
        raise TypeError('spec must be AttentionSpec')
    rows = spec.batch_size * spec.query_heads * spec.query_length
    return AttentionWork(spec.score_pairs * spec.key_dim, spec.score_pairs * spec.value_dim,
                         spec.visible_pairs, spec.visible_pairs * (spec.key_dim + spec.value_dim), rows,
                         spec.visible_pairs, spec.visible_pairs - rows, spec.visible_pairs,
                         spec.visible_pairs, spec.visible_pairs - rows, spec.visible_pairs, rows * spec.key_dim * 8,
                         spec.batch_size * spec.kv_heads * spec.kv_length * (spec.key_dim + spec.value_dim) * 8,
                         rows * spec.value_dim * 8, spec.score_pairs * 8)


# Stable labeled SHA256 test inputs, values (byte%17-8)/16; synthetic bounded data, not a representative distribution.
def generate_attention(spec: AttentionSpec, seed: int, *, max_elements: int = 1_000_000) -> AttentionInputs:
    if not isinstance(spec, AttentionSpec):
        raise TypeError('spec must be AttentionSpec')
    if type(seed) is not int or not 0 <= seed < 1 << 64:
        raise ValueError('seed must be uint64')
    positive_int('max_elements', max_elements)
    if spec.input_elements > max_elements:
        raise ValueError('Attention input materialization exceeds max_elements')
    sizes = {'q': spec.batch_size * spec.query_heads * spec.query_length * spec.key_dim,
             'k': spec.batch_size * spec.kv_heads * spec.kv_length * spec.key_dim,
             'v': spec.batch_size * spec.kv_heads * spec.kv_length * spec.value_dim}
    buffers = {name: tuple((sha256(f'attention-input/v1:{seed}:{name}:{i}'.encode('ascii')).digest()[0] % 17 - 8) / 16.0
                           for i in range(size)) for name, size in sizes.items()}
    return AttentionInputs(**buffers)
