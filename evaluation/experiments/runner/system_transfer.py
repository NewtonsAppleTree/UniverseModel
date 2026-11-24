"""Complete PCIe/DMA studies with immutable byte ledgers, conditional bounds and explicit failed candidates."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.hardware.network import validate_identity
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from evaluation.experiments.runner.bundle import read_records, write_records
from evaluation.experiments.runner.single import run_experiment
from systemmodel.io.dma.analysis import analyze_transfers, validate_transfers
from systemmodel.io.dma.model import CopyBatch, DmaSystem
from systemmodel.topology.graph import freeze_inventory
from systemmodel.topology.query import SystemPath


# One candidate retains its full source/destination/staging placement and finite independent copy chains.
@dataclass(frozen=True, slots=True, kw_only=True)
class TransferCase:
    name: str  # Unique case identity, including negative controls.
    batch: CopyBatch  # Full placement, logical phase and ordered whole-copy chains.
    expected_status: Literal['succeeded','failed'] = 'succeeded'  # Fixture expectation checked separately from execution status.

    # Reject malformed cases before execution, while retaining infeasible placements/paths as failure records.
    def __post_init__(self) -> None:
        validate_identity('name',self.name)
        if not isinstance(self.batch,CopyBatch) or self.expected_status not in ('succeeded','failed'):
            raise ValueError('invalid transfer case')


# All cases share one complete memory/channel/fabric budget; specific comparisons must also match useful task bytes.
@dataclass(frozen=True, slots=True, kw_only=True)
class TransferStudy:
    system: DmaSystem  # Fixed, sourced hardware capacities and packet/DMA service assumptions.
    cases: tuple[TransferCase, ...]  # Complete finite candidate roster.
    schema_version: Literal['system-transfer-study/v1'] = 'system-transfer-study/v1'  # Analytical posted-write/whole-copy study.

    # Canonicalize cases without sorting the semantically ordered legs inside each chain.
    def __post_init__(self) -> None:
        if not isinstance(self.system,DmaSystem) or self.schema_version!='system-transfer-study/v1':
            raise ValueError('invalid transfer study/schema')
        object.__setattr__(self,'cases',freeze_inventory('cases',self.cases,TransferCase,'name'))
        if not self.cases:
            raise ValueError('transfer study requires cases')


# Useful task bytes and per-leg traffic are distinct; partial necessary service does not become target execution time.
def _metrics(batch: CopyBatch, analysis) -> tuple[Metric, ...]:
    counts = (('payload_bytes',sum(c.payload_bytes for c in batch.chains)),
              ('copied_bytes',sum(l.traffic.payload_bytes for l in analysis.legs)),
              ('pcie_frame_bytes',sum(l.traffic.frame_bytes*len(l.path.link_ids) for l in analysis.legs)))
    return tuple(Metric(name=name,value=value,unit='byte',kind='counter') for name,value in counts)+(
        Metric(name='known_service_lower_bound',value=analysis.bounds.lower_bound_s,unit='second',kind='lower_bound'),
        Metric(name='target_execution_time',value=None,unit='second',kind='estimated',unknown_reason='Necessary service/dependency bounds only; no complete memory, queue or visibility execution'),
        Metric(name='target_energy',value=None,unit='joule',kind='estimated',unknown_reason='No complete calibrated memory/DMA/PCIe action-cost coverage'))


# Execute one static candidate; an infeasible chain remains a failed record with a diagnostic and no fabricated metrics.
def _evaluate(config: dict, inputs: dict) -> tuple[dict, tuple[Metric, ...]]:
    analysis = analyze_transfers(config['study'].system,inputs['batch'])
    return {'analysis':analysis},_metrics(inputs['batch'],analysis)


# Save exact hardware, full roster and selected batch on every attempt; expectations never suppress failures.
def run_study(study: TransferStudy, *, source_revision: str = 'unrecorded') -> tuple[RunRecord, ...]:
    if not isinstance(study,TransferStudy):
        raise TypeError('expected TransferStudy')
    records = []
    for case in study.cases:
        spec = ExperimentSpec(experiment_id=case.name,implementation_id='system-transfer-study/v1',mode='analytical',source_revision=source_revision,
                              assumptions=('Explicit local-source DMA posted writes; no implicit remote pulls, P2P permissions or host staging',
                                           'Whole-copy completion dependencies; all reservations live at one logical phase; no chunk pipelining',
                                           'Unique zero-credit service ceilings; startup/burst work in DMA, TLP padding/overhead in frame demand, coding in line capacity',
                                           'Bounds omit backing service, control traffic and execution/visibility; input byte contents and task quality are not evaluated'))
        records.append(run_experiment(spec,{'study':study,'selected':case.name},{'batch':case.batch},_evaluate))
    return tuple(records)


# Reanalyze exact saved routes/bytes/dependencies under the same source; no producer callback or path search executes.
def summarize_records(records: tuple[RunRecord, ...]) -> tuple[dict, ...]:
    if not records or any(not isinstance(r,RunRecord) for r in records):
        raise ValueError('expected nonempty transfer study records')
    common,names,ids,rows = None,set(),set(),[]
    for record in records:
        if (record.spec.implementation_id,record.spec.mode)!=('system-transfer-study/v1','analytical'):
            raise ValueError('wrong transfer record kind')
        config,inputs = parse_json(record.configuration_json),parse_json(record.inputs_json)
        if not isinstance(config,dict) or set(config)!={'study','selected'} or not isinstance(inputs,dict) or set(inputs)!={'batch'}:
            raise ValueError('invalid transfer snapshot schema')
        study = resolve_dataclass(TransferStudy,config['study'])
        digest = content_hash((study,record.spec.source_revision,record.spec.assumptions))
        if common is not None and digest!=common:
            raise ValueError('mixed transfer study/source/assumptions')
        common = digest
        case = next((c for c in study.cases if c.name==config['selected']),None)
        if case is None or case.name!=record.spec.experiment_id or case.name in names or record.run_id in ids:
            raise ValueError('duplicate or invalid transfer case identity')
        if canonical_json(case.batch)!=canonical_json(inputs['batch']):
            raise ValueError('transfer case/input mismatch')
        payload = parse_json(record.output_json) if record.status=='succeeded' else None
        if record.status=='succeeded':
            if not isinstance(payload,dict) or set(payload)!={'analysis'} or not isinstance(payload['analysis'],dict):
                raise ValueError('invalid transfer output schema')
            saved = payload['analysis'].get('legs')
            if not isinstance(saved,list) or any(not isinstance(l,dict) or not isinstance(l.get('path'),dict) for l in saved):
                raise ValueError('missing saved transfer routes')
            paths = tuple(resolve_dataclass(SystemPath,l['path']) for l in saved)
            analysis = validate_transfers(study.system,case.batch,paths)
            if canonical_json(payload)!=canonical_json({'analysis':analysis}):
                raise ValueError('saved transfer observations disagree with declarations/paths')
            if canonical_json(sorted(record.metrics,key=lambda m:m.name))!=canonical_json(sorted(_metrics(case.batch,analysis),key=lambda m:m.name)):
                raise ValueError('transfer metrics disagree with byte ledger/bounds/unknown costs')
        rows.append({'case':case.name,'status':record.status,'expected_status':case.expected_status,'expectation_met':record.status==case.expected_status,
                     'result':payload,'diagnostic':record.diagnostic,'identity_hash':record.identity_hash})
        names.add(case.name)
        ids.add(record.run_id)
    if names!={c.name for c in study.cases}:
        raise ValueError('incomplete transfer study roster')
    return tuple(sorted(rows,key=lambda r:r['case']))


# Preserve one complete validated study in an immutable directory; never overwrite existing evidence.
def write_study(records: tuple[RunRecord, ...], directory: str | Path) -> Path:
    return write_records(records,directory,'system-transfer-index/v1',summarize_records)


# Read exact stored observations and recheck their static semantics without producing a new execution.
def read_study(directory: str | Path) -> tuple[RunRecord, ...]:
    return read_records(directory,'system-transfer-index/v1',summarize_records)
