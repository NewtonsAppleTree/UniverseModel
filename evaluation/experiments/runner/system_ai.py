"""Numerically checked AI tasks with explicit node residency, P2P/staging demand and conditional bottlenecks."""

from dataclasses import dataclass, replace
from pathlib import Path

from compiler.src.interpret.linear import execute_plan
from compiler.src.interpret.training import execute_training
from compiler.src.interpret.attention import execute_attention_plan
from compiler.src.memplan.linear import plan_memory
from compiler.src.memplan.attention import plan_attention_memory, count_attention_traffic
from compiler.src.sched.training import build_training_plan
from compiler.src.tiling.linear import build_plan
from compiler.src.tiling.attention import build_attention_plan
from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.plan.linear import TileShape
from contracts.hardware.network import finite_quantity, validate_count, validate_identity
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from contracts.workload.linear import LinearSpec, LinearInputs
from contracts.workload.training import TrainingSpec, TrainingInputs, TrainingState, TrainingResult
from contracts.workload.attention import AttentionSpec, AttentionInputs
from evaluation.experiments.runner.bundle import read_records, write_records
from evaluation.experiments.runner.single import run_experiment
from systemmodel.io.dma.model import DmaSystem, CopyBatch, CopyChain, CopyLeg
from systemmodel.io.dma.analysis import analyze_transfers, validate_transfers
from systemmodel.memory.model import MemoryObject, MemoryAllocation, MemoryRegion, MemoryPlan
from systemmodel.memory.placement import analyze_placement
from systemmodel.topology.graph import freeze_inventory
from systemmodel.topology.query import SystemPath
from workloads.kernels.linear import generate_inputs, describe_work
from workloads.graphs.training import generate_training, describe_training
from workloads.kernels.attention import generate_attention
from workloads.reference.linear import reference_linear, compare_output
from workloads.reference.training import reference_training, compare_training
from workloads.reference.attention import reference_attention, compare_attention


# Task semantics are replaceable; small deterministic inputs exercise exact compute and node-demand linkage.
@dataclass(frozen=True, slots=True, kw_only=True)
class AiTask:
    task_id: str  # Unique task identity, shared by its placement/policy comparison group.
    seed: int  # Deterministic input seed [1], uint64.
    linear: LinearSpec | None = None  # Dense Linear task; exactly one task kind is provided.
    training: TrainingSpec | None = None  # Dense MSE/SGD chain, including gradient and next-state checks.
    attention: AttentionSpec | None = None  # Attention/GQA/KV task with explicit numerical semantics.

    # Validate one professional task description without fixing its shape to the default fixture.
    def __post_init__(self) -> None:
        validate_identity('task_id',self.task_id)
        validate_count('seed',self.seed)
        if self.seed>=1<<64 or sum(v is not None for v in (self.linear,self.training,self.attention))!=1:
            raise ValueError('AI task requires uint64 seed and exactly one workload')
        for name,kind in (('linear',LinearSpec),('training',TrainingSpec),('attention',AttentionSpec)):
            if getattr(self,name) is not None and not isinstance(getattr(self,name),kind):
                raise TypeError('invalid AI workload type')


# Bandwidth/startup changes are explicit sensitivity interventions, separate from same-budget strategy comparisons.
@dataclass(frozen=True, slots=True, kw_only=True)
class AiCase:
    name: str  # Unique candidate identity.
    task_id: str  # Existing shared task.
    strategy: str  # resident, direct or staged complete input-buffer preparation.
    bandwidth_scale: float = 1.0  # Multiplicative change to one declared shared service ceiling [1], positive.
    startup_scale: int = 1  # Multiplicative DMA startup-cycle intervention [1], positive.
    expected_status: str = 'succeeded'  # Reviewed feasibility expectation.

    # Reject unsupported policies and silent invalid sensitivity parameters.
    def __post_init__(self) -> None:
        for name in ('name','task_id'):
            validate_identity(name,getattr(self,name))
        object.__setattr__(self,'bandwidth_scale',finite_quantity('bandwidth_scale',self.bandwidth_scale,positive=True))
        validate_count('startup_scale',self.startup_scale,minimum=1)
        if self.strategy not in ('resident','direct','staged') or self.expected_status not in ('succeeded','failed'):
            raise ValueError('invalid AI policy/expectation')


# Fixed memory/DMA budget and declared compute/scratch service; input copies and workspace are derived from each task.
@dataclass(frozen=True, slots=True, kw_only=True)
class AiStudy:
    system: DmaSystem  # Physical node resources and local service source.
    source_backing_id: str  # Initial remote device storage for direct/staged policies.
    target_backing_id: str  # Compute device's backing for inputs plus conservative workspace reservation.
    staging_backing_id: str  # Host backing used only by staged policy.
    shared_resource_id: str  # Declared payload ceiling changed by explicit bandwidth sensitivity cases.
    scratch_capacity_bytes: int  # Separate compute-local scratch arena [B], checked by existing compiler models.
    compute_capacity_macs_s: float  # MAC-only service ceiling [MAC/s] for target owner; scalar/softmax service remains unknown.
    compute_source_ref: str  # Compute/scratch assumption or calibration provenance.
    tasks: tuple[AiTask, ...]  # Task roster; no comparison of different tasks as a speedup.
    cases: tuple[AiCase, ...]  # Complete policies, sensitivities and infeasible tasks.

    # Require distinct input/host/compute backings and explicitly named service budgets.
    def __post_init__(self) -> None:
        if not isinstance(self.system,DmaSystem):
            raise TypeError('expected DmaSystem')
        for name in ('source_backing_id','target_backing_id','staging_backing_id','shared_resource_id','compute_source_ref'):
            validate_identity(name,getattr(self,name))
        keys = (self.source_backing_id,self.target_backing_id,self.staging_backing_id)
        if len(set(keys))!=3 or not set(keys)<={b.resource_id for b in self.system.memory.backings}:
            raise ValueError('three distinct physical backings required')
        selected = next((c for c in self.system.memory.node.topology.constraints if c.resource_id==self.shared_resource_id),None)
        if selected is None or selected.byte_basis!='payload' or selected.capacity_kind!='declared_ceiling':
            raise ValueError('sensitivity requires a declared payload service ceiling')
        validate_count('scratch_capacity_bytes',self.scratch_capacity_bytes,minimum=1)
        object.__setattr__(self,'compute_capacity_macs_s',finite_quantity('compute_capacity_macs_s',self.compute_capacity_macs_s,positive=True))
        object.__setattr__(self,'tasks',freeze_inventory('tasks',self.tasks,AiTask,'task_id'))
        object.__setattr__(self,'cases',freeze_inventory('cases',self.cases,AiCase,'name'))
        if not self.cases or {c.task_id for c in self.cases}!={t.task_id for t in self.tasks}:
            raise ValueError('cases must cover the exact nonempty task roster')


# Store actual deterministic operands/state; all strategy cases for one task use identical values and versions.
def task_inputs(task: AiTask) -> dict:
    if task.linear is not None:
        return {'operands':generate_inputs(task.linear,task.seed)}
    if task.training is not None:
        state,inputs = generate_training(task.training,task.seed)
        return {'state':state,'operands':inputs}
    return {'operands':generate_attention(task.attention,task.seed)}


# Execute mapped numerics or verify saved numerics with an independent reference; derive actual operand/backing/scratch demand.
def task_evidence(study: AiStudy, task: AiTask, inputs: dict, saved: dict | None = None) -> dict:
    tile = TileShape(m=2,n=2,k=2)
    scratch = study.scratch_capacity_bytes
    cap = next(b.capacity_bytes for b in study.system.memory.backings if b.resource_id==study.target_backing_id)
    if task.linear is not None:
        spec = task.linear
        data = resolve_dataclass(LinearInputs,parse_json(canonical_json(inputs['operands'])))
        work = describe_work(spec)
        if work.macs>1_000_000:
            raise ValueError('task exceeds bounded numerical reference')
        plan = build_plan(spec,tile,'output_stationary')
        local = plan_memory(spec,plan,scratch)
        actual = execute_plan(spec,data,plan,scratch) if saved is None else tuple(saved['actual'])
        validation = {'output':compare_output(spec,actual,reference_linear(spec,data))}
        input_bytes,backing_bytes,macs,scratch_bytes = work.a_bytes+work.b_bytes,work.a_bytes+work.b_bytes+work.output_bytes,work.macs,local.allocation_bytes
        compiler_peak = backing_bytes
    elif task.training is not None:
        spec = task.training
        data = resolve_dataclass(TrainingInputs,parse_json(canonical_json(inputs['operands'])))
        state = resolve_dataclass(TrainingState,parse_json(canonical_json(inputs['state'])))
        plan = build_training_plan(spec,tile,'output_stationary',scratch_capacity_bytes=scratch,backing_capacity_bytes=cap)
        actual = (execute_training(spec,state,data,0.125,tile,'output_stationary',scratch_capacity_bytes=scratch,backing_capacity_bytes=cap)[0]
                  if saved is None else resolve_dataclass(TrainingResult,saved['actual']))
        validation = compare_training(actual,reference_training(spec,state,data,0.125))
        input_bytes = 8*(len(data.x)+len(data.target)+sum(len(w) for w in state.weights))
        # Retained packed inputs cannot reuse dead input slots; reserve every noninitial tensor as separate workspace.
        backing_bytes = input_bytes+sum(t.rows*t.columns*8 for t in plan.tensors if not t.initial)
        compiler_peak,macs = plan.memory.peak_bytes,describe_training(spec).gemm_macs
        scratch_bytes = max((op.scratch.allocation_bytes for op in plan.operations if op.scratch is not None),default=0)
    else:
        spec = task.attention
        data = resolve_dataclass(AttentionInputs,parse_json(canonical_json(inputs['operands'])))
        plan = build_attention_plan(spec,query_tile=1,score_policy='fused',kv_layout='shared')
        local = plan_attention_memory(spec,plan,scratch_capacity_bytes=scratch,backing_capacity_bytes=cap)
        traffic = count_attention_traffic(spec,plan)
        actual = (execute_attention_plan(spec,data,plan,scratch_capacity_bytes=scratch,backing_capacity_bytes=cap)
                  if saved is None else tuple(saved['actual']))
        validation = {'output':compare_attention(spec,data,actual,reference_attention(spec,data))}
        input_bytes,backing_bytes,scratch_bytes = 8*(len(data.q)+len(data.k)+len(data.v)),local.backing_bytes,local.scratch_bytes
        compiler_peak = backing_bytes
        macs = traffic.qk_macs+traffic.av_macs
    if not all(v.passed for v in validation.values()):
        raise ValueError('AI numerical quality/correctness validation failed')
    return {'input_identity':content_hash((task,inputs)),'actual':actual,'validation':validation,
            'input_bytes':input_bytes,'backing_peak_bytes':max(backing_bytes,input_bytes),'compiler_backing_peak_bytes':compiler_peak,'scratch_bytes':scratch_bytes,'macs':macs,
            'quality_scope':'Synthetic operator/gradient/state correctness only; not dataset accuracy or end-to-end model quality'}


# Derive and record the exact single-resource and startup interventions; unchanged cases retain original hardware identity.
def case_hardware(study: AiStudy, case: AiCase) -> DmaSystem:
    system = study.system
    if case.bandwidth_scale!=1:
        topology = system.memory.node.topology
        constraints = tuple(replace(c,capacity_Bps=c.capacity_Bps*case.bandwidth_scale,source_ref=c.source_ref+f';scale={case.bandwidth_scale}') if c.resource_id==study.shared_resource_id else c for c in topology.constraints)
        system = replace(system,memory=replace(system.memory,node=replace(system.memory.node,topology=replace(topology,constraints=constraints))))
    if case.startup_scale!=1:
        system = replace(system,engines=tuple(replace(e,params=replace(e.params,startup_cycles=e.params.startup_cycles*case.startup_scale),source_ref=e.source_ref+f';startup_scale={case.startup_scale}') for e in system.engines))
    return system


# Reserve packed input copies and conservative compute workspace, with full-buffer staging only for the staged policy.
def map_task(study: AiStudy, case: AiCase, evidence: dict) -> tuple[DmaSystem, MemoryPlan, CopyBatch | None]:
    system = case_hardware(study,case)
    backings = {b.resource_id:b for b in system.memory.backings}
    size = evidence['input_bytes']
    objects = [MemoryObject(object_id='task.inputs',size_bytes=size,source_ref=evidence['input_identity'])]
    locations = [('target',study.target_backing_id)]
    if case.strategy!='resident':
        locations.append(('source',study.source_backing_id))
    if case.strategy=='staged':
        locations.append(('staging',study.staging_backing_id))
    allocations,regions = [],[]
    for name,backing in locations:
        allocations.append(MemoryAllocation(allocation_id=name,object_id='task.inputs',backing_id=backing,offset_bytes=0,begin_phase=0,end_phase=3))
        regions.append(MemoryRegion(region_id=name,allocation_id=name,access_port_id=backings[backing].access_port_ids[0],base_address=4096,object_offset_bytes=0,length_bytes=size,permissions=('read','write')))
    extra = evidence['backing_peak_bytes']-size
    if extra:
        granule = backings[study.target_backing_id].allocation_granule_bytes
        objects.append(MemoryObject(object_id='task.workspace',size_bytes=extra,source_ref='derived:conservative-task-peak-minus-inputs/v1'))
        allocations.append(MemoryAllocation(allocation_id='workspace',object_id='task.workspace',backing_id=study.target_backing_id,offset_bytes=((size+granule-1)//granule)*granule,begin_phase=0,end_phase=3))
    plan = MemoryPlan(memory_identity=system.memory.identity_hash,objects=tuple(objects),allocations=tuple(allocations),regions=tuple(regions),source_ref='derived:complete-input-copy-and-workspace/v1')
    analyze_placement(system.memory,plan)
    batch = None
    if case.strategy!='resident':
        sequence = ('source','staging','target') if case.strategy=='staged' else ('source','target')
        lookup = dict(locations)
        legs = []
        for i,(src,dst) in enumerate(zip(sequence,sequence[1:])):
            engines = [e for e in system.engines if lookup[src] in e.read_backing_ids]
            if len(engines)!=1:
                raise ValueError('explicit fixture requires one source engine per backing')
            legs.append(CopyLeg(leg_id=f'prepare.{i}',engine_id=engines[0].resource_id,source_region_id=src,source_address=4096,target_region_id=dst,target_address=4096))
        batch = CopyBatch(placement=plan,phase=1,chains=(CopyChain(chain_id='prepare',payload_bytes=size,legs=tuple(legs)),),source_ref='derived:input-preparation/v1')
    return system,plan,batch


# Link checked task values to exact byte demand and node work; compute and transfer ceilings are necessary bounds only.
def analyze_ai(study: AiStudy, case: AiCase, inputs: dict, saved: dict | None = None) -> dict:
    task = next(t for t in study.tasks if t.task_id==case.task_id)
    evidence = task_evidence(study,task,inputs,None if saved is None else saved['task'])
    system,plan,batch = map_task(study,case,evidence)
    transfer = None
    if batch is not None:
        transfer = (analyze_transfers(system,batch) if saved is None else validate_transfers(system,batch,
                    tuple(resolve_dataclass(SystemPath,l['path']) for l in saved['transfer']['legs'])))
    compute = finite_quantity('MAC necessary time',evidence['macs']/study.compute_capacity_macs_s,positive=True)
    movement = 0.0 if transfer is None else transfer.bounds.lower_bound_s
    limits = [('compute.mac',compute)]+([] if transfer is None else [(c.resource_id,c.lower_bound_s) for c in transfer.contributions])
    if transfer is not None:
        limits.append(('preparation.dependencies',transfer.bounds.critical_path_s))
    maximum = max(v for _,v in limits)
    return {'task':evidence,'hardware_identity':system.identity_hash,'placement':plan,'placement_analysis':analyze_placement(system.memory,plan),
            'transfer':transfer,'copied_bytes':0 if transfer is None else sum(l.traffic.payload_bytes for l in transfer.legs),
            'compute_lower_bound_s':compute,'transfer_lower_bound_s':movement,'known_service_lower_bound_s':max(compute,movement),
            'bottleneck_resource_ids':tuple(key for key,value in limits if value==maximum),
            'unknown_costs':('Resident inputs assumed already present; direct/staged comparison includes full input preparation only',
                             'Separate compute-local scratch; conservative backing peak reservation, no automatic allocator or live scheduling',
                             'Numerical interpreter does not execute physical copies; scalar/softmax, backing/internal supply, output return, visibility and total energy unknown')}


# Record meaningful work and correctness without labeling a partial service bound as end-to-end performance.
def _metrics(result: dict) -> tuple[Metric, ...]:
    return (Metric(name='input_bytes',value=result['task']['input_bytes'],unit='byte',kind='counter'),
            Metric(name='copied_bytes',value=result['copied_bytes'],unit='byte',kind='counter'),
            Metric(name='known_service_lower_bound',value=result['known_service_lower_bound_s'],unit='second',kind='lower_bound'),
            Metric(name='target_execution_time',value=None,unit='second',kind='estimated',unknown_reason='Partial MAC/preparation evidence; no complete execution schedule'),
            Metric(name='target_energy',value=None,unit='joule',kind='estimated',unknown_reason='No calibrated complete node energy'))


# Produce mapped numerical and node evidence for one candidate.
def _evaluate(config: dict, inputs: dict) -> tuple[dict, tuple[Metric, ...]]:
    case = next(c for c in config['study'].cases if c.name==config['selected'])
    result = analyze_ai(config['study'],case,inputs)
    return result,_metrics(result)


# Save actual input tensors/state and full common budget for every successful or failed candidate.
def run_study(study: AiStudy, *, source_revision: str = 'unrecorded') -> tuple[RunRecord, ...]:
    tasks = {t.task_id:t for t in study.tasks}
    return tuple(run_experiment(ExperimentSpec(experiment_id=case.name,implementation_id='system-ai-study/v1',mode='analytical',source_revision=source_revision,
        assumptions=('Functional AI numerics with independent reference; exact packed inputs bind static node placement/copies',
                     'Same task and base hardware; bandwidth/startup interventions explicit, residency changes input-preparation preconditions',
                     'No complete performance/energy, dataset accuracy or coherent data movement claim')),
        {'study':study,'selected':case.name},task_inputs(tasks[case.task_id]),_evaluate) for case in study.cases)


# Replay saved actual numerics against independent references and saved DMA routes without mapped execution or a new search.
def summarize_records(records: tuple[RunRecord, ...]) -> tuple[dict, ...]:
    if not records or any(not isinstance(r,RunRecord) for r in records):
        raise ValueError('expected complete AI records')
    common,names,ids,rows = None,set(),set(),[]
    for record in records:
        if (record.spec.implementation_id,record.spec.mode)!=('system-ai-study/v1','analytical'):
            raise ValueError('wrong AI record kind')
        config,inputs = parse_json(record.configuration_json),parse_json(record.inputs_json)
        if not isinstance(config,dict) or set(config)!={'study','selected'} or not isinstance(inputs,dict):
            raise ValueError('invalid AI snapshot')
        study = resolve_dataclass(AiStudy,config['study'])
        digest = content_hash((study,record.spec.source_revision,record.spec.assumptions))
        if common is not None and common!=digest:
            raise ValueError('mixed AI source/budget/roster')
        common = digest
        case = next((c for c in study.cases if c.name==config['selected']),None)
        if case is None or case.name!=record.spec.experiment_id or case.name in names or record.run_id in ids:
            raise ValueError('invalid AI selection identity')
        task = next(t for t in study.tasks if t.task_id==case.task_id)
        if canonical_json(task_inputs(task))!=canonical_json(inputs):
            raise ValueError('actual input tensors/state differ from declared deterministic task')
        payload = parse_json(record.output_json) if record.status=='succeeded' else None
        if record.status=='succeeded':
            try:
                if not isinstance(payload,dict):
                    raise ValueError('missing AI observations')
                checked = analyze_ai(study,case,inputs,payload)
            except (KeyError,TypeError,IndexError,StopIteration,AttributeError) as exc:
                raise ValueError('malformed saved AI evidence') from exc
            if canonical_json(checked)!=canonical_json(payload) or canonical_json(sorted(_metrics(checked),key=lambda m:m.name))!=canonical_json(sorted(record.metrics,key=lambda m:m.name)):
                raise ValueError('AI numerical/work/path/metric observations disagree')
        rows.append({'case':case.name,'task_id':case.task_id,'strategy':case.strategy,'bandwidth_scale':case.bandwidth_scale,'startup_scale':case.startup_scale,
                     'status':record.status,'expected_status':case.expected_status,'expectation_met':record.status==case.expected_status,
                     'result':payload,'diagnostic':record.diagnostic,'identity_hash':record.identity_hash})
        names.add(case.name)
        ids.add(record.run_id)
    if names!={c.name for c in study.cases}:
        raise ValueError('incomplete AI roster')
    return tuple(sorted(rows,key=lambda r:r['case']))


# Save one verified complete task/policy/sensitivity study without overwriting previous evidence.
def write_study(records: tuple[RunRecord, ...], directory: str | Path) -> Path:
    return write_records(records,directory,'system-ai-index/v1',summarize_records)


# Recover records and recheck independent numeric/static evidence, retaining prior failure diagnostics.
def read_study(directory: str | Path) -> tuple[RunRecord, ...]:
    return read_records(directory,'system-ai-index/v1',summarize_records)
