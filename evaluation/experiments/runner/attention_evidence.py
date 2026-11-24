"""Validate saved Attention observations and row ownership without generating inputs or executing a model."""

from math import isfinite

from compiler.src.memplan.attention import AttentionMemory, AttentionTraffic
from compiler.src.tiling.attention import validate_attention_plan
from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.plan.attention import AttentionPlan
from contracts.versions.json_codec import canonical_json
from contracts.workload.attention import AttentionInputs, AttentionSpec, attention_buffer, attention_identity
from workloads.reference.attention import AttentionReference, compare_attention


# A saved plan must own all rows of this task and use the candidate's exact declared mapping choices.
def validate_saved_plan(spec: AttentionSpec, snapshot: dict, *, query_tile: int, score_policy: str = 'fused',
                        kv_layout: str = 'shared') -> None:
    plan = resolve_dataclass(AttentionPlan,snapshot)
    validate_attention_plan(spec,plan)
    if (plan.query_tile,plan.score_policy,plan.kv_layout)!=(query_tile,score_policy,kv_layout):
        raise ValueError('saved Attention plan differs from selected mapping')


# Check saved reservations, payload bounds and work conservation; no allocator, traffic generator or device model is rerun.
def validate_saved_resources(spec: AttentionSpec, plan: dict, memory: dict, traffic: dict, *,
                             scratch_capacity_bytes: int, backing_capacity_bytes: int) -> int:
    allocation = resolve_dataclass(AttentionMemory,memory)
    work = resolve_dataclass(AttentionTraffic,traffic)
    offset,names = 0,set()
    for name,start,size in allocation.scratch_arenas:
        if not name or name in names or start!=offset or size<=0 or size%8:
            raise ValueError('invalid saved Attention scratch reservation')
        names.add(name)
        offset += size
    if (names!={'Q','K','V','O','score_probability','row_max_sum'} or offset!=allocation.scratch_bytes
            or offset>scratch_capacity_bytes):
        raise ValueError('saved Attention scratch total/capacity mismatch')
    tensors = dict(allocation.backing_tensors)
    expected_names = {'Q','K','V','O'}
    if plan['kv_layout']=='expanded':
        expected_names.update(('K_expanded','V_expanded'))
    if plan['score_policy']=='spill':
        expected_names.add('score_probability')
    if (len(tensors)!=len(allocation.backing_tensors) or set(tensors)!=expected_names
            or any(size<=0 or size%8 for size in tensors.values()) or sum(tensors.values())!=allocation.backing_bytes
            or allocation.backing_bytes>backing_capacity_bytes):
        raise ValueError('saved Attention backing total/capacity mismatch')
    pairs,rows = spec.visible_pairs,spec.batch_size*spec.query_heads*spec.query_length
    expected = (pairs*spec.key_dim,pairs*spec.value_dim,pairs,pairs-rows,pairs,pairs,pairs-rows,pairs)
    actual = (work.qk_macs,work.av_macs,work.scale_multiplications,work.max_comparisons,work.shift_subtractions,
              work.exp_evaluations,work.sum_additions,work.divisions)
    copies = spec.batch_size*spec.query_heads*spec.kv_length*(spec.key_dim+spec.value_dim) if plan['kv_layout']=='expanded' else 0
    if actual!=expected or work.layout_copy_elements!=copies:
        raise ValueError('saved Attention arithmetic/copy work is not conserved')
    expected_transfers = len(plan['blocks'])*(8 if plan['score_policy']=='spill' else 4)
    if plan['kv_layout']=='expanded':
        expected_transfers += 4*spec.batch_size*spec.query_heads
    if len(work.transfers)!=expected_transfers:
        raise ValueError('incomplete saved Attention transfer roster')
    for transfer in work.transfers:
        if (transfer.tensor not in tensors or transfer.direction not in ('read','write') or transfer.offset_bytes<0
                or transfer.payload_bytes<=0 or transfer.offset_bytes%8 or transfer.payload_bytes%8
                or transfer.offset_bytes+transfer.payload_bytes>tensors[transfer.tensor]
                or not -1<=transfer.block_index<len(plan['blocks'])
                or (transfer.block_index==-1 and plan['kv_layout']!='expanded')):
            raise ValueError('saved Attention transfer outside declared backing/block')
    return work.external_bytes


# v1 evidence gets structural checks; v2 additionally reconstructs error/tolerance results from saved reference observations.
def validate_saved_comparison(spec: AttentionSpec, inputs: AttentionInputs, actual: list, validation: dict, *,
                              reference_output: list | None = None, atol: float = 1e-12, rtol: float = 1e-12) -> None:
    values = attention_buffer('saved Attention output',actual)
    size = spec.batch_size*spec.query_heads*spec.query_length*spec.value_dim
    if len(values)!=size:
        raise ValueError('saved Attention output shape mismatch')
    if not isinstance(validation,dict) or set(validation)!={'passed','max_absolute_error','mismatched_indices'}:
        raise ValueError('invalid saved Attention validation schema')
    passed,error,indices = validation['passed'],validation['max_absolute_error'],validation['mismatched_indices']
    if (type(passed) is not bool or type(error) not in (int,float) or not isfinite(error) or error<0
            or not isinstance(indices,list) or any(type(i) is not int or not 0<=i<size for i in indices)
            or indices!=sorted(set(indices)) or passed!= (not indices) or (indices and error==0)):
        raise ValueError('inconsistent saved Attention validation')
    if reference_output is not None:
        reference = AttentionReference(attention_identity(spec,inputs),tuple(reference_output),(),80)
        observed = compare_attention(spec,inputs,values,reference,atol=atol,rtol=rtol)
        if canonical_json(observed)!=canonical_json(validation):
            raise ValueError('saved Attention validation disagrees with observed outputs')
