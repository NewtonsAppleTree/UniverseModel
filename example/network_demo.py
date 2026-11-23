"""Run/save/read a C1 isolated network link query with a validated two-endpoint graph."""

import argparse
from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Literal

from artifacts.storage.local import read_run, write_run
from clustermodel.fabric.links.model import estimate_link
from clustermodel.topology.graph import NetworkGraph, cut_capacity, get_link, reachable_endpoints
from configuration.resolution.dataclass_config import load_config
from contracts.hardware.network import validate_count
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from evaluation.experiments.runner.single import run_experiment


# The example selects an existing channel; link and endpoint parameters remain in the graph schema.
@dataclass(frozen=True, slots=True, kw_only=True)
class NetworkConfiguration:
    graph: NetworkGraph  # Validated direct-link network; no target queues or implicit forwarding.
    link_id: str  # Declared directional channel to query independently.

    # Reject a missing selected link before executing or recording a physical estimate.
    def __post_init__(self) -> None:
        get_link(self.graph, self.link_id)


# Input workload is separate from the hardware configuration; zero is an explicit empty query.
@dataclass(frozen=True, slots=True, kw_only=True)
class NetworkInputs:
    payload_bytes: int  # Logical message size [B]; exact nonnegative integer.

    # Numeric validation does not assert that a particular link profile supports this message size.
    def __post_init__(self) -> None:
        validate_count("payload_bytes", self.payload_bytes)


# A small example boundary reuses strict dataclass configuration and existing experiment artifacts.
@dataclass(frozen=True, slots=True, kw_only=True)
class NetworkCase:
    configuration: NetworkConfiguration  # Immutable graph and selected channel parameters.
    inputs: NetworkInputs  # Explicit logical message size, independent of graph identity.
    schema_version: Literal["network-link-example/v1"] = "network-link-example/v1"  # Example schema ID.

    # Direct Python construction and JSON resolution accept the same versioned example boundary.
    def __post_init__(self) -> None:
        if not isinstance(self.configuration, NetworkConfiguration) or not isinstance(self.inputs, NetworkInputs):
            raise TypeError("expected NetworkConfiguration and NetworkInputs")
        if self.schema_version != "network-link-example/v1":
            raise ValueError("unsupported network example schema_version")


# Query isolated link service and an outgoing cut; NIC/shared limits are recorded but not scheduled.
def evaluate_network(configuration: NetworkConfiguration, inputs: NetworkInputs) -> tuple[object, tuple[Metric, ...]]:
    graph = configuration.graph
    link = get_link(graph, configuration.link_id)
    source = next(endpoint for endpoint in graph.endpoints if endpoint.port_id == link.src_port_id)
    estimate = estimate_link(link, inputs.payload_bytes)
    cut = cut_capacity(graph, (source.node_id,))
    return {"link_id": link.link_id, "link_estimate": estimate, "outgoing_cut": cut,
            "reachable_endpoints": reachable_endpoints(graph, source.endpoint_id),
            "scope": "isolated link only; NIC/shared resource service and destination visibility not simulated"}, (
        Metric(name="payload_bytes", value=estimate.payload_bytes, unit="byte", kind="counter"),
        Metric(name="link_frame_bytes", value=estimate.wire_bytes, unit="byte", kind="counter",
               unknown_reason=estimate.wire_unknown_reason),
        Metric(name="link_serialization_time", value=estimate.serialization_s, unit="second", kind="estimated"),
        Metric(name="isolated_link_time", value=estimate.isolated_time_s, unit="second", kind="estimated"),
        Metric(name="outgoing_cut_link_capacity", value=cut.capacity_Bps, unit="byte_per_second", kind="estimated"),
        Metric(name="network_energy", value=None, unit="joule", kind="estimated",
               unknown_reason="No network energy characterization or execution duration is supplied"),
    )


# Reuse the generic runner; profile-domain errors become failed records with no fabricated metrics.
def run_case(case: NetworkCase, *, source_revision: str = "unrecorded") -> RunRecord:
    if not isinstance(case, NetworkCase):
        raise TypeError("case: expected NetworkCase")
    spec = ExperimentSpec(experiment_id="network-link-c1", implementation_id="network-link-demo/v1",
                          mode="analytical", source_revision=source_revision,
                          assumptions=("C1 direct-link graph; all explicit capacities are conditional model inputs",
                                       "Isolated message; no contention, NIC service, software launch, or destination visibility",
                                       "Outgoing cut is a link capacity sum, not attainable end-to-end throughput",
                                       "No AI numerical or physical network calibration claim"))
    return run_experiment(spec, case.configuration, case.inputs, evaluate_network)


# Print the same concise view for fresh and verified persisted records without rerunning the model.
def summarize(record: RunRecord) -> dict[str, object]:
    if record.spec.implementation_id != "network-link-demo/v1":
        raise ValueError("the artifact is not a network-link-demo/v1 record")
    return {"status": record.status, "mode": record.spec.mode, "source_revision": record.spec.source_revision,
            "identity_hash": record.identity_hash, "diagnostic": record.diagnostic,
            "metrics": [{"name": metric.name, "value": metric.value, "unit": metric.unit,
                         "kind": metric.kind, "unknown_reason": metric.unknown_reason} for metric in record.metrics]}


# Load explicit parameters, optionally override message size, and save/read through the existing bundle API.
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="JSON NetworkCase; defaults to config/experiments/network_link.json")
    parser.add_argument("--payload-bytes", type=int, help="override the logical message length [B]")
    parser.add_argument("--source-revision", help="source snapshot identity; default unrecorded")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--output", type=Path, help="write a new immutable run directory")
    mode.add_argument("--read", type=Path, help="verify/read a saved run without model execution")
    args = parser.parse_args()
    if args.read and any(value is not None for value in (args.config, args.payload_bytes, args.source_revision)):
        parser.error("--read cannot be combined with configuration or input overrides")
    try:
        if args.read:
            record = RunRecord.from_dict(read_run(args.read))
        else:
            path = args.config or Path(__file__).resolve().parents[1] / "config/experiments/network_link.json"
            case = load_config(NetworkCase, path)
            if args.payload_bytes is not None:
                case = replace(case, inputs=NetworkInputs(payload_bytes=args.payload_bytes))
            record = run_case(case, source_revision=args.source_revision or "unrecorded")
            if args.output:
                write_run(record, args.output)
        print(json.dumps(summarize(record), ensure_ascii=False, indent=2))
        return 0 if record.status == "succeeded" else 1
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
