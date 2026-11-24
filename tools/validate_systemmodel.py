"""S0–S7 complete default-fixture run/read acceptance with source and artifact provenance."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]  # Checkout providing configuration/examples; no target timing inferred.
sys.path.insert(0,str(ROOT))
from tools.validate_chipmodel import artifact_hashes, invoke, source_snapshot, write_json
from contracts.results.experiment import RunRecord
from evaluation.experiments.runner.bundle import read_records

STUDIES = {
    'system':(7,('hop_limit_failed','peer_reverse_denied','read_denied','wrong_explicit_path')),
    'system_memory':(15,('address_overlap','expired','exposed_padding','physical_overlap','rounded_capacity','span_overflow','stale_memory','unreachable','write_denied')),
    'system_transfer':(14,('expired','remote_pull_denied','reverse_direct_denied','staging_discontinuity','staging_too_small','write_conflict','write_permission_denied')),
    'system_tiering':(15,('cache_is_not_mem','decoder_mismatch','io_is_not_mem','local_capacity_failed','masked_write_unsupported','reuse_source_too_early','source_retired_early','wrong_copy_object')),
    'system_network':(12,('buffer_capacity','expired_registration','missing_flow_binding','missing_registration','short_registration','wrong_data_version','wrong_direction','wrong_permission')),
    'system_ai':(18,('too_large_direct','too_large_resident','too_large_staged')),
}  # Reviewed finite roster sizes and failure identities, never inferred from whichever attempts happened to succeed.

SUCCESSES = {
    'system':('host_to_gpu0','host_to_gpu1','peer_declared'),
    'system_memory':('alias','lifetime_reuse','local','placement_only','remote','replicated_copy'),
    'system_transfer':('direct','explicit_route','reverse_staged','small_1B','staged','tail_513B','two_shared'),
    'system_tiering':('demote','dma_to_accelerator','expanded_residency','native_read','partial_read_1B','promote','replicate'),
    'system_network':('rdma_write','same_node','shared_nic','single'),
    'system_ai':tuple(f'{task}_{policy}' for task in ('linear','training','attention')
                      for policy in ('resident','direct','staged','half_bandwidth','high_startup')),
}  # Pin positive controls too: equal counts cannot substitute an unreviewed candidate for a required case.

INDEX_SCHEMAS = {
    'system':'system-connectivity-index/v1', 'system_memory':'system-memory-index/v1',
    'system_transfer':'system-transfer-index/v1', 'system_tiering':'system-tiering-index/v1',
    'system_network':'system-network-index/v1', 'system_ai':'system-ai-index/v1',
}  # Immutable study formats; read_records checks run manifests/identities without executing models.


# Check complete counts, unique names and both unexpected success/failure before accepting any study.
def check_rows(name: str, rows: list) -> dict:
    count,failures = STUDIES[name]
    if len(rows)!=count or len({r['case'] for r in rows})!=count:
        raise ValueError(f'{name}: missing/duplicate candidate rows')
    if {r['case'] for r in rows}!=set(SUCCESSES[name])|set(failures):
        raise ValueError(f'{name}: candidate roster differs from reviewed fixture')
    actual=[]
    for row in rows:
        if row['status'] not in ('succeeded','failed') or row['expectation_met'] is not True:
            raise ValueError(f'{name}: unfinished or unexpected outcome')
        if row['status']=='failed':
            if not row['diagnostic']:
                raise ValueError('failure requires a diagnostic')
            actual.append(row['case'])
    if sorted(actual)!=sorted(failures):
        raise ValueError(f'{name}: failure roster differs from reviewed fixture')
    return {'cases':count,'succeeded':count-len(failures),'expected_failures':sorted(failures)}


# Recompute the saved manifest digest, not the current checkout: historical bundles remain independently readable.
def check_source(source: dict, revision: str) -> None:
    if not isinstance(source,dict):
        raise ValueError('invalid source manifest schema')
    files=source.get('files')
    if (source.get('source_revision')!=revision or not isinstance(revision,str)
            or not isinstance(files,dict) or not files
            or any(not isinstance(key,str) or not key or not isinstance(value,str)
                   or re.fullmatch('[0-9a-f]{64}',value) is None for key,value in files.items())):
        raise ValueError('invalid source identity/file manifest')
    digest=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    parts=revision.rsplit('+python-config-sha256:',1)
    if len(parts)!=2 or not parts[0] or parts[1]!=digest:
        raise ValueError('source file manifest digest mismatch')


# All successful and failed runs must declare the same source as the top-level evidence; study-local consistency is insufficient.
def check_record_sources(records: tuple[RunRecord, ...], revision: str) -> None:
    if not records or any(record.spec.source_revision!=revision for record in records):
        raise ValueError('run source identity differs from acceptance source')


# Validate index/run hashes and source binding without producers, path searches or current-source recapture.
def check_bundle_source(target: Path, name: str, revision: str) -> None:
    read_records(target/name,INDEX_SCHEMAS[name],lambda records: check_record_sources(records,revision))


# Manifest verification detects missing/added/tampered files before independent saved-record checks; no producer is invoked.
def verify_saved(target: Path) -> dict:
    report=json.loads((target/'acceptance.json').read_text(encoding='utf-8'))
    if report['schema']!='systemmodel-acceptance/v1' or set(report['studies'])!=set(STUDIES):
        raise ValueError('invalid complete system acceptance roster/schema')
    if artifact_hashes(target)!=report['artifacts']:
        raise ValueError('artifact hash or complete file roster mismatch')
    source=json.loads((target/'source.json').read_text(encoding='utf-8'))
    check_source(source,report['source_revision'])
    for name in STUDIES:
        check_bundle_source(target,name,report['source_revision'])
        saved=json.loads((target/(name+'_summary.json')).read_text(encoding='utf-8'))
        rows,_=invoke(name,['--read',str(target/name)])
        if rows!=saved or check_rows(name,rows)!=report['studies'][name]:
            raise ValueError(f'{name}: saved summary differs from complete bundles')
    return report


# Run all six package studies and read them back under one actual source snapshot; a final report marks completion.
def run_acceptance(target: Path) -> dict:
    target.mkdir(parents=True,exist_ok=False)
    source=source_snapshot()
    check_source(source,source['source_revision'])
    write_json(target/'source.json',source)
    studies,commands={},[]
    for name in STUDIES:
        rows,run=invoke(name,['--source-revision',source['source_revision'],'--output',str(target/name)])
        write_json(target/(name+'_summary.json'),rows)
        restored,read=invoke(name,['--read',str(target/name)])
        if rows!=restored:
            raise ValueError(f'{name}: run/read mismatch')
        check_bundle_source(target,name,source['source_revision'])
        studies[name]=check_rows(name,rows)
        commands.extend((run,read))
    if source_snapshot()['files']!=source['files']:
        raise ValueError('source changed during acceptance')
    write_json(target/'commands.json',commands)
    report={'schema':'systemmodel-acceptance/v1','source_revision':source['source_revision'],
            'studies':studies,'artifacts':artifact_hashes(target),
            'evidence':'Static node/memory/transport/NIC/fabric plus independent AI operator/gradient numerics; no complete timing, coherence, dataset quality or hardware calibration'}
    write_json(target/'acceptance.json',report)
    return report


# Select a fresh run directory or read-only replay; never delete evidence or alter Git state.
def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--output',type=Path)
    choice.add_argument('--read',type=Path)
    args=parser.parse_args()
    try:
        report=verify_saved(args.read.resolve()) if args.read else run_acceptance(args.output.resolve())
    except (ValueError,TypeError,KeyError,OSError,subprocess.CalledProcessError) as exc:
        print(f'systemmodel acceptance failed: {exc}',file=sys.stderr)
        return 1
    print(json.dumps({k:v for k,v in report.items() if k!='artifacts'},ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
