"""Named tensor regions, conservative scratch reservation and concrete Attention payload transfers."""

from dataclasses import dataclass

from compiler.src.tiling.attention import validate_attention_plan
from contracts.plan.attention import AttentionPlan
from contracts.workload.attention import AttentionSpec
from contracts.workload.linear import positive_int


# Each transfer is contiguous within one named backing tensor; addresses across tensors are separate domains.
@dataclass(frozen=True, slots=True)
class AttentionTransfer:
    block_index: int  # Consumer/producer block [index]; -1 identifies the KV expansion prelude.
    tensor: str  # Q/K/V/O, K_expanded/V_expanded or shared in-place score_probability temporary.
    direction: str  # read or write relative to scratch.
    offset_bytes: int  # Offset within the named tensor [B].
    payload_bytes: int  # Actual contiguous binary64 payload [B]; DMA rounding is separate.


# All arenas are reserved for the call; this conservative allocator does not assert optimal peak liveness.
@dataclass(frozen=True, slots=True)
class AttentionMemory:
    scratch_arenas: tuple[tuple[str, int, int], ...]  # (name, offset, size) [identity,B,B], disjoint reserved arenas.
    scratch_bytes: int  # Sum of maximum Q/K/V/score/O/reduction arenas [B].
    backing_tensors: tuple[tuple[str, int], ...]  # Named disjoint backing sizes [B], original inputs retained.
    backing_bytes: int  # Sum of reserved backing tensors [B], excluding the distinct scratch resource.


# Keep actual visible arithmetic and copy/traffic work separate from logical unique KV capacity.
@dataclass(frozen=True, slots=True)
class AttentionTraffic:
    qk_macs: int  # Visible pairs times D [MAC]; causal masking is explicitly exploited by this interpreter.
    av_macs: int  # Visible pairs times Dv [MAC].
    scale_multiplications: int  # One scale multiplication per visible score [multiply].
    max_comparisons: int  # Sum(visible keys-1) [compare].
    shift_subtractions: int  # One subtraction per visible score [subtract].
    exp_evaluations: int  # One exponential per visible score [exp].
    sum_additions: int  # Denominator reduction, sum(visible keys-1) [add].
    divisions: int  # Probability normalization [divide].
    layout_copy_elements: int  # Elements copied to explicit expanded KV [element], not free aliasing or dtype conversion.
    transfers: tuple[AttentionTransfer, ...]  # Ordered payload movements, including layout and score spills.

    # External payload counts both directions once per declared transfer; no caching is inferred.
    @property
    def external_bytes(self) -> int:
        return sum(t.payload_bytes for t in self.transfers)


# Reserve full-key operands and one in-place local score/probability matrix for the largest query block.
def plan_attention_memory(spec: AttentionSpec, plan: AttentionPlan, *, scratch_capacity_bytes: int,
                          backing_capacity_bytes: int) -> AttentionMemory:
    validate_attention_plan(spec, plan)
    for name, value in (('scratch_capacity_bytes', scratch_capacity_bytes), ('backing_capacity_bytes', backing_capacity_bytes)):
        positive_int(name, value)
    b, h, hk, q, k, d, v = spec.batch_size, spec.query_heads, spec.kv_heads, spec.query_length, spec.kv_length, spec.key_dim, spec.value_dim
    rows = min(plan.query_tile, q)
    sizes = (('Q', rows*d*8), ('K', k*d*8), ('V', k*v*8), ('score_probability', rows*k*8), ('O', rows*v*8), ('row_max_sum', rows*2*8))
    arenas, offset = [], 0
    for name, size in sizes:
        arenas.append((name, offset, size))
        offset += size
    tensors = [('Q', b*h*q*d*8), ('K', b*hk*k*d*8), ('V', b*hk*k*v*8), ('O', b*h*q*v*8)]
    if plan.kv_layout == 'expanded':
        tensors.extend((('K_expanded', b*h*k*d*8), ('V_expanded', b*h*k*v*8)))
    if plan.score_policy == 'spill':
        tensors.append(('score_probability', b*h*q*k*8))
    backing = sum(size for _, size in tensors)
    if offset > scratch_capacity_bytes or backing > backing_capacity_bytes:
        raise ValueError(f'Attention capacity exceeded: scratch {offset}/{scratch_capacity_bytes}, backing {backing}/{backing_capacity_bytes} bytes')
    return AttentionMemory(tuple(arenas), offset, tuple(tensors), backing)


# Prelude copies KV once per query head; blocks reload full KV and optionally spill/reload the score/probability region.
def count_attention_traffic(spec: AttentionSpec, plan: AttentionPlan, *, max_transfers: int = 1_000_000) -> AttentionTraffic:
    validate_attention_plan(spec, plan)
    positive_int('max_transfers', max_transfers)
    expected = len(plan.blocks) * (8 if plan.score_policy == 'spill' else 4)
    expected += 4 * spec.batch_size * spec.query_heads if plan.kv_layout == 'expanded' else 0
    if expected > max_transfers:
        raise ValueError('Attention movement exceeds max_transfers')
    transfers = []
    if plan.kv_layout == 'expanded':
        for batch in range(spec.batch_size):
            for head in range(spec.query_heads):
                source = batch * spec.kv_heads + head // (spec.query_heads // spec.kv_heads)
                target = batch * spec.query_heads + head
                for name, dim in (('K', spec.key_dim), ('V', spec.value_dim)):
                    size = spec.kv_length * dim * 8
                    transfers.extend((AttentionTransfer(-1, name, 'read', source*size, size),
                                      AttentionTransfer(-1, name+'_expanded', 'write', target*size, size)))
    for i, block in enumerate(plan.blocks):
        row = (block.batch * spec.query_heads + block.head) * spec.query_length + block.query_start
        group = block.batch * spec.kv_heads + block.head // (spec.query_heads // spec.kv_heads)
        if plan.kv_layout == 'expanded':
            group = block.batch * spec.query_heads + block.head
        suffix = '_expanded' if plan.kv_layout == 'expanded' else ''
        transfers.extend((AttentionTransfer(i, 'Q', 'read', row*spec.key_dim*8, block.rows*spec.key_dim*8),
                          AttentionTransfer(i, 'K'+suffix, 'read', group*spec.kv_length*spec.key_dim*8, spec.kv_length*spec.key_dim*8)))
        if plan.score_policy == 'spill':
            transfers.extend(AttentionTransfer(i, 'score_probability', direction, row*spec.kv_length*8, block.rows*spec.kv_length*8)
                             for direction in ('write', 'read', 'write', 'read'))
        transfers.extend((AttentionTransfer(i, 'V'+suffix, 'read', group*spec.kv_length*spec.value_dim*8, spec.kv_length*spec.value_dim*8),
                          AttentionTransfer(i, 'O', 'write', row*spec.value_dim*8, block.rows*spec.value_dim*8)))
    # Derive visible work from the row owners, rather than assuming rectangular MAC counts.
    pairs = sum(sum(spec.query_start+q+1 if spec.causal else spec.kv_length
                    for q in range(block.query_start, block.query_start+block.rows)) for block in plan.blocks)
    rows = sum(block.rows for block in plan.blocks)
    copies = spec.batch_size * spec.query_heads * spec.kv_length * (spec.key_dim+spec.value_dim) if plan.kv_layout == 'expanded' else 0
    return AttentionTraffic(pairs*spec.key_dim, pairs*spec.value_dim, pairs, pairs-rows, pairs, pairs, pairs-rows, pairs, copies, tuple(transfers))
