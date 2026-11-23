"""Finite fixed-budget placement studies using the shared analytical runner and immutable artifacts."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from artifacts.storage.local import read_run, write_run
from contracts.hardware.network import validate_identity
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from clustermodel.composition.cluster.analysis import analyze_traffic
from clustermodel.composition.cluster.model import ClusterSpec, TrafficInput
from clustermodel.composition.cluster.traffic import describe_traffic
from clustermodel.composition.groups.model import CommunicationGroup, RankPlacement
from clustermodel.topology.graph import NetworkGraph, _freeze_records
from clustermodel.topology.inspection import inspect_network
from clustermodel.topology.scenarios import NetworkOutage, apply_outage
from evaluation.experiments.runner.single import run_experiment


# One candidate changes rank placement only; shared graph, groups and messages define the comparison budget.
@dataclass(frozen=True, slots=True, kw_only=True)
class PlacementCandidate:
    name: str  # Unique candidate identity; never interpreted as a filesystem path.
    placements: tuple[RankPlacement, ...]  # Requested placements; graph/group feasibility is checked inside the run.

    # Freeze rank identities while retaining invalid boundary references for recorded feasibility diagnostics.
    def __post_init__(self) -> None:
        validate_identity("candidate name", self.name)
        object.__setattr__(self, "placements", _freeze_records("placements", self.placements, RankPlacement, "rank_id"))


# A strict nonexecutable study declares a finite candidate roster and one common communication workload.
@dataclass(frozen=True, slots=True, kw_only=True)
class ClusterStudy:
    graph: NetworkGraph  # Identical node/fabric resource budget for all candidates.
    traffic: TrafficInput  # Identical data identities, lengths, routes/policy and requested cuts.
    candidates: tuple[PlacementCandidate, ...]  # Nonempty finite roster, including infeasible requested placements.
    groups: tuple[CommunicationGroup, ...] = ()  # Shared logical membership and ordering.
    outage: NetworkOutage | None = None  # Optional static channel/owner outage shared by every placement; original graph is retained.
    schema_version: Literal["cluster-placement-study/v1"] = "cluster-placement-study/v1"  # Comparison input schema.

    # Validate schema/types now; placement/reference failures must remain part of the candidate evidence.
    def __post_init__(self) -> None:
        if not isinstance(self.graph, NetworkGraph) or not isinstance(self.traffic, TrafficInput):
            raise TypeError("expected NetworkGraph and TrafficInput")
        object.__setattr__(self, "candidates", _freeze_records("candidates", self.candidates, PlacementCandidate, "name"))
        object.__setattr__(self, "groups", _freeze_records("groups", self.groups, CommunicationGroup, "group_id"))
        if not self.candidates:
            raise ValueError("study requires at least one candidate")
        if self.outage is not None and not isinstance(self.outage, NetworkOutage):
            raise TypeError("outage: expected NetworkOutage or None")
        if self.schema_version != "cluster-placement-study/v1":
            raise ValueError("unsupported cluster study schema_version")


# Adapt independent cluster analysis to standard metrics, preserving unknown costs and conditional lower bounds.
def evaluate_cluster(cluster: ClusterSpec, traffic: TrafficInput) -> tuple[object, tuple[Metric, ...]]:
    result = analyze_traffic(cluster, traffic)
    sources = tuple(sorted({message.route.src_endpoint_id for message in result.messages}))
    payload = {**asdict(result), "traffic_description": describe_traffic(cluster, traffic),
               "network_overview": inspect_network(cluster.graph, source_endpoint_ids=sources)}
    return payload, (
        Metric(name="logical_payload", value=result.logical_payload_bytes, unit="byte", kind="counter"),
        Metric(name="link_frame_bytes", value=result.total_link_wire_bytes, unit="byte", kind="counter",
               unknown_reason=result.wire_unknown_reason),
        Metric(name="resource_time_lower_bound", value=result.resource_time_lower_bound_s, unit="second", kind="lower_bound"),
        Metric(name="dependency_time_lower_bound", value=result.dependency_time_lower_bound_s, unit="second", kind="lower_bound"),
        Metric(name="cut_time_lower_bound", value=result.cut_time_lower_bound_s, unit="second", kind="lower_bound"),
        Metric(name="communication_time_lower_bound", value=result.communication_time_lower_bound_s, unit="second", kind="lower_bound"),
        Metric(name="network_energy", value=result.total_energy_j, unit="joule", kind="estimated",
               unknown_reason=result.energy_unknown_reason),
    )


# Assemble inside the recorded callback so missing endpoints, local paths and unreachable candidates are preserved.
def _evaluate_candidate(configuration: dict, traffic: TrafficInput) -> tuple[object, tuple[Metric, ...]]:
    candidate = next(item for item in configuration["candidates"] if item.name == configuration["selected_candidate"])
    outage = configuration.get("outage")
    view = apply_outage(configuration["graph"], outage) if outage is not None else None
    cluster = ClusterSpec(cluster_id=candidate.name, graph=view.graph if view else configuration["graph"],
                          groups=configuration["groups"], placements=candidate.placements)
    payload, metrics = evaluate_cluster(cluster, traffic)
    payload["outage_view"] = ({"original_graph_hash": view.original_graph_hash, "removed_link_ids": view.removed_link_ids,
                                "source_ref": view.outage.source_ref} if view else None)
    return payload, metrics


# Run every declared candidate with the same input/resource budget; no result-based filtering is performed.
def run_study(study: ClusterStudy, *, source_revision: str = "unrecorded") -> tuple[RunRecord, ...]:
    if not isinstance(study, ClusterStudy):
        raise TypeError("study: expected ClusterStudy")
    records = []
    for candidate in study.candidates:
        spec = ExperimentSpec(experiment_id=candidate.name, implementation_id="cluster-traffic-analysis/v1",
                              mode="analytical", source_revision=source_revision, assumptions=(
                                  "Fixed P2P demands all ready at origin; identical data, topology and capacity budget across placements",
                                  "Explicit directed switching; shortest-hop-lex/v1 or explicit/v1 fixed paths",
                                  "Q/C bounds conditional on supplied capacities; effective-service rates are not physical guarantees",
                                  "No local-node summary, queue execution, collective computation, AI quality or physical calibration",
                                  "Propagation/processing bound and resource/cut bounds combine by max; no inferred startup additivity",
                              ))
        configuration = {"graph": study.graph, "groups": study.groups, "candidates": study.candidates,
                         "selected_candidate": candidate.name, "schema_version": study.schema_version, "outage": study.outage}
        records.append(run_experiment(spec, configuration, study.traffic, _evaluate_candidate))
    return tuple(records)


# Reconstruct the complete roster from snapshots and reject mixed budgets, versions or missing candidate evidence.
def summarize_records(records: tuple[RunRecord, ...], *, include_overview: bool = False) -> tuple[dict[str, object], ...]:
    if not records:
        raise ValueError("no cluster records")
    rows, shared_identity, names, roster, run_ids = [], None, set(), None, set()
    for record in records:
        if record.spec.implementation_id != "cluster-traffic-analysis/v1" or record.spec.mode != "analytical":
            raise ValueError("expected cluster-traffic-analysis/v1 analytical record")
        configuration = parse_json(record.configuration_json)
        required = {"graph", "groups", "candidates", "selected_candidate", "schema_version"}
        if (not isinstance(configuration, dict) or not required.issubset(configuration)
                or set(configuration) - required - {"outage"}
                or configuration["schema_version"] != "cluster-placement-study/v1"):
            raise ValueError("invalid cluster study configuration snapshot")
        candidates = configuration["candidates"]
        if (not isinstance(candidates, list) or not candidates
                or any(not isinstance(item, dict) or set(item) != {"name", "placements"} for item in candidates)):
            raise ValueError("invalid cluster candidate roster")
        candidate_names = [item["name"] for item in candidates]
        for name in candidate_names:
            validate_identity("candidate name", name)
        if len(set(candidate_names)) != len(candidate_names):
            raise ValueError("duplicate cluster candidate in configuration roster")
        selected = configuration.pop("selected_candidate")
        identity = content_hash({"configuration": configuration, "inputs": parse_json(record.inputs_json),
                                 "source_revision": record.spec.source_revision, "assumptions": record.spec.assumptions})
        if shared_identity is not None and shared_identity != identity:
            raise ValueError("mixed cluster study budgets, inputs or source versions")
        shared_identity = identity
        roster = set(candidate_names)
        if selected != record.spec.experiment_id or selected not in roster or selected in names:
            raise ValueError("invalid or duplicate selected candidate")
        names.add(selected)
        if record.run_id in run_ids:
            raise ValueError("duplicate cluster run_id")
        run_ids.add(record.run_id)
        result = parse_json(record.output_json) if record.status == "succeeded" else None
        rows.append({"candidate": selected, "status": record.status, "identity_hash": record.identity_hash,
                     "source_revision": record.spec.source_revision, "diagnostic": record.diagnostic,
                     "logical_payload_bytes": result["logical_payload_bytes"] if result else None,
                     "link_frame_bytes": result["total_link_wire_bytes"] if result else None,
                     "resource_lower_bound_s": result["resource_time_lower_bound_s"] if result else None,
                     "communication_lower_bound_s": result["communication_time_lower_bound_s"] if result else None,
                     "bottleneck_resource_ids": result["bottleneck_resource_ids"] if result else None,
                     "cuts": result["cuts"] if result else None})
        if include_overview:
            rows[-1].update(network_overview=result.get("network_overview") if result else None,
                            traffic_description=result.get("traffic_description") if result else None,
                            outage_view=result.get("outage_view") if result else None)
    if names != roster:
        raise ValueError("incomplete cluster candidate roster")
    return tuple(sorted(rows, key=lambda row: row["candidate"]))


# Write all existing RunRecord bundles then a final study index; incomplete studies cannot silently lose failures.
def write_study(records: tuple[RunRecord, ...], directory: str | Path) -> Path:
    summarize_records(records)
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=False)
    entries = []
    for index, record in enumerate(sorted(records, key=lambda item: item.spec.experiment_id)):
        name = f"run-{index:04d}"
        write_run(record, target / name)
        entries.append({"directory": name, "run_id": record.run_id, "identity_hash": record.identity_hash})
    with (target / "index.json").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_json({"schema_version": "cluster-study-index/v1", "runs": entries}) + "\n")
    return target


# Verify a committed roster and each bundle's hashes; never execute the model while reading observations.
def read_study(directory: str | Path) -> tuple[RunRecord, ...]:
    target = Path(directory)
    index = parse_json((target / "index.json").read_text(encoding="utf-8"))
    if (not isinstance(index, dict) or set(index) != {"schema_version", "runs"}
            or index.get("schema_version") != "cluster-study-index/v1"):
        raise ValueError("unsupported cluster study index")
    entries = index.get("runs")
    if not isinstance(entries, list) or not entries:
        raise ValueError("cluster study index requires committed runs")
    records = []
    for position, entry in enumerate(entries):
        if (not isinstance(entry, dict) or set(entry) != {"directory", "run_id", "identity_hash"}
                or entry.get("directory") != f"run-{position:04d}"):
            raise ValueError("invalid cluster study bundle path/order")
        record = RunRecord.from_dict(read_run(target / entry["directory"]))
        if entry.get("run_id") != record.run_id or entry.get("identity_hash") != record.identity_hash:
            raise ValueError("cluster study index disagrees with run identity")
        records.append(record)
    summarize_records(tuple(records))
    return tuple(records)
