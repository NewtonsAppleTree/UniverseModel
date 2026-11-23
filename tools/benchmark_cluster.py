"""Reproducible host-only cluster benchmark; no host timing is a target network metric."""

import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]  # Repository root; benchmark uses the explicit fixture below.
sys.path.insert(0, str(ROOT))

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import content_hash
from clustermodel.composition.cluster.analysis import analyze_traffic
from clustermodel.composition.cluster.model import ClusterSpec, P2PMessage, TrafficInput
from clustermodel.composition.groups.model import RankPlacement
from clustermodel.topology.builders import leaf_spine_network
from clustermodel.topology.inspection import inspect_network
from evaluation.experiments.runner.cluster import ClusterStudy


# Expand an explicit ideal profile into a declared synthetic workload; graph construction remains separately timed.
def fixture(leaves, nodes_per_leaf, spines, pattern):
    study = load_config(ClusterStudy, ROOT / "config/experiments/cluster_leaf_spine.json")
    endpoint = study.graph.endpoints[0]
    resource = next(item for item in study.graph.constraints if item.resource_id == "n0.tx")
    count = leaves * nodes_per_leaf
    endpoints = tuple(replace(endpoint, endpoint_id=f"e{i}", node_id=f"n{i}", port_id=f"n{i}.p0",
                              tx_constraint_ids=(f"n{i}.tx",), rx_constraint_ids=(f"n{i}.rx",)) for i in range(count))
    constraints = tuple(replace(resource, resource_id=f"n{i}.{direction}", owner_id=f"n{i}")
                        for i in range(count) for direction in ("tx", "rx"))
    arguments = dict(graph_id="host-benchmark", leaves={f"l{i}": endpoints[i*nodes_per_leaf:(i+1)*nodes_per_leaf]
                                                     for i in range(leaves)},
                     spine_ids=tuple(f"s{i}" for i in range(spines)), constraints=constraints,
                     access_profile=study.graph.links[0],
                     uplink_profile=next(item for item in study.graph.links if item.link_id == "l0->s0"),
                     leaf_capacity_Bps=100e9, spine_capacity_Bps=100e9,
                     leaf_forwarding_latency_s=0, spine_forwarding_latency_s=0,
                     source_ref="manual:cluster-host-benchmark/v1")
    placements = tuple(RankPlacement(rank_id=f"r{i}", node_id=f"n{i}", endpoint_id=f"e{i}") for i in range(count))
    pairs = ([(i, j) for i in range(count) for j in range(count) if i != j] if pattern == "all-pairs"
             else [(i, (i + nodes_per_leaf) % count) for i in range(count) for _ in range(8)])
    traffic = TrafficInput(messages=tuple(P2PMessage(message_id=f"m{k:06d}", src_rank=f"r{i}", dst_rank=f"r{j}",
                                                    payload_bytes=1048576, data_id=f"d{k}", content_version="v1")
                                          for k, (i, j) in enumerate(pairs)))
    return arguments, placements, traffic


# Record individual wall-time samples and return the last result; no warm-up sample enters the median.
def measure(callback, samples):
    callback()
    values = []
    for _ in range(samples):
        start = perf_counter()
        result = callback()
        values.append(perf_counter() - start)
    return result, {"samples_s": values, "median_s": median(values)}


# Save exact inputs/output digests plus host timings and a separate tracemalloc peak, without overwriting evidence.
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--leaves", type=int, default=8)
    parser.add_argument("--nodes-per-leaf", type=int, default=8)
    parser.add_argument("--spines", type=int, default=4)
    parser.add_argument("--pattern", choices=("repeated", "all-pairs"), default="repeated")
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    if min(args.nodes_per_leaf, args.spines, args.samples) < 1 or args.leaves < 2:
        parser.error("positive sizes/samples and at least two leaves are required")
    if args.output.exists():
        parser.error("output already exists; use a new evidence path")
    arguments, placements, traffic = fixture(args.leaves, args.nodes_per_leaf, args.spines, args.pattern)
    graph, build_time = measure(lambda: leaf_spine_network(**arguments), args.samples)
    cluster = ClusterSpec(cluster_id="host-benchmark", graph=graph, placements=placements)
    result, analysis_time = measure(lambda: analyze_traffic(cluster, traffic), args.samples)
    overview, inspection_time = measure(lambda: inspect_network(graph, source_endpoint_ids=tuple(
        endpoint.endpoint_id for endpoint in graph.endpoints)), args.samples)
    tracemalloc.start()
    traced_result = analyze_traffic(cluster, traffic)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert traced_result == result
    files = sorted(path for directory in ("clustermodel", "contracts") for path in (ROOT / directory).rglob("*.py"))
    files.append(Path(__file__).resolve())
    sources = {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest() for path in files}
    payload = {"schema_version": "cluster-host-benchmark/v1", "python": sys.version, "platform": platform.platform(),
               "parameters": {key: value for key, value in vars(args).items() if key != "output"},
               "node_count": len(graph.node_ids), "direction_count": len(graph.links), "message_count": len(traffic.messages),
               "graph_hash": content_hash(graph), "input_hash": content_hash(traffic), "output_hash": content_hash(result),
               "overview_hash": content_hash(overview), "host_build": build_time, "host_analysis": analysis_time,
               "host_inspection": inspection_time, "host_analysis_tracemalloc_peak_bytes": peak,
               "source_files": sources,
               "coverage": "Host wall time and Python allocation peak only; synthetic fixture, no target performance claim"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    print(json.dumps({key: payload[key] for key in ("node_count", "message_count", "host_build", "host_analysis",
                                                   "host_inspection", "host_analysis_tracemalloc_peak_bytes", "output_hash")}))


if __name__ == "__main__":
    main()
