"""Node DMA/NIC and cluster composition with explicit routes and disjoint resource ledgers."""

from dataclasses import dataclass, replace
from pathlib import Path

from clustermodel.composition.cluster.analysis import analyze_traffic
from clustermodel.composition.cluster.model import ClusterSpec, TrafficInput, validate_traffic_references
from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.hardware.network import validate_identity
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from evaluation.experiments.runner.bundle import read_records, write_records
from evaluation.experiments.runner.single import run_experiment
from systemmodel.io.dma.analysis import analyze_transfers, validate_transfers
from systemmodel.io.dma.model import CopyBatch
from systemmodel.io.nic.model import NicBatch, NicSystem, analyze_nic
from systemmodel.topology.graph import freeze_inventory
from systemmodel.topology.query import SystemPath


# One node's simultaneous local work must be analyzed in a single batch to conserve shared demand and hazards.
@dataclass(frozen=True, slots=True, kw_only=True)
class NodeWork:
    node_id: str  # Existing physical node identity.
    nic: NicBatch | None = None  # Inter-node flows with explicit supply/drain buffers.
    local: CopyBatch | None = None  # Same-node messages served entirely by local DMA; no network charge.

    # Mixed local/fabric activity on one node needs an integrated schedule, outside this static batch adapter.
    def __post_init__(self) -> None:
        validate_identity('node_id',self.node_id)
        if (self.nic is None)==(self.local is None):
            raise ValueError('provide exactly one NIC or local DMA batch per node')
        if (self.nic is not None and not isinstance(self.nic,NicBatch)) or (self.local is not None and not isinstance(self.local,CopyBatch)):
            raise TypeError('invalid node work batch')


# Each P2P message binds both node endpoints or one entirely local whole-copy chain.
@dataclass(frozen=True, slots=True, kw_only=True)
class MessageBinding:
    message_id: str  # Exact cluster traffic identity.
    tx_flow_id: str | None = None  # Source-node NIC flow for an inter-node message.
    rx_flow_id: str | None = None  # Destination-node NIC flow for an inter-node message.
    local_chain_id: str | None = None  # Same-node copy chain, mutually exclusive with NIC flow IDs.

    # Reject partial endpoint references before semantic rank/object binding checks.
    def __post_init__(self) -> None:
        validate_identity('message_id',self.message_id)
        for name in ('tx_flow_id','rx_flow_id','local_chain_id'):
            if getattr(self,name) is not None:
                validate_identity(name,getattr(self,name))
        if not ((self.local_chain_id is not None and self.tx_flow_id is None and self.rx_flow_id is None)
                or (self.local_chain_id is None and self.tx_flow_id is not None and self.rx_flow_id is not None)):
            raise ValueError('binding requires either two NIC flows or one local chain')


# Every candidate uses the same node/fabric hardware; only demand and explicit paths/buffers vary.
@dataclass(frozen=True, slots=True, kw_only=True)
class NetworkCase:
    name: str  # Unique candidate identity.
    traffic: TrafficInput  # Exact simultaneous messages; remote routes must be explicit for deterministic replay.
    nodes: tuple[NodeWork, ...]  # One shared batch per active node.
    bindings: tuple[MessageBinding, ...]  # Complete message-to-service roster.
    expected_status: str = 'succeeded'  # Reviewed expectation, separate from actual feasibility.

    # Freeze finite rosters while retaining semantic failures for experiment records.
    def __post_init__(self) -> None:
        validate_identity('name',self.name)
        if not isinstance(self.traffic,TrafficInput) or self.expected_status not in ('succeeded','failed'):
            raise ValueError('invalid network case')
        object.__setattr__(self,'nodes',freeze_inventory('nodes',self.nodes,NodeWork,'node_id'))
        object.__setattr__(self,'bindings',freeze_inventory('bindings',self.bindings,MessageBinding,'message_id'))


# Hardware assembly joins actual standard-library endpoint exports, preserving one authoritative NIC budget.
@dataclass(frozen=True, slots=True, kw_only=True)
class NetworkStudy:
    systems: tuple[NicSystem, ...]  # Node hardware, uniquely identified by topology scope.
    cluster: ClusterSpec  # Fabric graph, exact exported endpoints/capacities and rank placements.
    cases: tuple[NetworkCase, ...]  # Complete success/failure study.

    # Require exact endpoint/service snapshots and globally disjoint node resources before composition.
    def __post_init__(self) -> None:
        if not isinstance(self.cluster,ClusterSpec) or not isinstance(self.systems,(tuple,list)) or not self.systems or any(not isinstance(s,NicSystem) for s in self.systems):
            raise TypeError('invalid network study hardware')
        object.__setattr__(self,'systems',tuple(sorted(self.systems,key=lambda s:s.dma.memory.node.topology.scope_id)))
        object.__setattr__(self,'cases',freeze_inventory('cases',self.cases,NetworkCase,'name'))
        nodes = [s.dma.memory.node.topology.scope_id for s in self.systems]
        resources = [r.instance_id for s in self.systems for r in s.dma.memory.node.topology.resources]
        if len(set(nodes))!=len(nodes) or len(set(resources))!=len(resources) or not self.cases:
            raise ValueError('nodes need globally unique physical resource identities and nonempty cases')
        endpoints = {p.endpoint.endpoint_id:p.endpoint for s in self.systems for p in s.ports}
        if len(endpoints)!=sum(len(s.ports) for s in self.systems) or endpoints!={p.endpoint_id:p for p in self.cluster.graph.endpoints}:
            raise ValueError('cluster endpoints must equal actual node NIC exports')
        limits = {c.resource_id:c for s in self.systems for c in s.constraints}
        installed = {c.resource_id:c for c in self.cluster.graph.constraints}
        if any(installed.get(k)!=v for k,v in limits.items()):
            raise ValueError('cluster NIC capacity differs from authoritative node export')
        extra = set(installed)-set(limits)
        if any(installed[k].owner_id in nodes for k in extra) or set(resources).intersection(extra|{l.link_id for l in self.cluster.graph.links}):
            raise ValueError('node-local summary or fabric resource duplicates node accounting')


# Saved local evidence supplies exact paths; a missing path cannot fall back to a producer search.
def _paths(saved: dict, node: str, nic: bool) -> tuple[SystemPath, ...]:
    value = saved['nodes'][node]
    value = value['dma'] if nic else value
    return tuple(resolve_dataclass(SystemPath,leg['path']) for leg in value['legs'])


# Compose supply/drain, NIC and fabric necessary bounds by max; no completed-message or overlap schedule is inferred.
def analyze_network(study: NetworkStudy, case: NetworkCase, saved: dict | None = None) -> dict:
    validate_traffic_references(study.cluster,case.traffic)
    systems = {s.dma.memory.node.topology.scope_id:s for s in study.systems}
    nodes,local_bounds,local_resources = {},[],set()
    expected_flows,used_flows,expected_local,used_local = set(),set(),set(),set()
    for work in case.nodes:
        if work.node_id not in systems:
            raise ValueError('unknown node work')
        system = systems[work.node_id]
        if work.nic is not None:
            result = analyze_nic(system,work.nic,saved_paths=None if saved is None else _paths(saved,work.node_id,True))
            dma = result.dma
            expected_flows.update((work.node_id,f.flow_id) for f in work.nic.flows)
        else:
            result = analyze_transfers(system.dma,work.local) if saved is None else validate_transfers(system.dma,work.local,_paths(saved,work.node_id,False))
            dma = result
            expected_local.update((work.node_id,c.chain_id) for c in work.local.chains)
        nodes[work.node_id]=result
        local_bounds.append(dma.bounds.lower_bound_s)
        local_resources.update(c.resource_id for c in dma.contributions)
    placements = {p.rank_id:p for p in study.cluster.placements}
    messages = {m.message_id:m for m in case.traffic.messages}
    work_by_node = {w.node_id:w for w in case.nodes}
    if {b.message_id for b in case.bindings}!=set(messages):
        raise ValueError('incomplete message bindings')
    remote = []
    for binding in case.bindings:
        message = messages[binding.message_id]
        src,dst = placements[message.src_rank],placements[message.dst_rank]
        if src.node_id==dst.node_id:
            key = (src.node_id,binding.local_chain_id)
            if key not in expected_local or key in used_local:
                raise ValueError('local message needs exactly one unshared local copy chain')
            used_local.add(key)
            batch = work_by_node[src.node_id].local
            legs = [l for l in nodes[src.node_id].legs if l.chain_id==binding.local_chain_id]
            for span in (legs[0].source,legs[-1].target):
                obj = next(o for o in batch.placement.objects if o.object_id==span.object_id)
                if (span.object_id,obj.source_ref,span.length_bytes)!=(message.data_id,message.content_version,message.payload_bytes):
                    raise ValueError('local message data/version/length differs from copy')
            allocations = {a.allocation_id:a for a in batch.placement.allocations}
            if legs[0].source.physical_offset_bytes-allocations[legs[0].source.allocation_id].offset_bytes!=legs[-1].target.physical_offset_bytes-allocations[legs[-1].target.allocation_id].offset_bytes:
                raise ValueError('local message changes object offset')
        else:
            if message.route_policy!='explicit/v1' or binding.local_chain_id is not None:
                raise ValueError('remote composition requires an explicit fabric route and both NIC flows')
            observed = []
            modes = []
            for placement,identity,direction in ((src,binding.tx_flow_id,'tx'),(dst,binding.rx_flow_id,'rx')):
                key = (placement.node_id,identity)
                if key not in expected_flows or key in used_flows:
                    raise ValueError('remote message needs unique source TX/destination RX flow')
                used_flows.add(key)
                flow = next(f for f in nodes[placement.node_id].flows if f.flow_id==identity)
                if (flow.endpoint_id,flow.direction,flow.object_id,flow.content_version,flow.payload_bytes)!=(placement.endpoint_id,direction,message.data_id,message.content_version,message.payload_bytes):
                    raise ValueError('message rank/endpoint/data/version/length mismatch')
                observed.append(flow.object_offset_bytes)
                modes.append(next(f.mode for f in work_by_node[placement.node_id].nic.flows if f.flow_id==identity))
            if observed[0]!=observed[1] or modes[0]!=modes[1]:
                raise ValueError('remote object offset or RDMA mode mismatch')
            remote.append(message)
    if expected_flows!=used_flows or expected_local!=used_local:
        raise ValueError('unbound or duplicated local/NIC work')
    fabric = analyze_traffic(study.cluster,replace(case.traffic,messages=tuple(remote)))
    if local_resources.intersection(r.resource_id for r in fabric.resources):
        raise ValueError('local service and NIC/fabric ledgers overlap')
    local_bound = max(local_bounds,default=0.0)
    return {'nodes':nodes,'fabric':fabric,'local_payload_bytes':sum(messages[b.message_id].payload_bytes for b in case.bindings if b.local_chain_id is not None),
            'logical_payload_bytes':sum(m.payload_bytes for m in messages.values()),'local_lower_bound_s':local_bound,
            'known_service_lower_bound_s':max(local_bound,fabric.communication_time_lower_bound_s),
            'unknown_costs':('Relaxed simultaneous fixed-route service bounds only; no local/fabric completion schedule',
                             'Buffered data/content availability, RDMA remote authentication/ordering/coherence and complete energy unmodeled')}


# Known necessary work/time and unknown complete execution remain separate metrics.
def _metrics(result: dict) -> tuple[Metric, ...]:
    return (Metric(name='logical_payload_bytes',value=result['logical_payload_bytes'],unit='byte',kind='counter'),
            Metric(name='known_service_lower_bound',value=result['known_service_lower_bound_s'],unit='second',kind='lower_bound'),
            Metric(name='target_execution_time',value=None,unit='second',kind='estimated',unknown_reason='No composed completion/visibility schedule'),
            Metric(name='target_energy',value=None,unit='joule',kind='estimated',unknown_reason='No calibrated complete node/fabric energy'))


# Produce one static candidate; failures remain immutable unsuccessful attempts.
def _evaluate(config: dict, inputs: dict) -> tuple[dict, tuple[Metric, ...]]:
    result = analyze_network(config['study'],inputs['case'])
    return result,_metrics(result)


# Preserve the full hardware/budget and candidate roster in every record.
def run_study(study: NetworkStudy, *, source_revision: str = 'unrecorded') -> tuple[RunRecord, ...]:
    return tuple(run_experiment(ExperimentSpec(experiment_id=case.name,implementation_id='system-network-study/v1',mode='analytical',source_revision=source_revision,
        assumptions=('Buffered NIC with explicit DMA supply/drain; actual endpoint exports charged once by cluster',
                     'Fixed explicit fabric routes; local and fabric bounds combine by max, execution/coherence/energy unknown')),
        {'study':study,'selected':case.name},{'case':case},_evaluate) for case in study.cases)


# Replay declarations and exact saved local routes; no producer or fabric path selection runs.
def summarize_records(records: tuple[RunRecord, ...]) -> tuple[dict, ...]:
    if not records or any(not isinstance(r,RunRecord) for r in records):
        raise ValueError('expected complete network records')
    common,names,ids,rows = None,set(),set(),[]
    for record in records:
        if (record.spec.implementation_id,record.spec.mode)!=('system-network-study/v1','analytical'):
            raise ValueError('wrong network record kind')
        config,inputs = parse_json(record.configuration_json),parse_json(record.inputs_json)
        if not isinstance(config,dict) or set(config)!={'study','selected'} or not isinstance(inputs,dict) or set(inputs)!={'case'}:
            raise ValueError('invalid network snapshot')
        study = resolve_dataclass(NetworkStudy,config['study'])
        digest = content_hash((study,record.spec.source_revision,record.spec.assumptions))
        if common is not None and common!=digest:
            raise ValueError('mixed network source/budget/roster')
        common = digest
        case = next((c for c in study.cases if c.name==config['selected']),None)
        if case is None or case.name!=record.spec.experiment_id or case.name in names or record.run_id in ids or canonical_json(case)!=canonical_json(inputs['case']):
            raise ValueError('invalid network selection/input identity')
        payload = parse_json(record.output_json) if record.status=='succeeded' else None
        if record.status=='succeeded':
            try:
                if not isinstance(payload,dict):
                    raise ValueError('missing network observations')
                checked = analyze_network(study,case,payload)
            except (KeyError,TypeError,IndexError,StopIteration,AttributeError) as exc:
                raise ValueError('malformed saved network evidence') from exc
            if canonical_json(checked)!=canonical_json(payload) or canonical_json(sorted(_metrics(checked),key=lambda m:m.name))!=canonical_json(sorted(record.metrics,key=lambda m:m.name)):
                raise ValueError('network work/path/metric observations disagree')
        rows.append({'case':case.name,'status':record.status,'expected_status':case.expected_status,'expectation_met':record.status==case.expected_status,
                     'result':payload,'diagnostic':record.diagnostic,'identity_hash':record.identity_hash})
        names.add(case.name)
        ids.add(record.run_id)
    if names!={c.name for c in study.cases}:
        raise ValueError('incomplete network roster')
    return tuple(sorted(rows,key=lambda r:r['case']))


# Save only a complete verified study into a fresh output directory.
def write_study(records: tuple[RunRecord, ...], directory: str | Path) -> Path:
    return write_records(records,directory,'system-network-index/v1',summarize_records)


# Read immutable observations and validate static accounting without a new experiment callback.
def read_study(directory: str | Path) -> tuple[RunRecord, ...]:
    return read_records(directory,'system-network-index/v1',summarize_records)
