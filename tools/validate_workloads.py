"""Run/read the complete W0-W6 workload acceptance roster with code, source data and byte-verified evidence."""

import argparse
from hashlib import sha256
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]  # Checkout roots supply configs/examples; installed model modules stay independent.
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json,content_hash,parse_json
from evaluation.experiments.runner import attention,retrieval,workload
from tools.validate_chipmodel import source_snapshot
from workloads.profiles.attention import AttentionSuite
from workloads.profiles.retrieval import RetrievalProfile


KINDS = ('foundation','mapping','quality')  # Fixed complete acceptance packages; no dynamic module imports from config.
EXPECTED = {  # Complete reviewed case identities, including failures and task-quality negative controls.
    'foundation': {'prefill_mha','prefill_gqa','prefill_mqa','decode_short','decode_long','cross_attention','dataset_uniform',
                   'host_limit_failed','dataset_hash_failed','reference_limit_failed'},
    'mapping': {'fused_q1','spill_q1','fused_q2','expanded_q1','capacity_failed'},
    'quality': {f'seed{s}:{v}' for s in (0,1,2) for v in ('baseline','keys_round_1','keys_round_12','keys_coarse_control')},
}


# Include non-JSON dataset/name/license files in addition to raw Python/config/pyproject bytes.
def workload_source_snapshot() -> dict:
    source = source_snapshot()
    for path in sorted((ROOT/'config/workloads').rglob('*')):
        if path.is_file():
            source['files'][path.relative_to(ROOT).as_posix()] = sha256(path.read_bytes()).hexdigest()
    head = source['source_revision'].split('+',1)[0]
    source['source_revision'] = head+'+workloads-sha256:'+content_hash(source['files'])
    source['scope'] = 'project Python/config/pyproject plus all local workload source data/provenance bytes; excludes build artifacts'
    return source


# Roster omissions, unexpected failures/successes and flipped quality controls all fail acceptance.
def check_rows(kind: str, rows: tuple[dict, ...]) -> dict:
    if kind not in EXPECTED or len(rows)!=len(EXPECTED[kind]) or {r['case'] for r in rows}!=EXPECTED[kind]:
        raise ValueError('incomplete or unexpected acceptance case roster')
    if not all(r['expectation_met'] for r in rows):
        raise ValueError('workload acceptance expectation failed')
    failed = {r['case'] for r in rows if r['status']=='failed'}
    required = {'foundation':{'host_limit_failed','dataset_hash_failed','reference_limit_failed'},'mapping':{'capacity_failed'},'quality':set()}[kind]
    if failed!=required:
        raise ValueError('acceptance failure roster changed')
    negatives = []
    if kind=='quality':
        negatives = [r['case'] for r in rows if not r['result']['quality_passed']]
        if set(negatives)!={f'seed{s}:keys_coarse_control' for s in (0,1,2)}:
            raise ValueError('task-quality negative-control roster changed')
    return {'cases':len(rows),'succeeded':len(rows)-len(failed),'expected_failures':sorted(failed),'quality_negative_controls':sorted(negatives)}


# Complete all three studies with one source identity and commit the acceptance report only after saved/read equivalence.
def validate_workloads(directory: str | Path, *, numpy_reference: bool = False) -> dict:
    target = Path(directory)
    target.mkdir(parents=True,exist_ok=False)
    source = workload_source_snapshot()
    (target/'source.json').write_text(canonical_json(source)+'\n',encoding='utf-8')
    studies = {}
    for kind,module,model,filename in (
        ('foundation',workload,AttentionSuite,'attention_workloads.json'),
        ('mapping',attention,attention.AttentionMappingStudy,'attention_mapping.json'),
        ('quality',retrieval,RetrievalProfile,'retrieval_quality.json')):
        config = load_config(model,ROOT/'config/experiments'/filename)
        options = {'source_revision':source['source_revision']}
        if kind!='mapping':
            options['data_root'] = ROOT/'config/workloads'
        if kind=='quality':
            options['numpy_reference'] = numpy_reference
        records = module.run_study(config,**options)
        rows = module.summarize_records(records)
        module.write_study(records,target/kind)
        (target/(kind+'_summary.json')).write_text(canonical_json(rows)+'\n',encoding='utf-8')
        studies[kind] = check_rows(kind,rows)
        if module.summarize_records(module.read_study(target/kind))!=rows:
            raise ValueError('saved/read workload results differ')
    if workload_source_snapshot()['files']!=source['files']:
        raise ValueError('source changed during workload acceptance')
    hashes = {path.relative_to(target).as_posix():sha256(path.read_bytes()).hexdigest() for path in sorted(target.rglob('*')) if path.is_file()}
    report = {'schema_version':'workloads-acceptance/v1','source_revision':source['source_revision'],'numpy_reference_requested':numpy_reference,
              'studies':studies,'artifact_hashes':hashes,'scope':'finite task/numerical/mapping evidence; no complete target timing or population-generalization claim'}
    with (target/'report.json').open('x',encoding='utf-8') as handle:
        handle.write(canonical_json(report)+'\n')
    return report


# Verify exact committed bytes and regenerate summaries only from saved observations, never from source data or execution.
def read_acceptance(directory: str | Path) -> dict:
    target = Path(directory)
    report = parse_json((target/'report.json').read_text(encoding='utf-8'))
    if (not isinstance(report,dict) or report.get('schema_version')!='workloads-acceptance/v1'
            or set(report.get('studies',{}))!=set(KINDS) or type(report.get('numpy_reference_requested')) is not bool):
        raise ValueError('invalid workloads acceptance report')
    actual = {p.relative_to(target).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob('*')) if p.is_file() and p!=target/'report.json'}
    if actual!=report['artifact_hashes']:
        raise ValueError('acceptance artifact roster/SHA256 mismatch')
    source = parse_json((target/'source.json').read_text(encoding='utf-8'))
    if report['source_revision']!=source['source_revision']:
        raise ValueError('acceptance source identity mismatch')
    for kind,module in (('foundation',workload),('mapping',attention),('quality',retrieval)):
        records = module.read_study(target/kind)
        if kind=='quality' and any((parse_json(r.configuration_json)['external_environment']['backend']!='none')!=report['numpy_reference_requested'] for r in records):
            raise ValueError('acceptance external-reference declaration mismatch')
        if any(r.spec.source_revision!=source['source_revision'] for r in records):
            raise ValueError('study/source identity mismatch')
        rows = module.summarize_records(records)
        if check_rows(kind,rows)!=report['studies'][kind] or canonical_json(rows)!=canonical_json(parse_json((target/(kind+'_summary.json')).read_text(encoding='utf-8'))):
            raise ValueError('acceptance summary differs from records')
    return report


# Standard-library acceptance is always available; optional NumPy evidence is explicit and replay remains dependency-free.
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output',type=Path)
    group.add_argument('--read',type=Path)
    parser.add_argument('--numpy-reference',action='store_true')
    args = parser.parse_args()
    if args.read and args.numpy_reference:
        parser.error('--read does not execute an external reference')
    report = read_acceptance(args.read) if args.read else validate_workloads(args.output,numpy_reference=args.numpy_reference)
    print(canonical_json({k:v for k,v in report.items() if k!='artifact_hashes'}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
