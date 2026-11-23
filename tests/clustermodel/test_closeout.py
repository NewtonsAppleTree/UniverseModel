"""Independent path search and batch accounting regressions for the cluster foundation closeout."""

from collections import deque
from dataclasses import replace
from pathlib import Path
import random
import unittest

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import content_hash
from clustermodel.composition.cluster.analysis import analyze_traffic
from clustermodel.composition.cluster.model import ClusterSpec, CutRequest, P2PMessage, TrafficInput
from clustermodel.fabric.routing.paths import resolve_route, shortest_route_choices
from clustermodel.topology.graph import reachable_endpoints
from clustermodel.topology.inspection import inspect_network
from clustermodel.topology.scenarios import NetworkOutage, apply_outage
from evaluation.experiments.runner.cluster import ClusterStudy

CONFIG = Path(__file__).resolve().parents[2] / "config/experiments/cluster_leaf_spine.json"  # Explicit six-node input fixture.


# Enumerate simple port walks breadth-first using only raw declarations, independently of production indices or routing.
def reference_paths(graph, source, destination):
    endpoints = {item.endpoint_id: item.port_id for item in graph.endpoints}
    terminals = set(endpoints.values())
    pending = deque([(endpoints[source], (), frozenset((endpoints[source],)))])
    paths, minimum = [], None
    while pending:
        port, path, visited = pending.popleft()
        if minimum is not None and len(path) > minimum:
            break
        if port == endpoints[destination]:
            minimum = len(path)
            paths.append(path)
            continue
        if (minimum is not None and len(path) >= minimum) or (path and port in terminals):
            continue
        departures = ({port} if not path else {connection.egress_port_id
                       for switch in graph.switches for connection in switch.connections
                       if connection.ingress_port_id == port})
        for link in graph.links:
            if link.src_port_id in departures and link.dst_port_id not in visited:
                pending.append((link.dst_port_id, path + (link.link_id,), visited | {link.dst_port_id}))
    return tuple(sorted(paths))


# Check query and batch semantics without asserting internal cache shape or wall-clock speed.
class CloseoutTests(unittest.TestCase):
    # Use an explicit graph and placement; expected numeric work is hand-counted in each case.
    def setUp(self):
        self.study = load_config(ClusterStudy, CONFIG)
        self.cluster = ClusterSpec(cluster_id="closeout", graph=self.study.graph,
                                   placements=self.study.candidates[0].placements, groups=self.study.groups)

    # Sparse crossings, fabric cycles and one-way outages retain exact shortest sequences and directional reachability.
    def test_routes_against_independent_walk_enumeration(self):
        generator = random.Random(20261123)
        base = self.study.graph
        for case in range(12):
            graph = base if case == 0 else replace(base,
                links=tuple(link for link in base.links if generator.random() > 0.25),
                switches=tuple(replace(switch, connections=tuple(connection for connection in switch.connections
                                                                 if generator.random() > 0.15)) for switch in base.switches))
            for source in graph.endpoints:
                expected_reachable = []
                for destination in graph.endpoints:
                    if source == destination:
                        continue
                    with self.subTest(case=case, source=source.endpoint_id, destination=destination.endpoint_id):
                        expected = reference_paths(graph, source.endpoint_id, destination.endpoint_id)
                        if not expected:
                            with self.assertRaisesRegex(ValueError, "unreachable"):
                                resolve_route(graph, source.endpoint_id, destination.endpoint_id)
                            with self.assertRaisesRegex(ValueError, "unreachable"):
                                shortest_route_choices(graph, source.endpoint_id, destination.endpoint_id)
                            continue
                        expected_reachable.append(destination.endpoint_id)
                        selected = resolve_route(graph, source.endpoint_id, destination.endpoint_id)
                        choices = shortest_route_choices(graph, source.endpoint_id, destination.endpoint_id, max_paths=1)
                        self.assertEqual(selected.link_ids, expected[0])
                        self.assertEqual(choices.minimum_hops, len(expected[0]))
                        self.assertEqual(choices.total_shortest_paths, len(expected))
                        self.assertEqual(choices.routes[0].link_ids, expected[0])
                        self.assertEqual(choices.truncated, len(expected) > 1)
                self.assertEqual(reachable_endpoints(graph, source.endpoint_id), tuple(expected_reachable))

    # Repeated endpoint pairs with different lengths/routes must retain tail framing and each real resource charge.
    def test_mixed_sizes_and_explicit_route_accounting(self):
        graph = replace(self.study.graph, links=tuple(replace(link, max_payload_bytes=1024, header_bytes=32,
                                                             alignment_bytes=64) for link in self.study.graph.links))
        template = P2PMessage(message_id="a", src_rank="r0", dst_rank="r2", payload_bytes=1025,
                              data_id="data", content_version="v1")
        messages = (template, replace(template, message_id="b", payload_bytes=2048),
                    replace(template, message_id="c", route_policy="explicit/v1",
                            explicit_link_ids=("e0->l0", "l0->s1", "s1->l1", "l1->e2")))
        traffic = TrafficInput(messages=messages, requested_cuts=(CutRequest(cut_id="leaf", node_ids=("n0", "n1"),
                                                                           switch_ids=("l0",)),))
        result = analyze_traffic(replace(self.cluster, graph=graph), traffic)
        self.assertEqual(result.logical_payload_bytes, 4098)
        self.assertEqual(result.total_link_wire_bytes, 17920)
        work = {item.resource_id: item.service_bytes for item in result.resources}
        self.assertEqual((work["n0.tx"], work["n2.rx"], work["l0.internal"]), (4098, 4098, 4098))
        self.assertEqual((work["l0->s0"], work["l0->s1"]), (3328, 1152))
        self.assertEqual((result.cuts[0].crossing_count, result.cuts[0].service_bytes), (3, 4480))
        self.assertEqual(result.cuts[0].message_ids, ("a", "b", "c"))

    # A profile edit on unchanged IDs must change results on the next call; no cache may survive the analysis boundary.
    def test_profile_replacement_and_input_identity(self):
        original_hash = content_hash(self.cluster)
        first = analyze_traffic(self.cluster, self.study.traffic)
        graph = replace(self.study.graph, links=tuple(replace(link, line_rate_bps=link.line_rate_bps / 2)
                                                      for link in self.study.graph.links))
        second = analyze_traffic(replace(self.cluster, graph=graph), self.study.traffic)
        self.assertEqual(second.communication_time_lower_bound_s, 2 * first.communication_time_lower_bound_s)
        self.assertEqual(first, analyze_traffic(self.cluster, self.study.traffic))
        self.assertEqual(content_hash(self.cluster), original_hash)

    # Primed baseline routes cannot leak into a new static view or make removed directions appear reachable.
    def test_outage_after_baseline_and_restoration(self):
        first = analyze_traffic(self.cluster, self.study.traffic)
        view = apply_outage(self.study.graph, NetworkOutage(disabled_switch_ids=("s0",), source_ref="test:closeout"))
        second = analyze_traffic(replace(self.cluster, graph=view.graph), self.study.traffic)
        self.assertEqual(second.total_link_wire_bytes, first.total_link_wire_bytes)
        self.assertFalse(any("s0" in identity for item in second.messages for identity in item.route.link_ids))
        disconnected = apply_outage(view.graph, NetworkOutage(disabled_switch_ids=("s1",), source_ref="test:closeout"))
        with self.assertRaisesRegex(ValueError, "unreachable"):
            analyze_traffic(replace(self.cluster, graph=disconnected.graph), self.study.traffic)
        self.assertEqual(inspect_network(disconnected.graph, source_endpoint_ids=("e0",)).reachability[0].reachable_remote_ids, ("e1",))
        self.assertEqual(analyze_traffic(self.cluster, self.study.traffic), first)

    # Caching a valid short message cannot bypass the domain check for a later longer message on the same path.
    def test_later_message_still_validates_profile_domain(self):
        graph = replace(self.study.graph, links=tuple(replace(link, profile_max_payload_bytes=1024)
                                                      for link in self.study.graph.links))
        first = P2PMessage(message_id="a", src_rank="r0", dst_rank="r2", payload_bytes=1, data_id="d", content_version="v1")
        with self.assertRaisesRegex(ValueError, "out_of_domain"):
            analyze_traffic(replace(self.cluster, graph=graph), TrafficInput(messages=(first, replace(first, message_id="b", payload_bytes=1025))))


if __name__ == "__main__":
    unittest.main()
