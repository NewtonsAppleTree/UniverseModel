"""Complete static memory-placement/access studies with immutable evidence and route-only readback."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.hardware.network import validate_identity
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from evaluation.experiments.runner.bundle import read_records, write_records
from evaluation.experiments.runner.single import run_experiment
from systemmodel.memory.access import MemoryAccessRequest, analyze_access, validate_access
from systemmodel.memory.model import MemoryPlan, MemorySystem
from systemmodel.memory.placement import analyze_placement
from systemmodel.topology.graph import freeze_inventory


# Each case declares one complete candidate placement and optionally one live address-access question.
@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryCase:
    name: str  # Unique identity in the complete finite study.
    plan: MemoryPlan  # Full demand/copies/views; infeasibility is recorded by execution.
    request: MemoryAccessRequest | None = None  # None checks placement only, without any path claim.
    expected_status: Literal['succeeded','failed'] = 'succeeded'  # Reviewed fixture expectation, not evidence by itself.

    # Reject malformed case types while retaining infeasible cross-resource declarations for failure records.
    def __post_init__(self) -> None:
        validate_identity('name',self.name)
        if not isinstance(self.plan,MemoryPlan) or (self.request is not None and not isinstance(self.request,MemoryAccessRequest)):
            raise TypeError('invalid memory case plan/request')
        if self.expected_status not in ('succeeded','failed'):
            raise ValueError('invalid memory case expected status')


# One sourced memory system is shared by all cases; task/budget equivalence must be stated per comparison.
@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryStudy:
    memory: MemorySystem  # Fixed resource ownership, capacity, topology and NUMA placement.
    cases: tuple[MemoryCase, ...]  # Complete roster including negative controls and placement-only cases.
    schema_version: Literal['system-memory-study/v1'] = 'system-memory-study/v1'  # Static analysis evidence.

    # Freeze a nonempty unique roster before any case executes.
    def __post_init__(self) -> None:
        if not isinstance(self.memory,MemorySystem) or self.schema_version!='system-memory-study/v1':
            raise ValueError('invalid memory study/schema')
        object.__setattr__(self,'cases',freeze_inventory('cases',self.cases,MemoryCase,'name'))
        if not self.cases:
            raise ValueError('memory study requires cases')


# Counters describe static work only; separate backing peaks are never added into a false node occupancy.
def _metrics(plan: MemoryPlan, access) -> tuple[Metric, ...]:
    counters = [('allocation_count',len(plan.allocations)),('region_count',len(plan.regions))]
    if access is not None:
        counters.append(('path_hops',len(access.path.link_ids)))
    return tuple(Metric(name=name,value=value,unit='one',kind='counter') for name,value in counters)+(
        Metric(name='target_execution_time',value=None,unit='second',kind='estimated',
               unknown_reason='Static placement/request reachability only; no response, service, queue or execution'),
        Metric(name='target_energy',value=None,unit='joule',kind='estimated',
               unknown_reason='No physical access/transfer action or calibrated energy model'))


# Compute capacity/mapping first, then optional access; failed cases retain diagnostics rather than fabricated partial metrics.
def _evaluate(config: dict, inputs: dict) -> tuple[dict, tuple[Metric, ...]]:
    memory,plan,request = config['study'].memory,inputs['plan'],inputs['request']
    access = analyze_access(memory,plan,request) if request is not None else None
    placement = access.placement if access is not None else analyze_placement(memory,plan)
    return {'placement':placement,'access':access},_metrics(plan,access)


# Snapshot the full hardware/roster and preserve every success or failure independently of fixture expectations.
def run_study(study: MemoryStudy, *, source_revision: str = 'unrecorded') -> tuple[RunRecord, ...]:
    if not isinstance(study,MemoryStudy):
        raise TypeError('expected MemoryStudy')
    records = []
    for case in study.cases:
        spec = ExperimentSpec(experiment_id=case.name,implementation_id='system-memory-study/v1',mode='analytical',
                              source_revision=source_revision,assumptions=(
                                  'Complete object copies reserve rounded physical intervals; views alias copies without extra capacity',
                                  'Half-open logical phase lifetimes are declarations, not execution schedules or elapsed time',
                                  'NUMA labels are explicit placement; reachability checks request permissions only',
                                  'No contents, translation service, coherence, read response, target latency/energy or task-quality claim'))
        records.append(run_experiment(spec,{'study':study,'selected':case.name},{'plan':case.plan,'request':case.request},_evaluate))
    return tuple(records)


# Recheck static intervals/mappings/locality and the saved explicit route; do not invoke the producer or search for paths.
def summarize_records(records: tuple[RunRecord, ...]) -> tuple[dict, ...]:
    if not records or any(not isinstance(r,RunRecord) for r in records):
        raise ValueError('expected nonempty memory study records')
    common,names,ids,rows = None,set(),set(),[]
    for record in records:
        if (record.spec.implementation_id,record.spec.mode)!=('system-memory-study/v1','analytical'):
            raise ValueError('wrong memory record kind')
        config,inputs = parse_json(record.configuration_json),parse_json(record.inputs_json)
        if not isinstance(config,dict) or set(config)!={'study','selected'} or not isinstance(inputs,dict) or set(inputs)!={'plan','request'}:
            raise ValueError('invalid memory record snapshot schema')
        study = resolve_dataclass(MemoryStudy,config['study'])
        digest = content_hash((study,record.spec.source_revision,record.spec.assumptions))
        if common is not None and digest!=common:
            raise ValueError('mixed memory study/source/assumptions')
        common = digest
        case = next((c for c in study.cases if c.name==config['selected']),None)
        if case is None or case.name!=record.spec.experiment_id or case.name in names or record.run_id in ids:
            raise ValueError('duplicate or invalid memory case identity')
        if canonical_json({'plan':case.plan,'request':case.request})!=canonical_json(inputs):
            raise ValueError('memory case/input mismatch')
        payload = parse_json(record.output_json) if record.status=='succeeded' else None
        if record.status=='succeeded':
            if not isinstance(payload,dict) or set(payload)!={'placement','access'}:
                raise ValueError('invalid memory result schema')
            access = None
            if case.request is not None:
                saved = payload['access']
                if not isinstance(saved,dict) or not isinstance(saved.get('path'),dict) or 'link_ids' not in saved['path']:
                    raise ValueError('missing saved memory access route')
                access = validate_access(study.memory,case.plan,case.request,saved['path']['link_ids'])
            placement = access.placement if access is not None else analyze_placement(study.memory,case.plan)
            if canonical_json(payload)!=canonical_json({'placement':placement,'access':access}):
                raise ValueError('saved memory observations disagree with static declarations')
            if canonical_json(sorted(record.metrics,key=lambda m:m.name))!=canonical_json(sorted(_metrics(case.plan,access),key=lambda m:m.name)):
                raise ValueError('memory metrics disagree with counters/unknown costs')
        rows.append({'case':case.name,'status':record.status,'expected_status':case.expected_status,
                     'expectation_met':record.status==case.expected_status,'result':payload,'diagnostic':record.diagnostic,
                     'identity_hash':record.identity_hash})
        names.add(case.name)
        ids.add(record.run_id)
    if names!={case.name for case in study.cases}:
        raise ValueError('incomplete memory study roster')
    return tuple(sorted(rows,key=lambda row:row['case']))


# Commit checked immutable records and their manifest once; do not overwrite prior research evidence.
def write_study(records: tuple[RunRecord, ...], directory: str | Path) -> Path:
    return write_records(records,directory,'system-memory-index/v1',summarize_records)


# Validate saved data and declared static semantics only; failure diagnostics remain observations, not rerun proofs.
def read_study(directory: str | Path) -> tuple[RunRecord, ...]:
    return read_records(directory,'system-memory-index/v1',summarize_records)
