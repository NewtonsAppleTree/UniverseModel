"""Independent fixed-path accounting references, routing counterexamples and sensitivity checks."""

from dataclasses import replace
from pathlib import Path
import unittest

from configuration.resolution.dataclass_config import load_config
from contracts.hardware.network import BandwidthConstraint
from contracts.versions.json_codec import content_hash
from clustermodel.composition.cluster.analysis import analyze_traffic
from clustermodel.composition.cluster.model import ClusterSpec, CutRequest, P2PMessage, TrafficInput
from clustermodel.composition.groups.model import CommunicationGroup, RankPlacement, validate_groups
from clustermodel.fabric.routing.paths import Route, resolve_route, validate_route
from clustermodel.fabric.switches.model import SwitchConnection, SwitchParams
from clustermodel.topology.builders import direct_network, single_switch_network, two_partition_network
from clustermodel.topology.graph import NetworkGraph, cut_capacity, reachable_endpoints
from evaluation.experiments.runner.cluster import ClusterStudy


CONFIG = Path(__file__).resolve().parents[2] / "config/experiments/cluster_placement.json"  # Explicit hand-calculated four-node fixture.
D = 134217728  # One fixture message [B] = 128 MiB.


# Assemble one immutable candidate; all numeric expected results below are independent constants.
def cluster(study, index=0):
    return ClusterSpec(cluster_id="test", graph=study.graph, groups=study.groups,
                       placements=study.candidates[index].placements)


# Build a diamond manually to exercise equal-hop paths, cycles and explicit revisits independently of builders.
def diamond(study):
    ports = {"a": ("a.in", "a.b", "a.c"), "b": ("b.a", "b.d"),
             "c": ("c.a", "c.d"), "d": ("d.b", "d.c", "d.out")}
    switches, limits = [], list(resource for resource in study.graph.constraints if resource.owner_id in ("n0", "n1"))
    for owner, owned in ports.items():
        limit = BandwidthConstraint(resource_id=f"{owner}.core", owner_id=owner, capacity_Bps=100e9,
                                    byte_basis="payload", capacity_kind="declared_ceiling", source_ref="test/v1", coverage=("one crossing",))
        limits.append(limit)
        switches.append(SwitchParams(switch_id=owner, port_ids=owned, forwarding_latency_s=0,
                                     source_ref="test/v1", coverage=("explicit diamond",), connections=tuple(
                                         SwitchConnection(ingress_port_id=i, egress_port_id=o, constraint_ids=(limit.resource_id,))
                                         for i in owned for o in owned if i != o)))
    wiring = (("start", "n0.p0", "a.in"), ("ab", "a.b", "b.a"), ("bd", "b.d", "d.b"),
              ("ac", "a.c", "c.a"), ("cd", "c.d", "d.c"), ("end", "d.out", "n1.p0"))
    links = tuple(replace(study.graph.links[0], link_id=name, src_port_id=src, dst_port_id=dst)
                  for name, src, dst in wiring)
    reverse = tuple(replace(item, link_id=f"rev-{item.link_id}", src_port_id=item.dst_port_id, dst_port_id=item.src_port_id)
                    for item in links)
    return NetworkGraph(graph_id="diamond", endpoints=study.graph.endpoints[:2], links=links + reverse,
                        constraints=limits, switches=switches, schema_version="routed-network-graph/v1")


# Validate analytical behavior and failure diagnostics using explicit integer and time references.
class ClusterTests(unittest.TestCase):
    # Load the static ideal fixture; no model call is used to generate expected arithmetic.
    def setUp(self):
        self.study = load_config(ClusterStudy, CONFIG)
        self.cluster = cluster(self.study)

    # Exact four-node acceptance values include shared switch work and per-direction uplink demand.
    def test_four_node_acceptance(self):
        first = analyze_traffic(self.cluster, self.study.traffic)
        second = analyze_traffic(cluster(self.study, 1), self.study.traffic)
        for result in (first, second):
            self.assertEqual(result.logical_payload_bytes, 268435456)
            self.assertAlmostEqual(max(item.time_lower_bound_s for item in result.resources if item.category == "nic"),
                                   0.00536870912, delta=1e-17)
        self.assertEqual(first.total_link_wire_bytes, 805306368)
        self.assertEqual(second.total_link_wire_bytes, 536870912)
        self.assertEqual(first.cuts[0].service_bytes, 268435456)
        self.assertEqual(second.cuts[0].service_bytes, 0)
        self.assertEqual(first.bottleneck_resource_ids, ("sL->sR",))
        self.assertAlmostEqual(first.resource_time_lower_bound_s, 0.02147483648, delta=1e-17)
        self.assertAlmostEqual(second.resource_time_lower_bound_s, 0.00536870912, delta=1e-17)
        self.assertEqual(first.resource_time_lower_bound_s / second.resource_time_lower_bound_s, 4)
        loads = {item.resource_id: item for item in first.resources}
        self.assertEqual(loads["sL.internal"].service_bytes, 268435456)
        self.assertEqual(loads["sR.internal"].service_bytes, 268435456)
        self.assertEqual(loads["sL->sR"].message_ids, ("m0", "m1"))

    # Faster uplinks first reduce the bound, then plateau at NIC/access service rather than scaling indefinitely.
    def test_uplink_sensitivity(self):
        for rate, expected in ((200e9, 0.01073741824), (400e9, 0.00536870912), (800e9, 0.00536870912)):
            graph = replace(self.study.graph, links=tuple(replace(item, line_rate_bps=rate)
                            if item.link_id in ("sL->sR", "sR->sL") else item for item in self.study.graph.links))
            result = analyze_traffic(replace(self.cluster, graph=graph), self.study.traffic)
            self.assertAlmostEqual(result.resource_time_lower_bound_s, expected, delta=1e-17)

    # Removing each real bottleneck separately exposes the others; a combined ideal ablation has no realism claim.
    def test_shared_resource_ablations(self):
        graph = replace(self.study.graph, constraints=tuple(replace(item, capacity_Bps=5e9)
                        if item.resource_id == "sL.internal" else item for item in self.study.graph.constraints))
        result = analyze_traffic(replace(self.cluster, graph=graph), self.study.traffic)
        self.assertEqual(result.bottleneck_resource_ids, ("sL.internal",))
        self.assertAlmostEqual(result.resource_time_lower_bound_s, 0.0536870912, delta=1e-17)
        released = replace(graph, constraints=tuple(replace(item, capacity_Bps=1e15)
                           if item.resource_id == "sL.internal" else item for item in graph.constraints))
        self.assertEqual(analyze_traffic(replace(self.cluster, graph=released), self.study.traffic).bottleneck_resource_ids, ("sL->sR",))

    # Full-duplex directions have independent work; a half-duplex medium charges both once to the same resource.
    def test_opposite_directions_and_half_duplex(self):
        traffic = replace(self.study.traffic, messages=(self.study.traffic.messages[0],
                          replace(self.study.traffic.messages[1], src_rank="r3", dst_rank="r2")))
        result = analyze_traffic(self.cluster, traffic)
        self.assertAlmostEqual(result.resource_time_lower_bound_s, 0.01073741824, delta=1e-17)
        self.assertEqual(result.bottleneck_resource_ids, ("sL->sR", "sR->sL"))
        medium = BandwidthConstraint(resource_id="medium", owner_id="fabric", capacity_Bps=12.5e9,
                                     byte_basis="payload", capacity_kind="declared_ceiling", source_ref="test/v1", coverage=("half duplex",))
        graph = replace(self.study.graph, constraints=self.study.graph.constraints + (medium,), links=tuple(
            replace(item, shared_constraint_ids=("medium",)) if item.link_id in ("sL->sR", "sR->sL") else item
            for item in self.study.graph.links))
        shared = analyze_traffic(replace(self.cluster, graph=graph), traffic)
        self.assertEqual(shared.total_link_wire_bytes, result.total_link_wire_bytes)
        self.assertEqual(shared.bottleneck_resource_ids, ("medium",))
        self.assertAlmostEqual(shared.resource_time_lower_bound_s, 0.02147483648, delta=1e-17)

    # Two ports of one node share a single NIC tx resource although their access links are independent.
    def test_multiport_shared_nic(self):
        eps = self.study.graph.endpoints
        extra = replace(eps[1], endpoint_id="e0b", node_id="n0", port_id="n0.p1",
                        tx_constraint_ids=("n0.tx",), rx_constraint_ids=("n0.rx",))
        graph = single_switch_network(graph_id="fabric", endpoints=(eps[0], extra, eps[2], eps[3]),
                                       constraints=tuple(item for item in self.study.graph.constraints if item.owner_id in ("n0", "n2", "n3")),
                                       access_profile=self.study.graph.links[0], switch_capacity_Bps=100e9,
                                       forwarding_latency_s=0, source_ref="test/v1")
        placements = (RankPlacement(rank_id="r0", node_id="n0", endpoint_id="e0"),
                      RankPlacement(rank_id="r1", node_id="n2", endpoint_id="e2"),
                      RankPlacement(rank_id="r2", node_id="n0", endpoint_id="e0b"),
                      RankPlacement(rank_id="r3", node_id="n3", endpoint_id="e3"))
        graph_cluster = ClusterSpec(cluster_id="shared", graph=graph, placements=placements, groups=self.study.groups)
        result = analyze_traffic(graph_cluster, replace(self.study.traffic, requested_cuts=()))
        self.assertAlmostEqual(result.resource_time_lower_bound_s, 0.01073741824, delta=1e-17)
        self.assertIn("n0.tx", result.bottleneck_resource_ids)
        self.assertEqual(next(item.service_bytes for item in result.resources if item.resource_id == "n0.tx"), 268435456)

    # Overlapping groups do not create bandwidth or extra transfers; many ranks may use the same endpoint.
    def test_overlapping_groups_and_incast(self):
        placements = tuple(replace(item, node_id="n2", endpoint_id="e2") if item.rank_id == "r3" else item
                           for item in self.cluster.placements)
        groups = (CommunicationGroup(group_id="g0", rank_ids=("r1", "r0", "r2")),
                  CommunicationGroup(group_id="g1", rank_ids=("r1", "r2", "r3")))
        modified = replace(self.cluster, placements=placements, groups=groups)
        result = analyze_traffic(modified, self.study.traffic)
        self.assertEqual(modified.groups[0].rank_ids, ("r1", "r0", "r2"))
        self.assertEqual(next(item.service_bytes for item in result.resources if item.resource_id == "n2.rx"), 268435456)
        self.assertEqual(result.logical_payload_bytes, 268435456)

    # Propagation and switch processing are a separate necessary path bound; link startup is isolated-profile data.
    def test_dependency_bound_uses_max_not_sum(self):
        graph = replace(self.study.graph, links=tuple(replace(item, propagation_s=0.01, startup_s=9)
                                                     for item in self.study.graph.links),
                        switches=tuple(replace(item, forwarding_latency_s=0.02) for item in self.study.graph.switches))
        result = analyze_traffic(replace(self.cluster, graph=graph), self.study.traffic)
        self.assertAlmostEqual(result.dependency_time_lower_bound_s, 0.07, delta=1e-16)
        self.assertAlmostEqual(result.communication_time_lower_bound_s, 0.07, delta=1e-16)
        self.assertAlmostEqual(result.resource_time_lower_bound_s, 0.02147483648, delta=1e-17)

    # An empty message set leaves every communication counter zero without inventing compute or leakage energy.
    def test_empty_and_single_node(self):
        graph = NetworkGraph(graph_id="empty", endpoints=self.study.graph.endpoints[:1], links=(),
                             constraints=tuple(item for item in self.study.graph.constraints if item.owner_id == "n0"))
        result = analyze_traffic(ClusterSpec(cluster_id="single", graph=graph, placements=()),
                                 TrafficInput(messages=(), requested_cuts=(CutRequest(cut_id="empty", node_ids=("n0",)),)))
        self.assertEqual(result.total_link_wire_bytes, 0)
        self.assertEqual(result.communication_time_lower_bound_s, 0)
        self.assertEqual(result.bottleneck_resource_ids, ())
        self.assertTrue(all(item.service_bytes == 0 for item in result.resources))
        self.assertIsNone(result.total_energy_j)
        self.assertTrue(result.energy_unknown_reason)

    # Same-node demand cannot use an out-and-back fabric route or disappear as free local work.
    def test_local_unknown_and_missing_references(self):
        invalid = ((replace(self.study.traffic.messages[0], dst_rank="r0"), "unsupported_local_path"),
                   (replace(self.study.traffic.messages[0], dst_rank="missing"), "unknown rank"),
                   (replace(self.study.traffic.messages[0], group_id="missing"), "unknown group"),
                   (replace(self.study.traffic.messages[0], group_id="g1"), "group member"))
        for message, diagnostic in invalid:
            with self.subTest(diagnostic=diagnostic), self.assertRaisesRegex(ValueError, diagnostic):
                analyze_traffic(self.cluster, TrafficInput(messages=(message,)))

    # Missing physical connectivity rejects positive demand instead of returning zero or infinity for an empty cut.
    def test_unreachable_and_empty_cut_demand(self):
        graph = replace(self.study.graph, links=tuple(item for item in self.study.graph.links
                                                      if item.link_id not in ("sL->sR", "sR->sL")))
        self.assertTrue(cut_capacity(graph, ("n0", "n1"), switch_ids=("sL",)).empty)
        with self.assertRaisesRegex(ValueError, "unreachable"):
            analyze_traffic(replace(self.cluster, graph=graph), self.study.traffic)

    # A used effective profile preserves unknown wire work; unused effective channels remain known zero work.
    def test_effective_unknown_and_nonuniform_profiles(self):
        first = self.study.graph.links[0]
        effective = replace(first, rate_basis="effective_payload", payload_bandwidth_Bps=20e9, line_rate_bps=None,
                            coding_efficiency=None, max_payload_bytes=None, header_bytes=None, trailer_bytes=None,
                            alignment_bytes=None, capacity_kind="effective_service")
        graph = replace(self.study.graph, links=(effective,) + self.study.graph.links[1:])
        result = analyze_traffic(replace(self.cluster, graph=graph), self.study.traffic)
        self.assertIsNone(result.total_link_wire_bytes)
        self.assertTrue(result.wire_unknown_reason)
        self.assertTrue(any(item.capacity_kind == "effective_service" for item in result.resources))
        empty = analyze_traffic(replace(self.cluster, graph=graph), TrafficInput(messages=()))
        self.assertEqual(empty.total_link_wire_bytes, 0)

    # The outgoing frame representation determines switch frame-service work, not the ingress packet format.
    def test_tail_and_switch_frame_basis(self):
        original = self.study.graph
        out = next(item for item in original.links if item.link_id == "sL->e1")
        tail = replace(out, max_payload_bytes=1024, header_bytes=32, alignment_bytes=64)
        limit = BandwidthConstraint(resource_id="sL.frames", owner_id="sL", capacity_Bps=25e9, byte_basis="frame",
                                    frame_format_id=tail.frame_format_id, capacity_kind="declared_ceiling", source_ref="test/v1",
                                    coverage=("outgoing frames counted once",))
        switches = tuple(replace(switch, connections=tuple(replace(connection, constraint_ids=connection.constraint_ids + (limit.resource_id,))
                          if connection.egress_port_id == out.src_port_id else connection for connection in switch.connections))
                         if switch.switch_id == "sL" else switch for switch in original.switches)
        graph = replace(original, links=tuple(tail if item.link_id == out.link_id else item for item in original.links),
                        switches=switches, constraints=original.constraints + (limit,))
        traffic = TrafficInput(messages=(replace(self.study.traffic.messages[0], payload_bytes=1025),))
        result = analyze_traffic(replace(cluster(self.study, 1), graph=graph), traffic)
        self.assertEqual(result.total_link_wire_bytes, 2177)
        self.assertEqual(next(item.service_bytes for item in result.resources if item.resource_id == "sL.frames"), 1152)
        self.assertEqual(next(item.service_bytes for item in result.resources if item.resource_id == "sL.internal"), 1025)
        with self.assertRaisesRegex(ValueError, "incompatible frame"):
            replace(graph, constraints=tuple(replace(item, frame_format_id="wrong") if item.resource_id == limit.resource_id else item
                                              for item in graph.constraints))

    # Every original byte is injected and received once; physical-hop totals exclude redundant capacity constraints.
    def test_message_conservation(self):
        result = analyze_traffic(self.cluster, self.study.traffic)
        for message in result.messages:
            self.assertEqual(sum(item.service_bytes for item in message.charges if item.role == "source_tx"), D)
            self.assertEqual(sum(item.service_bytes for item in message.charges if item.role == "destination_rx"), D)
            self.assertEqual(sum(item.estimate.wire_bytes for item in message.traversals), 402653184)
        self.assertEqual(sum(item.wire_bytes for item in result.links), 805306368)

    # Equivalent unordered resource/message/placement inputs produce byte-for-byte identical analytical outputs.
    def test_canonical_determinism_and_immutability(self):
        graph = replace(self.study.graph, endpoints=list(reversed(self.study.graph.endpoints)), links=list(reversed(self.study.graph.links)),
                        constraints=list(reversed(self.study.graph.constraints)), switches=list(reversed(self.study.graph.switches)))
        reordered = replace(self.cluster, graph=graph, placements=list(reversed(self.cluster.placements)), groups=list(reversed(self.cluster.groups)))
        messages = list(reversed(self.study.traffic.messages))
        traffic = replace(self.study.traffic, messages=messages)
        messages.clear()
        self.assertEqual(content_hash(analyze_traffic(reordered, traffic)), content_hash(analyze_traffic(self.cluster, self.study.traffic)))
        self.assertEqual(len(traffic.messages), 2)

    # Ordered members, explicit identity/type checks and group references reject silent rank loss.
    def test_group_validation(self):
        for members in ((), ("r0", "r0")):
            with self.assertRaises(ValueError):
                CommunicationGroup(group_id="bad", rank_ids=members)
        with self.assertRaisesRegex(ValueError, "unknown rank"):
            validate_groups(self.study.graph, self.cluster.placements, (CommunicationGroup(group_id="bad", rank_ids=("ghost",)),))
        with self.assertRaisesRegex(ValueError, "unknown endpoint"):
            replace(self.cluster, placements=(replace(self.cluster.placements[0], endpoint_id="ghost"),))
        with self.assertRaisesRegex(ValueError, "different node"):
            replace(self.cluster, placements=(replace(self.cluster.placements[0], node_id="n3"),))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            replace(self.cluster, placements=self.cluster.placements + self.cluster.placements[:1])

    # Positive payloads and mutually exclusive route selectors are part of the static traffic contract.
    def test_traffic_validation(self):
        message = self.study.traffic.messages[0]
        for size in (0, -1, True, 1.5):
            with self.subTest(size=size), self.assertRaises((ValueError, TypeError)):
                replace(message, payload_bytes=size)
        for changes in ({"explicit_link_ids": ("e0->sL",)}, {"route_policy": "explicit/v1"},
                        {"explicit_link_ids": (), "route_policy": "explicit/v1"}, {"route_policy": "adaptive"}):
            with self.assertRaises(ValueError):
                replace(message, **changes)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            TrafficInput(messages=(message, message))

    # Builder-generated physical attachments are explicit and preserve caller profile ownership/identity semantics.
    def test_builders_and_reachability(self):
        eps = self.study.graph.endpoints
        limits = tuple(item for item in self.study.graph.constraints if item.owner_id in ("n0", "n1"))
        direct = direct_network(graph_id="direct", endpoints=eps[:2], constraints=limits, link_profile=self.study.graph.links[0])
        self.assertEqual(resolve_route(direct, "e0", "e1").link_ids, ("e0->e1",))
        one = single_switch_network(graph_id="one", endpoints=eps[:2], constraints=limits, access_profile=self.study.graph.links[0],
                                     switch_capacity_Bps=100e9, forwarding_latency_s=0, source_ref="test/v1")
        self.assertEqual(resolve_route(one, "e0", "e1").link_ids, ("e0->s0", "s0->e1"))
        self.assertEqual(reachable_endpoints(self.study.graph, "e0"), ("e1", "e2", "e3"))
        rebuilt = two_partition_network(graph_id="fabric", left=eps[:2], right=eps[2:],
                                         constraints=tuple(item for item in self.study.graph.constraints if item.owner_id.startswith("n")),
                                         access_profile=self.study.graph.links[0], uplink_profile=next(item for item in self.study.graph.links if item.link_id == "sL->sR"),
                                         switch_capacity_Bps=100e9, forwarding_latency_s=0, source_ref=self.study.graph.switches[0].source_ref)
        self.assertEqual(content_hash(rebuilt), content_hash(self.study.graph))

    # Selected paths minimize physical hops; equal-hop choices use the complete canonical link sequence.
    def test_diamond_lexicographic_routing(self):
        graph = diamond(self.study)
        self.assertEqual(resolve_route(graph, "e0", "e1").link_ids, ("start", "ab", "bd", "end"))
        shuffled = replace(graph, links=tuple(reversed(graph.links)), switches=tuple(reversed(graph.switches)))
        self.assertEqual(resolve_route(shuffled, "e0", "e1"), resolve_route(graph, "e0", "e1"))
        explicit = resolve_route(graph, "e0", "e1", explicit_link_ids=("start", "ac", "cd", "end"), policy="explicit/v1")
        validate_route(graph, explicit)

    # Finite explicit walks can revisit fabric resources; cut and internal demand count actual crossings again.
    def test_explicit_cycle_crossings(self):
        graph = diamond(self.study)
        spec = ClusterSpec(cluster_id="cycle", graph=graph, placements=(
            RankPlacement(rank_id="r0", node_id="n0", endpoint_id="e0"), RankPlacement(rank_id="r1", node_id="n1", endpoint_id="e1")))
        message = replace(self.study.traffic.messages[0], group_id=None, payload_bytes=10, route_policy="explicit/v1",
                          explicit_link_ids=("start", "ab", "bd", "rev-cd", "rev-ac", "ab", "bd", "end"))
        result = analyze_traffic(spec, TrafficInput(messages=(message,), requested_cuts=(
            CutRequest(cut_id="a-out", node_ids=("n0",), switch_ids=("a",)),)))
        self.assertEqual(result.cuts[0].crossing_count, 2)
        self.assertEqual(result.cuts[0].service_bytes, 20)
        self.assertEqual(result.total_link_wire_bytes, 80)
        self.assertEqual(next(item.service_bytes for item in result.resources if item.resource_id == "a.core"), 20)

    # Broken directions and implicit NIC transit are rejected even when the topology contains legal wiring cycles.
    def test_invalid_routes_and_endpoint_transit(self):
        for path in (("sL->e0",), ("e0->sL", "sR->e2"), ("e0->sL", "sL->e1", "e1->sL", "sL->sR", "sR->e2")):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "invalid_route"):
                resolve_route(self.study.graph, "e0", "e2", explicit_link_ids=path, policy="explicit/v1")
        with self.assertRaisesRegex(ValueError, "unknown link"):
            validate_route(self.study.graph, Route(src_endpoint_id="e0", dst_endpoint_id="e2", link_ids=("absent",), policy="explicit/v1"))

    # Removing an internal connection removes reachability without deleting the physical wires.
    def test_switch_connections_are_authoritative(self):
        switches = tuple(replace(item, connections=()) if item.switch_id == "sL" else item for item in self.study.graph.switches)
        graph = replace(self.study.graph, switches=switches)
        self.assertEqual(reachable_endpoints(graph, "e0"), ())
        with self.assertRaisesRegex(ValueError, "unreachable"):
            resolve_route(graph, "e0", "e2")

    # Switch ports, resource owners and representation namespaces must remain unambiguous.
    def test_switch_schema_ownership_and_duplicates(self):
        graph = self.study.graph
        switch = graph.switches[0]
        with self.assertRaisesRegex(ValueError, "require routed"):
            replace(graph, schema_version="direct-network-graph/v1")
        with self.assertRaisesRegex(ValueError, "distinct"):
            replace(graph, switches=(replace(switch, switch_id="n0"),))
        with self.assertRaisesRegex(ValueError, "duplicate physical port"):
            replace(graph, endpoints=(replace(graph.endpoints[0], port_id=switch.port_ids[0]),) + graph.endpoints[1:])
        with self.assertRaisesRegex(ValueError, "different owner"):
            replace(graph, constraints=tuple(replace(item, owner_id="fabric") if item.resource_id == "sL.internal" else item for item in graph.constraints))
        with self.assertRaisesRegex(ValueError, "duplicate resource"):
            replace(graph, constraints=graph.constraints + (replace(graph.constraints[0], resource_id=graph.links[0].link_id),))
        with self.assertRaisesRegex(ValueError, "duplicate switch connection"):
            replace(switch, connections=switch.connections + switch.connections[:1])
        with self.assertRaisesRegex(ValueError, "unowned"):
            replace(switch, connections=(replace(switch.connections[0], ingress_port_id="ghost"),))
        with self.assertRaises(ValueError):
            replace(switch, forwarding_latency_s=float("nan"))

    # Cut capacity and demand require one compatible representation and explicit complete owner membership.
    def test_cut_validation(self):
        with self.assertRaisesRegex(ValueError, "unknown switch"):
            cut_capacity(self.study.graph, ("n0",), switch_ids=("absent",))
        links = tuple(replace(item, header_bytes=8) if item.link_id == "e0->sL" else item for item in self.study.graph.links)
        graph = replace(self.study.graph, links=links)
        with self.assertRaisesRegex(ValueError, "incompatible_byte_basis"):
            cut_capacity(graph, ("n0", "n1"))


if __name__ == "__main__":
    unittest.main()
