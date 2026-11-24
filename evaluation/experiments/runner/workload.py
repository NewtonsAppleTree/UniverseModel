"""Functional Attention workload evidence with complete inputs, provenance, failures and read-only replay."""

from pathlib import Path

from artifacts.storage.local import read_run, write_run
from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from contracts.workload.attention import AttentionInputs, attention_buffer, attention_identity, validate_attention
from evaluation.experiments.runner.single import run_experiment
from workloads.kernels.attention import describe_attention
from workloads.profiles.attention import AttentionSuite, prepare_attention
from workloads.reference.attention import reference_attention


# Produce reference observations and semantic counters; do not validate the reference by comparing it to itself.
def _evaluate(configuration: dict, prepared: dict) -> tuple[dict, tuple[Metric, ...]]:
    suite = configuration['suite']
    case = next(c for c in suite.cases if c.name == configuration['selected'])
    if prepared['error'] is not None:
        raise ValueError(f"input preparation failed: {prepared['error']}")
    data = prepared['data']
    result = reference_attention(case.spec, data, precision_digits=suite.precision_digits,
                                 max_score_pairs=suite.max_score_pairs, max_macs=suite.max_macs)
    work = describe_attention(case.spec)
    metrics = tuple(Metric(name=name, value=getattr(work, name), unit=unit, kind='counter') for name, unit in (
        ('dense_qk_macs', 'MAC'), ('dense_av_macs', 'MAC'), ('visible_pair_macs', 'MAC'),
        ('q_bytes', 'byte'), ('kv_bytes', 'byte'), ('output_bytes', 'byte'), ('materialized_score_bytes', 'byte')))
    metrics += (Metric(name='target_execution_time', value=None, unit='second', kind='estimated',
                       unknown_reason='Task/reference only; no compiler mapping or target execution'),
                Metric(name='target_energy', value=None, unit='joule', kind='estimated',
                       unknown_reason='No mapped actions or calibrated cost profile'))
    return {'spec_identity': case.spec.identity_hash, 'work': work, 'reference': result}, metrics


# Prepare actual input snapshots before the callback; preparation errors become records without invented input data.
def run_study(suite: AttentionSuite, *, data_root: str | Path, source_revision: str = 'unrecorded') -> tuple[RunRecord, ...]:
    if not isinstance(suite, AttentionSuite):
        raise TypeError('suite must be AttentionSuite')
    records = []
    for case in suite.cases:
        try:
            prepared = {'data': prepare_attention(case, suite, data_root=data_root), 'error': None}
        except (ValueError, TypeError, OSError) as exc:
            prepared = {'data': None, 'error': f'{type(exc).__name__}: {exc}'}
        spec = ExperimentSpec(experiment_id=case.name, implementation_id='attention-workloads/v1', mode='functional',
                              source_revision=source_revision, assumptions=(
            'Already projected Q/K/V; no RoPE, dropout, quantization, backward or complete Transformer',
            'Uniform B/head/token layout; contiguous query groups share KV; causal start is explicit',
            'Exact rational logits, Decimal exponentials/weighted sums; binary64 observations may underflow to zero',
            'Rectangular and visible-pair work are distinct; logical bytes are not target memory traffic',
            'Synthetic profiles do not establish task accuracy, perplexity, convergence or service representativeness',
            'Independent reference validation is in tests; callback success is not a quality or performance verdict',
        ))
        records.append(run_experiment(spec, {'suite': suite, 'selected': case.name}, prepared, _evaluate))
    return tuple(records)


# Check semantic identity, complete roster and source consistency without regenerating inputs or executing the reference.
def summarize_records(records: tuple[RunRecord, ...]) -> tuple[dict, ...]:
    if not isinstance(records, (tuple, list)) or not records or any(not isinstance(r, RunRecord) for r in records):
        raise ValueError('expected nonempty RunRecord list/tuple')
    rows, names, ids, identity = [], set(), set(), None
    for record in records:
        if (record.spec.implementation_id, record.spec.mode) != ('attention-workloads/v1', 'functional'):
            raise ValueError('expected Attention functional records')
        config = parse_json(record.configuration_json)
        if not isinstance(config, dict) or set(config) != {'suite', 'selected'}:
            raise ValueError('invalid workload configuration snapshot')
        suite = resolve_dataclass(AttentionSuite, config['suite'])
        current = content_hash({'suite': config['suite'], 'source': record.spec.source_revision, 'assumptions': record.spec.assumptions})
        if identity is not None and identity != current:
            raise ValueError('mixed workload suites or source versions')
        identity = current
        case = next((c for c in suite.cases if c.name == config['selected']), None)
        if case is None or case.name != record.spec.experiment_id or case.name in names or record.run_id in ids:
            raise ValueError('invalid or duplicate workload case/run identity')
        prepared = parse_json(record.inputs_json)
        if not isinstance(prepared, dict) or set(prepared) != {'data', 'error'}:
            raise ValueError('invalid prepared input snapshot')
        if prepared['data'] is None:
            if type(prepared['error']) is not str or not prepared['error'].strip() or record.status != 'failed':
                raise ValueError('missing workload inputs require a failed preparation record')
        else:
            if prepared['error'] is not None:
                raise ValueError('prepared inputs cannot also have a preparation error')
            data = resolve_dataclass(AttentionInputs, prepared['data'])
            validate_attention(case.spec, data)
        payload = parse_json(record.output_json) if record.output_json is not None else None
        if record.status == 'succeeded':
            if (not isinstance(payload, dict) or set(payload) != {'spec_identity', 'work', 'reference'}
                    or not isinstance(payload['work'], dict) or not isinstance(payload['reference'], dict)
                    or set(payload['reference']) != {'input_identity', 'output', 'probabilities', 'precision_digits'}):
                raise ValueError('invalid Attention reference output schema')
            attention_buffer('reference output', payload['reference']['output'])
            probabilities = attention_buffer('reference probabilities', payload['reference']['probabilities'])
            if any(p < 0.0 or p > 1.0 for p in probabilities):
                raise ValueError('reference probabilities must be in [0,1]')
            if (payload['spec_identity'] != case.spec.identity_hash
                    or payload['reference']['input_identity'] != attention_identity(case.spec, data)
                    or payload['reference']['precision_digits'] != suite.precision_digits
                    or len(payload['reference']['output']) != case.spec.batch_size * case.spec.query_heads * case.spec.query_length * case.spec.value_dim
                    or len(payload['reference']['probabilities']) != case.spec.score_pairs):
                raise ValueError('reference output disagrees with workload input identity/shape')
        names.add(case.name)
        ids.add(record.run_id)
        rows.append({'case': case.name, 'purpose': case.purpose, 'status': record.status,
                     'expected_status': case.expected_status, 'expectation_met': record.status == case.expected_status,
                     'input_kind': case.dataset.kind if case.dataset is not None else 'synthetic',
                     'result': payload, 'metrics': parse_json(canonical_json(record.metrics)),
                     'diagnostic': record.diagnostic, 'identity_hash': record.identity_hash})
    if names != {case.name for case in suite.cases}:
        raise ValueError('incomplete workload case roster')
    return tuple(sorted(rows, key=lambda row: row['case']))


# Commit the immutable bundle roster only after all records are written; never overwrite previous evidence.
def write_study(records: tuple[RunRecord, ...], directory: str | Path) -> Path:
    summarize_records(records)
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=False)
    entries = []
    for index, record in enumerate(sorted(records, key=lambda r: r.spec.experiment_id)):
        name = f'run-{index:04d}'
        write_run(record, target / name)
        entries.append({'directory': name, 'run_id': record.run_id, 'identity_hash': record.identity_hash})
    with (target / 'index.json').open('x', encoding='utf-8') as handle:
        handle.write(canonical_json({'schema_version': 'attention-study-index/v1', 'runs': entries}) + '\n')
    return target


# Read only local indexed bundles, rejecting omissions, duplicate identities and arbitrary paths; source data files are unnecessary.
def read_study(directory: str | Path) -> tuple[RunRecord, ...]:
    target = Path(directory)
    index = parse_json((target / 'index.json').read_text(encoding='utf-8'))
    if not isinstance(index, dict) or set(index) != {'schema_version', 'runs'} or index['schema_version'] != 'attention-study-index/v1':
        raise ValueError('invalid Attention study index')
    if not isinstance(index['runs'], list) or not index['runs']:
        raise ValueError('Attention study index requires complete runs')
    records = []
    for position, entry in enumerate(index['runs']):
        if not isinstance(entry, dict) or set(entry) != {'directory', 'run_id', 'identity_hash'} or entry['directory'] != f'run-{position:04d}':
            raise ValueError('invalid Attention bundle path/order')
        record = RunRecord.from_dict(read_run(target / entry['directory']))
        if (record.run_id, record.identity_hash) != (entry['run_id'], entry['identity_hash']):
            raise ValueError('Attention index/record identity mismatch')
        records.append(record)
    summarize_records(tuple(records))
    return tuple(records)
