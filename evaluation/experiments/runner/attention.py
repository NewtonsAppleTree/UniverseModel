"""Same-task Attention mapping comparisons with independent quality and explicit partial hardware coverage."""

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal

from chipmodel.common import ClockDomain
from chipmodel.compute.npu.mac import MacArithmetic, MacArray, MacWork
from chipmodel.control.data_movement import DmaParams, estimate_dma
from compiler.src.interpret.attention import execute_attention_plan
from compiler.src.memplan.attention import count_attention_traffic, plan_attention_memory
from compiler.src.tiling.attention import build_attention_plan
from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from contracts.workload.attention import AttentionInputs, AttentionSpec, attention_identity
from contracts.workload.linear import positive_int
from evaluation.experiments.runner.bundle import read_records, write_records
from evaluation.experiments.runner.attention_evidence import validate_saved_comparison, validate_saved_plan, validate_saved_resources
from evaluation.experiments.runner.single import run_experiment
from workloads.kernels.attention import generate_attention
from workloads.reference.attention import compare_attention, reference_attention


# A candidate changes only declared mapping choices; every candidate shares the same task/input/hardware budget.
@dataclass(frozen=True, slots=True, kw_only=True)
class AttentionCandidate:
    name: str  # Unique mapping identity.
    query_tile: int  # Maximum rows per query block [token].
    score_policy: Literal['fused', 'spill'] = 'fused'  # Explicit intermediate residency.
    kv_layout: Literal['shared', 'expanded'] = 'shared'  # Logical sharing or explicitly copied backing.
    expected_status: Literal['succeeded', 'failed'] = 'succeeded'  # Reviewed fixture expectation.

    # Reject invalid strategy configuration; capacity failure remains a recorded runtime outcome.
    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name.strip():
            raise ValueError('candidate name must be nonempty')
        positive_int('query_tile', self.query_tile)
        if self.score_policy not in ('fused', 'spill') or self.kv_layout not in ('shared', 'expanded') or self.expected_status not in ('succeeded', 'failed'):
            raise ValueError('invalid Attention candidate policy/status')


# MAC and serialized DMA are separate resources; scalar operations and actual external-memory timing remain uncovered.
@dataclass(frozen=True, slots=True, kw_only=True)
class AttentionHardware:
    scratch_capacity_bytes: int  # Separate scratch reservation budget [B].
    backing_capacity_bytes: int  # Original inputs, outputs and temporary backing reservation budget [B].
    mac: MacArray  # Explicit arithmetic/P/L/II/clock/source profile; must match binary64 mul-add at evaluation.
    dma: DmaParams  # One serialized payload service channel; no implicit second charge for memory traffic.
    dma_clock: ClockDomain  # DMA service clock, independently converted to seconds.

    # Resource parameters are immutable and validated without changing hardware state.
    def __post_init__(self) -> None:
        for name in ('scratch_capacity_bytes', 'backing_capacity_bytes'):
            positive_int(name, getattr(self, name))
        if not isinstance(self.mac, MacArray) or not isinstance(self.dma, DmaParams) or not isinstance(self.dma_clock, ClockDomain):
            raise TypeError('invalid Attention hardware model')
        if self.mac.clock.domain_id == self.dma_clock.domain_id and self.mac.clock != self.dma_clock:
            raise ValueError('same clock domain cannot have different frequencies')


# One complete comparison fixes quality tolerances, host limits and source-independent workload inputs.
@dataclass(frozen=True, slots=True, kw_only=True)
class AttentionMappingStudy:
    workload: AttentionSpec  # Common task semantics for all candidates.
    hardware: AttentionHardware  # Common resource budget, no per-candidate overprovisioning.
    candidates: tuple[AttentionCandidate, ...]  # Complete unique mapping roster, including failures.
    seed: int = 0  # Deterministic uint64 Q/K/V generation seed.
    atol: float = 1e-12  # Absolute numerical output tolerance [output value].
    rtol: float = 1e-12  # Relative numerical tolerance [1].
    max_macs: int = 1_000_000  # Host visible-pair contraction budget [MAC].
    max_elements: int = 1_000_000  # Host input/interpreter storage guard [element].
    max_score_pairs: int = 100_000  # Host independent-reference probability matrix limit [pair].
    schema_version: Literal['attention-mapping/v1'] = 'attention-mapping/v1'  # Same-task fixed-budget comparison.

    # Freeze unique candidates; source shape errors are distinct from candidate feasibility/quality failures.
    def __post_init__(self) -> None:
        if not isinstance(self.workload, AttentionSpec) or not isinstance(self.hardware, AttentionHardware):
            raise TypeError('invalid Attention mapping task/hardware')
        if not isinstance(self.candidates, (list, tuple)) or not self.candidates or any(not isinstance(c, AttentionCandidate) for c in self.candidates):
            raise ValueError('candidates must be nonempty AttentionCandidate list/tuple')
        object.__setattr__(self, 'candidates', tuple(self.candidates))
        if len({c.name for c in self.candidates}) != len(self.candidates):
            raise ValueError('duplicate Attention candidate')
        if type(self.seed) is not int or not 0 <= self.seed < 1 << 64 or self.schema_version != 'attention-mapping/v1':
            raise ValueError('invalid Attention mapping seed/schema')
        for name in ('max_macs', 'max_elements', 'max_score_pairs'):
            positive_int(name, getattr(self, name))
        for name in ('atol', 'rtol'):
            value = getattr(self, name)
            if type(value) not in (float, int) or not isfinite(value) or value < 0:
                raise ValueError('invalid numerical tolerance')


# Execute and compare against the independent reference, then query each resource once with matching arithmetic.
def evaluate_attention(study: AttentionMappingStudy, candidate: AttentionCandidate, inputs: AttentionInputs) -> tuple[dict, tuple[Metric, ...]]:
    if candidate not in study.candidates:
        raise ValueError('candidate is not in study')
    p, hw = study.workload, study.hardware
    plan = build_attention_plan(p, query_tile=candidate.query_tile, score_policy=candidate.score_policy, kv_layout=candidate.kv_layout)
    capacity = {'scratch_capacity_bytes': hw.scratch_capacity_bytes, 'backing_capacity_bytes': hw.backing_capacity_bytes}
    memory = plan_attention_memory(p, plan, **capacity)
    traffic = count_attention_traffic(p, plan)
    actual = execute_attention_plan(p, inputs, plan, **capacity, max_macs=study.max_macs, max_elements=study.max_elements)
    reference = reference_attention(p, inputs, max_macs=study.max_macs, max_score_pairs=study.max_score_pairs)
    quality = compare_attention(p, inputs, actual, reference, atol=study.atol, rtol=study.rtol)
    arithmetic = MacArithmetic(operation='float_mul_add', operand_format='float64', accumulator_format='float64', output_format='float64')
    mac = hw.mac.analyze(MacWork(arithmetic=arithmetic, logical_macs=traffic.qk_macs+traffic.av_macs, executed_macs=traffic.qk_macs+traffic.av_macs))
    dma_cycles = sum(estimate_dma(hw.dma, hw.dma_clock, t.payload_bytes).completion_cycles for t in traffic.transfers)
    dma_s = hw.dma_clock.seconds(dma_cycles)
    lower = max(mac.service.completion_time_s, dma_s)
    metrics = (Metric(name='known_resource_lower_bound', value=lower, unit='second', kind='lower_bound'),
               Metric(name='external_payload', value=traffic.external_bytes, unit='byte', kind='counter'),
               Metric(name='target_execution_time', value=None, unit='second', kind='estimated', unknown_reason='No scalar service, dependency execution, SRAM/DRAM access or contention model'),
               Metric(name='target_energy', value=None, unit='joule', kind='estimated', unknown_reason='No calibrated full-action cost profile'))
    return {'input_identity': attention_identity(p, inputs), 'plan': plan, 'memory': memory, 'traffic': traffic,
            'output': actual, 'reference_output': reference.output, 'validation': quality, 'mac': mac, 'serial_dma_cycles': dma_cycles,
            'serial_dma_s': dma_s, 'known_resource_lower_bound_s': lower}, metrics


# Keep all candidates, including input preparation failures; records own actual inputs rather than just seeds.
def run_study(study: AttentionMappingStudy, *, source_revision: str = 'unrecorded') -> tuple[RunRecord, ...]:
    try:
        prepared = {'data': generate_attention(study.workload, study.seed, max_elements=study.max_elements), 'error': None}
    except (ValueError, TypeError) as exc:
        prepared = {'data': None, 'error': f'{type(exc).__name__}: {exc}'}
    records = []
    for candidate in study.candidates:
        spec = ExperimentSpec(experiment_id=candidate.name, implementation_id='attention-mapping/v2', mode='analytical', source_revision=source_revision,
                              assumptions=('Same task/input/hardware; finite query blocking; complete visible-key reductions',
                                           'Binary64 separate multiply/add; independent Fraction/Decimal numerical reference',
                                           'KV expansion copies and score spills explicit; no implicit cache reuse',
                                           'One serialized DMA channel; MAC/DMA resource subset only; scalar/memory/contended execution unknown'))
        records.append(run_experiment(spec, {'study': study, 'selected': candidate.name}, prepared, _evaluate))
    return tuple(records)


# Convert preparation failures into ordinary failed records without fabricated output tensors.
def _evaluate(config: dict, prepared: dict) -> tuple[dict, tuple[Metric, ...]]:
    if prepared['error'] is not None:
        raise ValueError(prepared['error'])
    study = config['study']
    return evaluate_attention(study, next(c for c in study.candidates if c.name == config['selected']), prepared['data'])


# Replay validates complete common conditions and output identities without running mapping, input generation or models.
def summarize_records(records: tuple[RunRecord, ...]) -> tuple[dict, ...]:
    if not records or any(not isinstance(r, RunRecord) for r in records):
        raise ValueError('expected nonempty Attention mapping records')
    identity, names, ids, rows = None, set(), set(), []
    for record in records:
        if record.spec.implementation_id not in ('attention-mapping/v1','attention-mapping/v2') or record.spec.mode!='analytical':
            raise ValueError('wrong Attention mapping record kind')
        config = parse_json(record.configuration_json)
        if not isinstance(config, dict) or set(config) != {'study', 'selected'}:
            raise ValueError('invalid mapping snapshot')
        study = resolve_dataclass(AttentionMappingStudy, config['study'])
        current = content_hash((config['study'], record.inputs_json, record.spec.implementation_id, record.spec.source_revision, record.spec.assumptions))
        if identity is not None and identity != current:
            raise ValueError('mixed mapping task/input/budget/source')
        identity = current
        candidate = next((c for c in study.candidates if c.name == config['selected']), None)
        if candidate is None or candidate.name != record.spec.experiment_id or candidate.name in names or record.run_id in ids:
            raise ValueError('duplicate or invalid Attention mapping identity')
        prepared = parse_json(record.inputs_json)
        if not isinstance(prepared, dict) or set(prepared) != {'data', 'error'}:
            raise ValueError('invalid prepared mapping inputs')
        if prepared['data'] is None:
            if record.status != 'failed' or type(prepared['error']) is not str or not prepared['error']:
                raise ValueError('missing input requires preparation failure')
        else:
            if prepared['error'] is not None:
                raise ValueError('contradictory preparation status')
            data = resolve_dataclass(AttentionInputs, prepared['data'])
            input_hash = attention_identity(study.workload, data)
        payload = parse_json(record.output_json) if record.status == 'succeeded' else None
        if record.status == 'succeeded':
            if not isinstance(payload, dict) or payload.get('input_identity') != input_hash:
                raise ValueError('mapping output input identity mismatch')
            fields = {'input_identity','plan','memory','traffic','output','validation','mac','serial_dma_cycles',
                      'serial_dma_s','known_resource_lower_bound_s'}
            if record.spec.implementation_id=='attention-mapping/v2':
                fields.add('reference_output')
            if set(payload)!=fields or ('reference_output' in fields and not isinstance(payload['reference_output'],list)):
                raise ValueError('invalid mapping output evidence schema')
            validate_saved_plan(study.workload,payload['plan'],query_tile=candidate.query_tile,
                                score_policy=candidate.score_policy,kv_layout=candidate.kv_layout)
            validate_saved_comparison(study.workload,data,payload['output'],payload['validation'],
                                      reference_output=payload.get('reference_output'),atol=study.atol,rtol=study.rtol)
            external_bytes = validate_saved_resources(study.workload,payload['plan'],payload['memory'],payload['traffic'],
                                                      scratch_capacity_bytes=study.hardware.scratch_capacity_bytes,
                                                      backing_capacity_bytes=study.hardware.backing_capacity_bytes)
            metrics = {m.name:m for m in record.metrics}
            if (set(metrics)!={'known_resource_lower_bound','external_payload','target_execution_time','target_energy'}
                    or metrics['known_resource_lower_bound'].value!=payload['known_resource_lower_bound_s']
                    or metrics['known_resource_lower_bound'].unit!='second' or metrics['known_resource_lower_bound'].kind!='lower_bound'
                    or metrics['external_payload'].value!=external_bytes
                    or metrics['external_payload'].unit!='byte' or metrics['external_payload'].kind!='counter'
                    or metrics['target_execution_time'].value is not None or metrics['target_energy'].value is not None):
                raise ValueError('mapping metrics disagree with saved observations or unknown costs')
        met = record.status == candidate.expected_status and (payload is None or payload['validation']['passed'])
        rows.append({'case': candidate.name, 'status': record.status, 'expected_status': candidate.expected_status,
                     'expectation_met': met, 'result': payload, 'diagnostic': record.diagnostic,
                     'metrics': parse_json(canonical_json(record.metrics)), 'identity_hash': record.identity_hash})
        names.add(candidate.name)
        ids.add(record.run_id)
    if names != {c.name for c in study.candidates}:
        raise ValueError('incomplete Attention mapping roster')
    return tuple(sorted(rows, key=lambda row: row['case']))


# Commit a complete immutable mapping bundle using the common checked index.
def write_study(records: tuple[RunRecord, ...], directory: str | Path) -> Path:
    return write_records(records, directory, 'attention-mapping-index/v1', summarize_records)


# Read committed mapping evidence without invoking its models or reference.
def read_study(directory: str | Path) -> tuple[RunRecord, ...]:
    return read_records(directory, 'attention-mapping-index/v1', summarize_records)
