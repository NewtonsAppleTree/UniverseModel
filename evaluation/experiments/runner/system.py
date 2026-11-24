"""Complete node-connectivity studies with explicit failures and immutable static-evidence replay."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.hardware.network import validate_identity
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from evaluation.experiments.runner.bundle import read_records, write_records
from evaluation.experiments.runner.single import run_experiment
from systemmodel.composition.node.model import NodeSpec
from systemmodel.topology.graph import freeze_inventory
from systemmodel.topology.query import PathRequest, find_path, validate_path


# Each case asks one operation/path question; expected failure is a reviewed fixture condition, not suppressed evidence.
@dataclass(frozen=True, slots=True, kw_only=True)
class NodeCase:
    name: str  # Unique case identity in this finite study.
    request: PathRequest  # Source/target operation and explicit or searched route.
    expected_status: Literal['succeeded','failed'] = 'succeeded'  # Expected execution outcome, independently checked after recording.

    # Preserve invalid reachability as a runtime outcome while rejecting malformed case declarations.
    def __post_init__(self) -> None:
        validate_identity('name',self.name)
        if not isinstance(self.request,PathRequest) or self.expected_status not in ('succeeded','failed'):
            raise ValueError('invalid node case request/status')


# All cases share one sourced node; studies compare access feasibility, not measured hardware performance.
@dataclass(frozen=True, slots=True, kw_only=True)
class NodeStudy:
    node: NodeSpec  # Fixed complete node ownership, model references, capabilities and connectivity.
    cases: tuple[NodeCase, ...]  # Complete finite success/failure roster.
    schema_version: Literal['system-connectivity/v1'] = 'system-connectivity/v1'  # Static node-path study.

    # Canonicalize the finite case roster and reject duplicate names before any callback runs.
    def __post_init__(self) -> None:
        if not isinstance(self.node,NodeSpec) or self.schema_version!='system-connectivity/v1':
            raise ValueError('invalid node study/schema')
        object.__setattr__(self,'cases',freeze_inventory('cases',self.cases,NodeCase,'name'))
        if not self.cases:
            raise ValueError('node study requires cases')


# Static capability/path evidence leaves actual transfer latency and energy unknown, even for an empty cost ledger.
def _evaluate(config: dict, inputs: dict) -> tuple[dict, tuple[Metric, ...]]:
    study = config['study']
    path = find_path(study.node.topology,inputs['request'])
    return {'node_identity':study.node.identity_hash,'device_ids':study.node.device_ids,'path':path}, (
        Metric(name='path_hops',value=len(path.link_ids),unit='one',kind='counter'),
        Metric(name='target_execution_time',value=None,unit='second',kind='estimated',unknown_reason='Static connectivity only; no transfer/service/queue execution'),
        Metric(name='target_energy',value=None,unit='joule',kind='estimated',unknown_reason='No complete physical action/cost profile'))


# Each request creates an independent terminal record with the full node/case roster and immutable input snapshot.
def run_study(study: NodeStudy, *, source_revision: str = 'unrecorded') -> tuple[RunRecord, ...]:
    if not isinstance(study,NodeStudy):
        raise TypeError('expected NodeStudy')
    records = []
    for case in study.cases:
        spec = ExperimentSpec(experiment_id=case.name,implementation_id='system-connectivity/v1',mode='analytical',source_revision=source_revision,
                              assumptions=('Static ownership and declared permissions; no implicit endpoint forwarding, staging, translation or coherence',
                                           'One shared capacity declaration per physical resource; visits do not multiply capacity',
                                           'Chip model identities are references, not proof of attached model behavior',
                                           'A valid path is not executed transfer, memory visibility, target latency or task-quality evidence'))
        records.append(run_experiment(spec,{'study':study,'selected':case.name},{'request':case.request},_evaluate))
    return tuple(records)


# Recheck saved route legality and roster consistency without search, hardware analysis or target execution.
def summarize_records(records: tuple[RunRecord, ...]) -> tuple[dict, ...]:
    if not records or any(not isinstance(r,RunRecord) for r in records):
        raise ValueError('expected nonempty node study records')
    common,names,ids,rows = None,set(),set(),[]
    for record in records:
        if (record.spec.implementation_id,record.spec.mode)!=('system-connectivity/v1','analytical'):
            raise ValueError('wrong node record kind')
        config,inputs = parse_json(record.configuration_json),parse_json(record.inputs_json)
        if not isinstance(config,dict) or set(config)!={'study','selected'} or not isinstance(inputs,dict) or set(inputs)!={'request'}:
            raise ValueError('invalid node record snapshot schema')
        study = resolve_dataclass(NodeStudy,config['study'])
        digest = content_hash((study,record.spec.source_revision,record.spec.assumptions))
        if common is not None and digest!=common:
            raise ValueError('mixed node study/source/assumptions')
        common = digest
        case = next((case for case in study.cases if case.name==config['selected']),None)
        if case is None or case.name!=record.spec.experiment_id or case.name in names or record.run_id in ids:
            raise ValueError('duplicate or invalid node case identity')
        if canonical_json(case.request)!=canonical_json(inputs['request']):
            raise ValueError('node case/request mismatch')
        payload = parse_json(record.output_json) if record.status=='succeeded' else None
        if record.status=='succeeded':
            if not isinstance(payload,dict) or set(payload)!={'node_identity','device_ids','path'} or not isinstance(payload['path'],dict):
                raise ValueError('invalid node result schema')
            if payload['node_identity']!=study.node.identity_hash or payload['device_ids']!=list(study.node.device_ids):
                raise ValueError('node result identity/inventory mismatch')
            saved = payload['path']
            if 'link_ids' not in saved:
                raise ValueError('missing saved path')
            checked = validate_path(study.node.topology,case.request,saved['link_ids'])
            if canonical_json(checked)!=canonical_json(saved):
                raise ValueError('saved node path/constraint observations disagree')
            metrics = {m.name:m for m in record.metrics}
            if (set(metrics)!={'path_hops','target_execution_time','target_energy'}
                    or metrics['path_hops'].value!=len(checked.link_ids) or metrics['path_hops'].unit!='one' or metrics['path_hops'].kind!='counter'
                    or metrics['target_execution_time'].value is not None or metrics['target_energy'].value is not None
                    or metrics['target_execution_time'].unit!='second' or metrics['target_energy'].unit!='joule'
                    or any(metrics[key].kind!='estimated' for key in ('target_execution_time','target_energy'))):
                raise ValueError('node metrics disagree with static evidence/unknown costs')
        rows.append({'case':case.name,'status':record.status,'expected_status':case.expected_status,
                     'expectation_met':record.status==case.expected_status,'result':payload,'diagnostic':record.diagnostic,
                     'identity_hash':record.identity_hash})
        names.add(case.name)
        ids.add(record.run_id)
    if names!={case.name for case in study.cases}:
        raise ValueError('incomplete node study roster')
    return tuple(sorted(rows,key=lambda row:row['case']))


# Commit the complete checked study once; existing evidence directories are never overwritten.
def write_study(records: tuple[RunRecord, ...], directory: str | Path) -> Path:
    return write_records(records,directory,'system-connectivity-index/v1',summarize_records)


# Rebuild route observations from saved structure alone; no execution callback or path search is needed.
def read_study(directory: str | Path) -> tuple[RunRecord, ...]:
    return read_records(directory,'system-connectivity-index/v1',summarize_records)
