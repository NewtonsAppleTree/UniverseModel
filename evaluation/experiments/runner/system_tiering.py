"""Complete tier/CXL/migration studies with immutable failed candidates and saved-route static replay."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.hardware.network import validate_count, validate_identity
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from evaluation.experiments.runner.bundle import read_records, write_records
from evaluation.experiments.runner.single import run_experiment
from systemmodel.io.cxl.model import CxlAccessRequest, CxlMemorySystem, analyze_cxl_access, validate_cxl_access
from systemmodel.io.dma.model import CopyBatch, DmaSystem
from systemmodel.memory.migration import CxlCopyRequest, analyze_cxl_migration, analyze_dma_migration, validate_cxl_migration, validate_dma_migration
from systemmodel.memory.model import MemoryPlan
from systemmodel.memory.tiering import TieredMemorySystem, TierMigration, analyze_residency
from systemmodel.topology.graph import freeze_inventory
from systemmodel.topology.query import SystemPath


# Each case checks one placement and optionally native access or exactly one explicitly transported migration.
@dataclass(frozen=True, slots=True, kw_only=True)
class TierCase:
    name: str  # Unique candidate identity in the complete finite study.
    placement: MemoryPlan  # Initial static placement; must equal migration.before when a migration is requested.
    phase: int  # Shared logical phase for initial usage, native accesses and all migration snapshots.
    access: CxlAccessRequest | None = None  # Optional native access query, mutually exclusive with migration.
    migration: TierMigration | None = None  # Explicit before/overlap/after transition.
    cxl_copy: CxlCopyRequest | None = None  # Native host-copy transport for a migration.
    dma_copy: CopyBatch | None = None  # Compatible existing S3 transport for a migration.
    expected_status: Literal['succeeded','failed'] = 'succeeded'  # Reviewed fixture expectation, separate from actual status.

    # Validate case shape without suppressing semantic capacity, decoder or migration failures.
    def __post_init__(self) -> None:
        validate_identity('name',self.name)
        validate_count('phase',self.phase)
        if not isinstance(self.placement,MemoryPlan) or self.expected_status not in ('succeeded','failed'):
            raise ValueError('invalid tier case placement/status')
        for name,kind in (('access',CxlAccessRequest),('migration',TierMigration),('cxl_copy',CxlCopyRequest),('dma_copy',CopyBatch)):
            if getattr(self,name) is not None and not isinstance(getattr(self,name),kind):
                raise TypeError('invalid tier case optional request type')
        transports = int(self.cxl_copy is not None)+int(self.dma_copy is not None)
        if (self.migration is None and transports) or (self.migration is not None and (self.access is not None or transports!=1)):
            raise ValueError('migration requires exactly one transport and no separate access query')


# Every candidate uses the same physical hardware; changing a placement never invents new capacity or protocol capability.
@dataclass(frozen=True, slots=True, kw_only=True)
class TierStudy:
    system: TieredMemorySystem  # Complete physical tier assignment.
    cxl: CxlMemorySystem  # Native capability/decoder assembly on the same MemorySystem.
    cases: tuple[TierCase, ...]  # Complete success/failure roster.
    dma: DmaSystem | None = None  # Optional compatible PCIe/DMA assembly; not a CXL.mem protocol implementation.
    schema_version: Literal['system-tiering-study/v1'] = 'system-tiering-study/v1'  # Static residency/access/transition evidence.

    # Reject mixed hardware assemblies and duplicate cases before any static callback runs.
    def __post_init__(self) -> None:
        if not isinstance(self.system,TieredMemorySystem) or not isinstance(self.cxl,CxlMemorySystem) or self.schema_version!='system-tiering-study/v1':
            raise ValueError('invalid tier study/schema')
        if self.system.memory.identity_hash!=self.cxl.memory.identity_hash or (self.dma is not None and (not isinstance(self.dma,DmaSystem) or self.dma.memory.identity_hash!=self.system.memory.identity_hash)):
            raise ValueError('tier/CXL/DMA assemblies must reference identical physical memory/topology')
        object.__setattr__(self,'cases',freeze_inventory('cases',self.cases,TierCase,'name'))
        if not self.cases:
            raise ValueError('tier study requires cases')


# Extract an actual stored route for replay; absent/malformed evidence cannot silently trigger a new search.
def _path(value: dict) -> SystemPath:
    if not isinstance(value,dict):
        raise ValueError('missing saved tiering route')
    return resolve_dataclass(SystemPath,value)


# Compose only the requested professional analyses; replay branches use recorded paths and never call producers/search.
def _analyze_case(study: TierStudy, case: TierCase, saved: dict | None) -> dict:
    residency = analyze_residency(study.system,case.placement,case.phase)
    access,migration = None,None
    if case.access is not None:
        if case.access.access.phase!=case.phase:
            raise ValueError('native access and residency phases disagree')
        access = (analyze_cxl_access(study.cxl,case.placement,case.access) if saved is None else
                  validate_cxl_access(study.cxl,case.placement,case.access,_path(saved['access']['access']['path'])))
    if case.migration is not None:
        if case.migration.before!=case.placement:
            raise ValueError('migration.before must equal the selected initial placement')
        if case.cxl_copy is not None:
            migration = (analyze_cxl_migration(study.system,case.migration,case.phase,study.cxl,case.cxl_copy) if saved is None else
                         validate_cxl_migration(study.system,case.migration,case.phase,study.cxl,case.cxl_copy,_path(saved['migration']['cxl_access']['access']['path'])))
        else:
            if study.dma is None:
                raise ValueError('DMA migration has no declared DMA assembly')
            migration = (analyze_dma_migration(study.system,case.migration,case.phase,study.dma,case.dma_copy) if saved is None else
                         validate_dma_migration(study.system,case.migration,case.phase,study.dma,case.dma_copy,
                                                tuple(_path(l['path']) for l in saved['migration']['dma']['legs'])))
    return {'residency':residency,'access':access,'migration':migration}


# Simultaneous reservation counts and native data quanta are known; capacity labels do not imply performance.
def _metrics(result: dict) -> tuple[Metric, ...]:
    metrics = [Metric(name='initial_reserved_bytes',value=sum(t.reserved_bytes for t in result['residency'].tiers),unit='byte',kind='counter')]
    if result['access'] is not None:
        metrics.append(Metric(name='cxl_data_bytes',value=result['access'].data_bytes,unit='byte',kind='counter'))
    if result['migration'] is not None:
        evidence = result['migration']
        metrics.extend((Metric(name='migration_data_bytes',value=evidence.transport_data_bytes,unit='byte',kind='counter'),
                        Metric(name='additional_reserved_bytes',value=evidence.transition.additional_reserved_bytes,unit='byte',kind='counter'),
                        Metric(name='known_service_lower_bound',value=evidence.known_service_lower_bound_s,unit='second',kind='lower_bound',
                               unknown_reason='Native CXL/host service has no timing model' if evidence.known_service_lower_bound_s is None else None)))
    return (*metrics,Metric(name='target_execution_time',value=None,unit='second',kind='estimated',unknown_reason='Static feasibility only; no completed transfer, coherence or publication events'),
            Metric(name='target_energy',value=None,unit='joule',kind='estimated',unknown_reason='No complete calibrated tier/access/migration energy model'))


# Execute one static case; infeasibility becomes a failed immutable attempt without fabricated partial observations.
def _evaluate(config: dict, inputs: dict) -> tuple[dict, tuple[Metric, ...]]:
    result = _analyze_case(config['study'],inputs['case'],None)
    return result,_metrics(result)


# Preserve complete hardware, all cases and selected input for every success/failure independently of fixture expectation.
def run_study(study: TierStudy, *, source_revision: str = 'unrecorded') -> tuple[RunRecord, ...]:
    if not isinstance(study,TierStudy):
        raise TypeError('expected TierStudy')
    records = []
    for case in study.cases:
        spec = ExperimentSpec(experiment_id=case.name,implementation_id='system-tiering-study/v1',mode='analytical',source_revision=source_revision,
                              assumptions=('Tier membership references unique physical backing; simultaneous phase occupancy, not sum of independent peaks',
                                           'CXL.mem requires explicit enabled mode, host attachment, flat decoder and allowed request path; cache/coherence execution unmodeled',
                                           'Full object migration retains source and destination during copy; after snapshot is conditional, not executed or published',
                                           'Native CXL line data is separate from compatible PCIe/DMA framing; no complete target timing/energy or task-quality claim'))
        records.append(run_experiment(spec,{'study':study,'selected':case.name},{'case':case},_evaluate))
    return tuple(records)


# Recheck roster/source and all saved static evidence without producer execution; failed diagnostics remain prior observations.
def summarize_records(records: tuple[RunRecord, ...]) -> tuple[dict, ...]:
    if not records or any(not isinstance(r,RunRecord) for r in records):
        raise ValueError('expected nonempty tier study records')
    common,names,ids,rows = None,set(),set(),[]
    for record in records:
        if (record.spec.implementation_id,record.spec.mode)!=('system-tiering-study/v1','analytical'):
            raise ValueError('wrong tiering record kind')
        config,inputs = parse_json(record.configuration_json),parse_json(record.inputs_json)
        if not isinstance(config,dict) or set(config)!={'study','selected'} or not isinstance(inputs,dict) or set(inputs)!={'case'}:
            raise ValueError('invalid tiering snapshot schema')
        study = resolve_dataclass(TierStudy,config['study'])
        digest = content_hash((study,record.spec.source_revision,record.spec.assumptions))
        if common is not None and digest!=common:
            raise ValueError('mixed tier study/source/assumptions')
        common = digest
        case = next((c for c in study.cases if c.name==config['selected']),None)
        if case is None or case.name!=record.spec.experiment_id or case.name in names or record.run_id in ids or canonical_json(case)!=canonical_json(inputs['case']):
            raise ValueError('duplicate or inconsistent tiering case/input identity')
        payload = parse_json(record.output_json) if record.status=='succeeded' else None
        if record.status=='succeeded':
            if not isinstance(payload,dict) or set(payload)!={'residency','access','migration'}:
                raise ValueError('invalid tiering output schema')
            try:
                checked = _analyze_case(study,case,payload)
            except (KeyError,TypeError,IndexError) as exc:
                raise ValueError('malformed saved tiering observations/routes') from exc
            if canonical_json(checked)!=canonical_json(payload):
                raise ValueError('saved tiering observations disagree with declarations/routes')
            if canonical_json(sorted(record.metrics,key=lambda m:m.name))!=canonical_json(sorted(_metrics(checked),key=lambda m:m.name)):
                raise ValueError('tiering metrics disagree with reservations/data/unknown costs')
        rows.append({'case':case.name,'status':record.status,'expected_status':case.expected_status,'expectation_met':record.status==case.expected_status,
                     'result':payload,'diagnostic':record.diagnostic,'identity_hash':record.identity_hash})
        names.add(case.name)
        ids.add(record.run_id)
    if names!={c.name for c in study.cases}:
        raise ValueError('incomplete tiering study roster')
    return tuple(sorted(rows,key=lambda r:r['case']))


# Commit one complete checked study into a new immutable output directory.
def write_study(records: tuple[RunRecord, ...], directory: str | Path) -> Path:
    return write_records(records,directory,'system-tiering-index/v1',summarize_records)


# Decode records and verify saved static evidence without creating a new execution or data-transfer claim.
def read_study(directory: str | Path) -> tuple[RunRecord, ...]:
    return read_records(directory,'system-tiering-index/v1',summarize_records)
