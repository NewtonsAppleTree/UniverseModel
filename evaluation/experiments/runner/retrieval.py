"""Real-data RBF attention quality protocol, independent external baselines and reproducible held-out evidence."""

from pathlib import Path
from math import isfinite

from compiler.src.interpret.attention import execute_attention_plan
from compiler.src.memplan.attention import count_attention_traffic, plan_attention_memory
from compiler.src.tiling.attention import build_attention_plan
from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from contracts.workload.classification import ClassificationData
from contracts.workload.attention import AttentionInputs, AttentionSpec, attention_identity
from evaluation.calibration.numpy_attention import numpy_attention, numpy_environment, numpy_rbf
from evaluation.experiments.runner.bundle import read_records, write_records
from evaluation.experiments.runner.attention_evidence import validate_saved_comparison, validate_saved_plan, validate_saved_resources
from evaluation.experiments.runner.single import run_experiment
from workloads.datasets.tabular import load_classification
from workloads.graphs.retrieval import RetrievalState, fit_retrieval, retrieval_attention, retrieval_vectors, select_retrieval_scale, stratified_split
from workloads.profiles.retrieval import RetrievalProfile
from workloads.reference.attention import compare_attention, reference_attention
from workloads.reference.classification import classification_gate, classification_metrics


# Prepare actual source data/model/selection once per seed; no held-out test label participates in fitting or selection.
def prepare_retrieval(profile: RetrievalProfile, data: ClassificationData, seed: int) -> dict:
    if seed not in profile.seeds or data.source_sha256!=profile.source.sha256:
        raise ValueError('retrieval seed/source mismatch')
    split = stratified_split(data,seed=seed,train_per_class=profile.train_per_class,validation_per_class=profile.validation_per_class)
    state = fit_retrieval(data,split)
    selected,scores = select_retrieval_scale(state,data,profile.scale_candidates,max_macs=profile.max_macs,max_score_pairs=profile.max_score_pairs)
    return {'data':data,'state':state,'selected_scale':selected,'validation_scores':scores,'error':None}


# Compare actual mapped arithmetic to the oracle, then evaluate held-out task quality and optional two-form NumPy evidence.
def evaluate_retrieval(config: dict, prepared: dict) -> tuple[dict, tuple[Metric, ...]]:
    if prepared['error'] is not None:
        raise ValueError(prepared['error'])
    if config['external_environment'].get('error') is not None:
        raise ValueError(config['external_environment']['error'])
    profile = config['profile']
    variant = next(v for v in profile.variants if v.name==config['variant'])
    state,data,scale = prepared['state'],prepared['data'],prepared['selected_scale']
    queries = tuple(data.features[i] for i in state.split.test)
    truth = tuple(data.labels[i] for i in state.split.test)
    spec,inputs = retrieval_attention(state,queries,scale=scale,key_decimals=variant.key_decimals)
    plan = build_attention_plan(spec,query_tile=profile.query_tile)
    capacities = {'scratch_capacity_bytes':profile.scratch_capacity_bytes,'backing_capacity_bytes':profile.backing_capacity_bytes}
    output = execute_attention_plan(spec,inputs,plan,**capacities,max_macs=profile.max_macs)
    reference = reference_attention(spec,inputs,max_macs=profile.max_macs,max_score_pairs=profile.max_score_pairs)
    numerical = compare_attention(spec,inputs,output,reference)
    metrics = classification_metrics(output,truth,state.classes)
    base_spec,base_inputs = retrieval_attention(state,queries,scale=scale)
    base_output = reference_attention(base_spec,base_inputs,max_macs=profile.max_macs,max_score_pairs=profile.max_score_pairs).output
    baseline = classification_metrics(base_output,truth,state.classes)
    external = None
    if config['external_environment']['backend']!='none':
        direct = numpy_attention(spec,inputs)
        q,k = retrieval_vectors(state,queries,variant.key_decimals)
        rbf = numpy_rbf(q,k,state.labels,state.classes,scale)
        external = {'attention_output':direct,'rbf_output':rbf,
                    'attention_validation':compare_attention(spec,inputs,direct,reference),
                    'rbf_validation':compare_attention(spec,inputs,rbf,reference),
                    'rbf_metrics':classification_metrics(rbf,truth,state.classes)}
    quality,delta = classification_gate(metrics,baseline,minimum_accuracy=profile.minimum_accuracy,maximum_accuracy_drop=profile.maximum_accuracy_drop)
    return {'model_identity':state.identity_hash,'data_identity':data.identity_hash,'selected_scale':scale,
            'attention_spec':spec,'attention_inputs':inputs,'input_identity':attention_identity(spec,inputs),'plan':plan,'memory':plan_attention_memory(spec,plan,**capacities),
            'traffic':count_attention_traffic(spec,plan),'probabilities':output,'reference_output':reference.output,'truth':truth,'numerical':numerical,
            'metrics':metrics,'baseline_metrics':baseline,'baseline_probabilities':base_output,'accuracy_delta':delta,'quality_passed':quality,
            'prediction_changes':sum(a!=b for a,b in zip(metrics.predictions,baseline.predictions)),
            'external':external}, (Metric(name='test_accuracy',value=metrics.accuracy,unit='one',kind='counter'),
                                   Metric(name='target_execution_time',value=None,unit='second',kind='estimated',unknown_reason='Task-quality experiment; no complete target execution'),
                                   Metric(name='target_energy',value=None,unit='joule',kind='estimated',unknown_reason='No physical cost profile for preprocessing, mapping and scalar work'))


# Retain every split/variant including data/selection/tool failures; the optional backend version is part of configuration identity.
def run_study(profile: RetrievalProfile, *, data_root: str | Path, source_revision: str = 'unrecorded',
              numpy_reference: bool = False) -> tuple[RunRecord, ...]:
    if not isinstance(profile,RetrievalProfile) or type(numpy_reference) is not bool:
        raise TypeError('invalid retrieval profile/backend selection')
    environment = {'backend':'none'}
    if numpy_reference:
        try:
            environment = numpy_environment()
        except ImportError as exc:
            environment = {'backend':'numpy-attention/v1','error':f'{type(exc).__name__}: {exc}'}
    data,error = None,None
    try:
        data = load_classification(profile.source,data_root,max_samples=profile.max_samples,max_file_bytes=profile.max_file_bytes)
    except (ValueError,TypeError,OSError) as exc:
        error = f'{type(exc).__name__}: {exc}'
    records = []
    for seed in profile.seeds:
        prepared = {'data':data,'state':None,'selected_scale':None,'validation_scores':None,'error':error}
        if error is None:
            try:
                prepared = prepare_retrieval(profile,data,seed)
            except (ValueError,TypeError,ArithmeticError) as exc:
                prepared['error'] = f'{type(exc).__name__}: {exc}'
        for variant in profile.variants:
            spec = ExperimentSpec(experiment_id=f'seed{seed}:{variant.name}',implementation_id='retrieval-quality/v2',mode='functional',source_revision=source_revision,
                                  assumptions=('Real finite tabular classification; not language-model, serving or population-generalization evidence',
                                               'Stratified fixed split; train-only standardization; first best validation-accuracy scale; test labels only for reporting',
                                               'RBF attention; support-coordinate decimal rounding stays binary64 and does not imply packed capacity/speed gains',
                                               'Repeated splits reuse observations; accuracy ranges are descriptive and not independent-sample confidence intervals',
                                               'Numerical correctness, held-out task quality and target costs are separate outcomes'))
            config = {'profile':profile,'seed':seed,'variant':variant.name,'external_environment':environment}
            records.append(run_experiment(spec,config,prepared,evaluate_retrieval))
    return tuple(records)


# Check saved validation predictions/counts against validation labels; selection never reads test accuracy.
def _validate_selection(profile: RetrievalProfile, data: ClassificationData, state: RetrievalState, prepared: dict) -> None:
    table = prepared['validation_scores']
    if (not isinstance(table,list) or len(table)!=len(profile.scale_candidates)
            or any(not isinstance(entry,list) or len(entry)!=2 for entry in table)
            or [entry[0] for entry in table]!=list(profile.scale_candidates)):
        raise ValueError('incomplete validation scale table')
    truth = tuple(data.labels[i] for i in state.split.validation)
    for _,metrics in table:
        if not isinstance(metrics,dict) or not isinstance(metrics.get('predictions'),list):
            raise ValueError('invalid validation metrics')
        predictions = metrics['predictions']
        if len(predictions)!=len(truth) or any(type(p) is not int or not 0<=p<state.classes for p in predictions):
            raise ValueError('invalid validation predictions')
        counts = classification_metrics(tuple(float(p==j) for p in predictions for j in range(state.classes)),truth,state.classes)
        expected = parse_json(canonical_json(counts))
        if set(metrics)!=set(expected) or any(metrics[k]!=expected[k] for k in ('samples','correct','accuracy','confusion','predictions')):
            raise ValueError('validation metrics disagree with labels/predictions')
        loss,clipped = metrics['mean_log_loss'],metrics['clipped_samples']
        if (type(loss) not in (int,float) or not isfinite(loss) or loss<0 or type(clipped) is not int
                or not 0<=clipped<=len(truth) or metrics['probability_floor']!=counts.probability_floor):
            raise ValueError('invalid validation log-loss observations')
    if table[max(range(len(table)),key=lambda i:table[i][1]['correct'])][0]!=prepared['selected_scale']:
        raise ValueError('scale was not selected by the declared validation rule')


# Summarize complete paired cases without fitting/selection/reference or external-data access; validate recorded metrics from observations.
def summarize_records(records: tuple[RunRecord, ...]) -> tuple[dict, ...]:
    if not records or any(not isinstance(r,RunRecord) for r in records):
        raise ValueError('expected nonempty retrieval records')
    common,identities,ids,rows,seed_inputs = None,set(),set(),[],{}
    data_identity,baselines = None,{}
    for record in records:
        if record.spec.implementation_id not in ('retrieval-quality/v1','retrieval-quality/v2') or record.spec.mode!='functional':
            raise ValueError('invalid retrieval record kind')
        config = parse_json(record.configuration_json)
        if not isinstance(config,dict) or set(config)!={'profile','seed','variant','external_environment'}:
            raise ValueError('invalid retrieval config snapshot')
        profile = resolve_dataclass(RetrievalProfile,config['profile'])
        environment = config['external_environment']
        if not isinstance(environment,dict) or environment.get('backend') not in ('none','numpy-attention/v1'):
            raise ValueError('invalid retrieval external environment')
        digest = content_hash((config['profile'],environment,record.spec.implementation_id,record.spec.source_revision,record.spec.assumptions))
        if common is not None and common!=digest:
            raise ValueError('mixed retrieval profile/source/backend')
        common = digest
        seed,variant = config['seed'],next((v for v in profile.variants if v.name==config['variant']),None)
        if type(seed) is not int or seed not in profile.seeds or variant is None or record.spec.experiment_id!=f'seed{seed}:{variant.name}' or record.spec.experiment_id in identities or record.run_id in ids:
            raise ValueError('invalid or duplicate retrieval case')
        if seed in seed_inputs and seed_inputs[seed]!=record.inputs_json:
            raise ValueError('paired variants must share the same fitted state/input')
        seed_inputs[seed] = record.inputs_json
        prepared = parse_json(record.inputs_json)
        if not isinstance(prepared,dict) or set(prepared)!={'data','state','selected_scale','validation_scores','error'}:
            raise ValueError('invalid retrieval input snapshot')
        if prepared['data'] is not None:
            data = resolve_dataclass(ClassificationData,prepared['data'])
            if data.source_sha256!=profile.source.sha256:
                raise ValueError('retrieval source identity mismatch')
            if data_identity is not None and data_identity!=data.identity_hash:
                raise ValueError('different source observations across retrieval seeds')
            data_identity = data.identity_hash
        elif prepared['error'] is None:
            raise ValueError('missing retrieval dataset requires a preparation error')
        if prepared['error'] is not None and (record.status!='failed' or type(prepared['error']) is not str or not prepared['error']):
            raise ValueError('invalid preparation failure')
        payload = parse_json(record.output_json) if record.status=='succeeded' else None
        met = False
        if record.status=='succeeded':
            fields = {'model_identity','data_identity','selected_scale','attention_spec','attention_inputs','input_identity','plan','memory',
                      'traffic','probabilities','truth','numerical','metrics','baseline_metrics','baseline_probabilities','accuracy_delta',
                      'quality_passed','prediction_changes','external'}
            if record.spec.implementation_id=='retrieval-quality/v2':
                fields.add('reference_output')
            if not isinstance(payload,dict) or set(payload)!=fields or ('reference_output' in fields and not isinstance(payload['reference_output'],list)):
                raise ValueError('invalid retrieval output evidence schema')
            if environment.get('error') is not None:
                raise ValueError('successful retrieval cannot have an external backend error')
            state = resolve_dataclass(RetrievalState,prepared['state'])
            if state.data_identity!=data.identity_hash or state.split.seed!=seed or not isinstance(payload,dict) or payload.get('model_identity')!=state.identity_hash or payload.get('data_identity')!=data.identity_hash:
                raise ValueError('retrieval model/data identity mismatch')
            if set((*state.split.train,*state.split.validation,*state.split.test))!=set(range(len(data.labels))):
                raise ValueError('retrieval split incomplete')
            if (state.classes!=len(data.class_names) or len(state.means)!=len(data.feature_names)
                    or state.labels!=tuple(data.labels[i] for i in state.split.train)):
                raise ValueError('retrieval state dimensions/labels disagree with source')
            for partition,quota in ((state.split.train,profile.train_per_class),(state.split.validation,profile.validation_per_class)):
                if any(sum(data.labels[i]==label for i in partition)!=quota for label in range(state.classes)):
                    raise ValueError('retrieval split class quotas disagree with profile')
            _validate_selection(profile,data,state,prepared)
            attention_spec = resolve_dataclass(AttentionSpec,payload['attention_spec'])
            attention_inputs = resolve_dataclass(AttentionInputs,payload['attention_inputs'])
            if payload['input_identity']!=attention_identity(attention_spec,attention_inputs) or payload['plan']['workload_hash']!=attention_spec.identity_hash:
                raise ValueError('retrieval Attention input/plan identity mismatch')
            expected_spec = AttentionSpec(batch_size=1,query_heads=1,kv_heads=1,query_length=len(state.split.test),
                                          kv_length=len(state.labels),key_dim=len(state.means)+2,value_dim=state.classes,scale=prepared['selected_scale'])
            if attention_spec!=expected_spec or attention_inputs.v!=tuple(float(label==j) for label in state.labels for j in range(state.classes)):
                raise ValueError('retrieval Attention semantics disagree with fitted state/scale')
            validate_saved_plan(attention_spec,payload['plan'],query_tile=profile.query_tile)
            validate_saved_comparison(attention_spec,attention_inputs,payload['probabilities'],payload['numerical'],reference_output=payload.get('reference_output'))
            validate_saved_resources(attention_spec,payload['plan'],payload['memory'],payload['traffic'],
                                     scratch_capacity_bytes=profile.scratch_capacity_bytes,backing_capacity_bytes=profile.backing_capacity_bytes)
            truth = tuple(data.labels[i] for i in state.split.test)
            observed = classification_metrics(payload['probabilities'],truth,state.classes)
            if payload['truth']!=list(truth) or canonical_json(observed)!=canonical_json(payload['metrics']) or payload['selected_scale']!=prepared['selected_scale']:
                raise ValueError('retrieval metrics/scale disagree with observations')
            baseline = classification_metrics(payload['baseline_probabilities'],truth,state.classes)
            if canonical_json(baseline)!=canonical_json(payload['baseline_metrics']):
                raise ValueError('baseline metrics disagree with observations')
            if seed in baselines and baselines[seed]!=payload['baseline_probabilities']:
                raise ValueError('paired retrieval baselines differ')
            baselines[seed] = payload['baseline_probabilities']
            quality,delta = classification_gate(observed,baseline,minimum_accuracy=profile.minimum_accuracy,maximum_accuracy_drop=profile.maximum_accuracy_drop)
            if type(payload['quality_passed']) is not bool or payload['quality_passed']!=quality or payload['accuracy_delta']!=delta:
                raise ValueError('retrieval quality gate mismatch')
            changes = sum(a!=b for a,b in zip(observed.predictions,baseline.predictions))
            if type(payload['prediction_changes']) is not int or payload['prediction_changes']!=changes:
                raise ValueError('retrieval prediction-change count disagrees with observations')
            metrics = {m.name:m for m in record.metrics}
            if (set(metrics)!={'test_accuracy','target_execution_time','target_energy'} or metrics['test_accuracy'].value!=observed.accuracy
                    or metrics['test_accuracy'].unit!='one' or metrics['test_accuracy'].kind!='counter'
                    or metrics['target_execution_time'].value is not None or metrics['target_energy'].value is not None):
                raise ValueError('retrieval record metrics disagree with observations or unknown costs')
            met = payload['numerical']['passed'] and quality==variant.expected_quality
            if environment['backend']=='none':
                if payload['external'] is not None:
                    raise ValueError('unexpected external reference evidence')
            else:
                external = payload['external']
                external_fields = {'attention_validation','rbf_validation','rbf_metrics'}
                if record.spec.implementation_id=='retrieval-quality/v2':
                    external_fields.update(('attention_output','rbf_output'))
                if not isinstance(external,dict) or set(external)!=external_fields:
                    raise ValueError('invalid external reference evidence')
                for prefix in ('attention','rbf'):
                    validate_saved_comparison(attention_spec,attention_inputs,external.get(prefix+'_output',payload['probabilities']),
                                              external[prefix+'_validation'],reference_output=payload.get('reference_output'))
                if 'rbf_output' in external and canonical_json(classification_metrics(external['rbf_output'],truth,state.classes))!=canonical_json(external['rbf_metrics']):
                    raise ValueError('external RBF metrics disagree with observed probabilities')
                met = met and external['attention_validation']['passed'] and external['rbf_validation']['passed']
        rows.append({'case':record.spec.experiment_id,'seed':seed,'variant':variant.name,'status':record.status,
                     'expected_quality':variant.expected_quality,'expectation_met':bool(met),'result':payload,
                     'diagnostic':record.diagnostic,'identity_hash':record.identity_hash})
        identities.add(record.spec.experiment_id)
        ids.add(record.run_id)
    if identities!={f'seed{s}:{v.name}' for s in profile.seeds for v in profile.variants}:
        raise ValueError('incomplete retrieval roster')
    return tuple(sorted(rows,key=lambda r:r['case']))


# Preserve a complete immutable task-quality bundle, including failed executions and negative controls.
def write_study(records: tuple[RunRecord, ...], directory: str | Path) -> Path:
    return write_records(records,directory,'retrieval-quality-index/v1',summarize_records)


# Read verified saved observations; NumPy and original dataset files are unnecessary for replay.
def read_study(directory: str | Path) -> tuple[RunRecord, ...]:
    return read_records(directory,'retrieval-quality-index/v1',summarize_records)
