"""Horizontal coverage: leaf-spine, route diversity, availability views and demand inventories."""

from dataclasses import replace
from pathlib import Path
import unittest

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import content_hash
from clustermodel.composition.cluster.analysis import analyze_traffic
from clustermodel.composition.cluster.model import ClusterSpec, TrafficInput, validate_traffic_references
from clustermodel.composition.cluster.traffic import describe_traffic
from clustermodel.composition.groups.model import CommunicationGroup, RankPlacement
from clustermodel.fabric.routing.paths import resolve_route, shortest_route_choices, validate_route
from clustermodel.topology.builders import leaf_spine_network
from clustermodel.topology.inspection import inspect_network
from clustermodel.topology.scenarios import NetworkOutage, apply_outage
from evaluation.experiments.runner.cluster import ClusterStudy


CONFIG = Path(__file__).resolve().parents[2] / "config/experiments/cluster_leaf_spine.json"  # Six nodes, three leaves and two spines.
D = 1048576  # One synthetic P2P demand [B] = 1 MiB; not a collective numerical model.


# Rebuild fixture resources with caller-selected partitions; expected counts and routes remain independent constants.
def build(study, *, leaves=None, spines=("s0", "s1")):
    graph = study.graph
    return leaf_spine_network(graph_id=graph.graph_id,
                              leaves=leaves if leaves is not None else {f"l{i}": graph.endpoints[2*i:2*i+2] for i in range(3)},
                              spine_ids=spines, constraints=tuple(item for item in graph.constraints if item.owner_id in graph.node_ids),
                              access_profile=graph.links[0], uplink_profile=next(item for item in graph.links if item.link_id == "l0->s0"),
                              leaf_capacity_Bps=100e9, spine_capacity_Bps=100e9, leaf_forwarding_latency_s=0,
                              spine_forwarding_latency_s=0, source_ref=graph.switches[0].source_ref)


# Cross-scenario assertions test independent counts, directionality, identities and logical conservation.
class BreadthTests(unittest.TestCase):
    # The JSON fixture is an explicit resource declaration, not a source of expected output values.
    def setUp(self):
        self.study = load_config(ClusterStudy, CONFIG)
        self.graph = self.study.graph
        self.cluster = ClusterSpec(cluster_id="breadth", graph=self.graph, placements=self.study.candidates[0].placements,
                                   groups=self.study.groups)

    # Twelve physical attachments contain 24 directions, without multiplying shared NICs or switch capacities.
    def test_inventory_and_builder_equivalence(self):
        self.assertEqual(content_hash(build(self.study)), content_hash(self.graph))
        inventory = inspect_network(self.graph)
        self.assertEqual((inventory.node_count, inventory.endpoint_count, inventory.switch_count), (6, 6, 5))
        self.assertEqual((inventory.constraint_count, inventory.directed_link_count), (17, 24))
        self.assertEqual((inventory.physical_connection_count, inventory.bidirectional_connection_count), (12, 12))
        self.assertEqual(inventory.one_way_connection_count, 0)
        self.assertEqual(inventory.reachability, ())

    # Nonuniform leaf populations are supported without padding nodes or presuming a power-of-two topology.
    def test_nonuniform_partitions_and_single_spine(self):
        graph = build(self.study, leaves={"l0": self.graph.endpoints[:1], "l1": self.graph.endpoints[1:4], "l2": self.graph.endpoints[4:]},
                      spines=("s0",))
        self.assertEqual(len(graph.links), 18)
        self.assertEqual(resolve_route(graph, "e1", "e3").link_ids, ("e1->l1", "l1->e3"))
        self.assertEqual(shortest_route_choices(graph, "e0", "e5").total_shortest_paths, 1)

    # Mapping insertion order and endpoint/spine array order do not change generated physical identity.
    def test_builder_order_invariance(self):
        leaves = {f"l{i}": tuple(reversed(self.graph.endpoints[2*i:2*i+2])) for i in (2, 1, 0)}
        rebuilt = build(self.study, leaves=leaves, spines=("s1", "s0"))
        self.assertEqual(content_hash(rebuilt), content_hash(self.graph))

    # Invalid topology partitions fail rather than silently reassigning endpoints to the last leaf definition.
    def test_builder_rejects_ambiguous_partitions(self):
        invalid = (({}, ("s0",)), ({"l0": ()}, ("s0",)), ({"l0": self.graph.endpoints}, ()),
                   ({"l0": self.graph.endpoints}, ("l0",)),
                   ({"l0": self.graph.endpoints, "l1": self.graph.endpoints[:1]}, ("s0",)))
        for leaves, spines in invalid:
            with self.subTest(leaves=leaves.keys(), spines=spines), self.assertRaises((ValueError, TypeError)):
                build(self.study, leaves=leaves, spines=spines)

    # Two shortest cross-leaf sequences share access links; diversity is not a twofold NIC capacity claim.
    def test_shortest_choices_and_shared_access(self):
        result = shortest_route_choices(self.graph, "e0", "e2")
        self.assertEqual((result.minimum_hops, result.total_shortest_paths, result.truncated), (4, 2, False))
        self.assertEqual(tuple(route.link_ids for route in result.routes), (
            ("e0->l0", "l0->s0", "s0->l1", "l1->e2"),
            ("e0->l0", "l0->s1", "s1->l1", "l1->e2")))
        self.assertEqual(set(result.routes[0].link_ids) & set(result.routes[1].link_ids), {"e0->l0", "l1->e2"})
        self.assertEqual(result.routes[0].link_ids, resolve_route(self.graph, "e0", "e2").link_ids)
        for route in result.routes:
            validate_route(self.graph, route)

    # Exact counts remain available when enumeration is deliberately capped below the number of choices.
    def test_many_paths_bounded_materialization(self):
        graph = build(self.study, spines=tuple(f"s{i:02d}" for i in range(12)))
        result = shortest_route_choices(graph, "e0", "e2", max_paths=1)
        self.assertEqual(result.total_shortest_paths, 12)
        self.assertEqual(len(result.routes), 1)
        self.assertTrue(result.truncated)
        local_leaf = shortest_route_choices(graph, "e0", "e1", max_paths=1)
        self.assertEqual((local_leaf.minimum_hops, local_leaf.total_shortest_paths, local_leaf.truncated), (2, 1, False))

    # Path queries honor finite explicit limits, remote scope and missing-connectivity diagnostics.
    def test_path_query_boundaries(self):
        for cap in (0, -1, True, 1.5):
            with self.subTest(cap=cap), self.assertRaises((ValueError, TypeError)):
                shortest_route_choices(self.graph, "e0", "e2", max_paths=cap)
        with self.assertRaisesRegex(ValueError, "unsupported_local_path"):
            shortest_route_choices(self.graph, "e0", "e0")
        with self.assertRaisesRegex(ValueError, "unknown endpoint"):
            shortest_route_choices(self.graph, "absent", "e2")
        graph = apply_outage(self.graph, NetworkOutage(source_ref="test/v1", disabled_switch_ids=("s0", "s1"))).graph
        with self.assertRaisesRegex(ValueError, "unreachable"):
            shortest_route_choices(graph, "e0", "e2")

    # A static unavailable spine leaves installed ownership intact and provides a deterministic alternative path.
    def test_spine_outage_provenance_and_rerouting(self):
        before = content_hash(self.graph)
        view = apply_outage(self.graph, NetworkOutage(source_ref="maintenance/v1", disabled_switch_ids=("s0",)))
        self.assertEqual(view.original_graph_hash, before)
        self.assertEqual(content_hash(self.graph), before)
        self.assertEqual(len(view.removed_link_ids), 6)
        self.assertEqual(view.graph.endpoints, self.graph.endpoints)
        self.assertEqual(view.graph.constraints, self.graph.constraints)
        self.assertEqual(inspect_network(view.graph).switch_count, 5)
        self.assertEqual(inspect_network(view.graph).directed_link_count, 18)
        self.assertEqual(resolve_route(view.graph, "e0", "e2").link_ids, ("e0->l0", "l0->s1", "s1->l1", "l1->e2"))
        self.assertEqual(shortest_route_choices(view.graph, "e0", "e2").total_shortest_paths, 1)

    # Explicit routes remain pinned after an outage; only a new selected-route query chooses a surviving path.
    def test_outage_does_not_rewrite_explicit_routes(self):
        message = next(item for item in self.study.traffic.messages if item.message_id == "m0-2")
        route = resolve_route(self.graph, "e0", "e2")
        pinned = replace(message, route_policy="explicit/v1", explicit_link_ids=route.link_ids)
        graph = apply_outage(self.graph, NetworkOutage(source_ref="test/v1", disabled_switch_ids=("s0",))).graph
        with self.assertRaisesRegex(ValueError, "unknown link"):
            analyze_traffic(replace(self.cluster, graph=graph), TrafficInput(messages=(pinned,)))
        self.assertEqual(len(analyze_traffic(replace(self.cluster, graph=graph), TrafficInput(messages=(message,))).messages), 1)

    # Removing outgoing leaf uplinks preserves reverse traffic; reachability is not silently symmetrized.
    def test_directional_outage_and_reachability(self):
        view = apply_outage(self.graph, NetworkOutage(source_ref="test/v1", disabled_link_ids=("l0->s0", "l0->s1")))
        report = inspect_network(view.graph, source_endpoint_ids=("e0", "e2"))
        self.assertEqual(report.one_way_connection_count, 2)
        self.assertEqual(report.bidirectional_connection_count, 10)
        self.assertEqual(report.reachability[0].reachable_remote_ids, ("e1",))
        self.assertEqual(report.reachability[0].unreachable_remote_ids, ("e2", "e3", "e4", "e5"))
        self.assertIn("e0", report.reachability[1].reachable_remote_ids)
        self.assertEqual(set(view.removed_link_ids), {"l0->s0", "l0->s1"})

    # A disabled node retains its ranks and logical demand, which fails instead of being removed from the workload.
    def test_node_outage_keeps_demand(self):
        view = apply_outage(self.graph, NetworkOutage(source_ref="test/v1", disabled_node_ids=("n0",)))
        value = replace(self.cluster, graph=view.graph)
        report = inspect_network(view.graph, source_endpoint_ids=("e0",))
        self.assertEqual(report.unattached_endpoint_ids, ("e0",))
        self.assertEqual(report.node_count, 6)
        self.assertEqual(len(report.reachability[0].unreachable_remote_ids), 5)
        self.assertEqual(describe_traffic(value, self.study.traffic).logical_payload_bytes, 31457280)
        with self.assertRaisesRegex(ValueError, "unreachable"):
            analyze_traffic(value, self.study.traffic)

    # Empty and overlapping selectors are deterministic; nonexistent failures cannot be mistaken for no effect.
    def test_outage_selector_validation_and_union(self):
        self.assertEqual(apply_outage(self.graph, NetworkOutage(source_ref="none/v1")).graph, self.graph)
        view = apply_outage(self.graph, NetworkOutage(source_ref="test/v1", disabled_switch_ids=("s0",), disabled_link_ids=("l0->s0",)))
        self.assertEqual(len(view.removed_link_ids), 6)
        for field in ("disabled_link_ids", "disabled_node_ids", "disabled_switch_ids"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "unknown identities"):
                apply_outage(self.graph, NetworkOutage(source_ref="test/v1", **{field: ("absent",)}))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            NetworkOutage(source_ref="test/v1", disabled_switch_ids=("s0", "s0"))
        with self.assertRaises(ValueError):
            inspect_network(self.graph, source_endpoint_ids=("absent",))

    # A 6x6 off-diagonal matrix conserves 30 messages, five sends/receives per participant and 30 MiB total.
    def test_demand_inventory_conservation(self):
        report = describe_traffic(self.cluster, self.study.traffic)
        self.assertEqual((report.message_count, report.logical_payload_bytes), (30, 31457280))
        self.assertEqual((report.local_payload_bytes, report.inter_node_payload_bytes), (0, 31457280))
        self.assertEqual(len(report.node_matrix), 30)
        self.assertEqual(sum(item.payload_bytes for item in report.node_matrix), 31457280)
        for table in (report.per_rank, report.per_node, report.per_endpoint):
            self.assertEqual(len(table), 6)
            self.assertTrue(all(item.sent_payload_bytes == 5242880 and item.received_payload_bytes == 5242880 for item in table))
            self.assertEqual(sum(item.sent_message_count for item in table), 30)
            self.assertEqual(sum(item.received_message_count for item in table), 30)

    # Overlapping memberships create no attribution duplicates, and an ungrouped message remains explicitly ungrouped.
    def test_group_attribution_and_idle_participants(self):
        groups = (CommunicationGroup(group_id="g0", rank_ids=("r0", "r1", "r2")),
                  CommunicationGroup(group_id="g1", rank_ids=("r1", "r2", "r3")))
        first = replace(self.study.traffic.messages[0], group_id="g0")
        second = replace(next(item for item in self.study.traffic.messages if item.message_id == "m1-2"), group_id="g1")
        third = replace(first, message_id="ungrouped", group_id=None)
        report = describe_traffic(replace(self.cluster, groups=groups), TrafficInput(messages=(first, second, third)))
        self.assertEqual(tuple((item.group_id, item.message_count, item.payload_bytes) for item in report.per_group),
                         (("g0", 1, D), ("g1", 1, D), (None, 1, D)))
        self.assertEqual(next(item.sent_payload_bytes for item in report.per_rank if item.participant_id == "r5"), 0)

    # Several ranks on one NIC aggregate logically; a local demand is described but never granted zero service.
    def test_shared_endpoint_and_local_description(self):
        placements = tuple(replace(item, node_id="n0", endpoint_id="e0") if item.rank_id == "r1" else item for item in self.cluster.placements)
        cluster = replace(self.cluster, placements=placements)
        message = self.study.traffic.messages[0]
        traffic = TrafficInput(messages=(message,))
        report = describe_traffic(cluster, traffic)
        self.assertEqual(report.local_payload_bytes, D)
        self.assertEqual(report.inter_node_payload_bytes, 0)
        row = next(item for item in report.per_endpoint if item.participant_id == "e0")
        self.assertEqual((row.sent_payload_bytes, row.received_payload_bytes), (D, D))
        with self.assertRaisesRegex(ValueError, "unsupported_local_path"):
            analyze_traffic(cluster, traffic)

    # Same-node multi-rail endpoints remain distinct physical ports with one shared injection resource.
    def test_multirail_shared_capacity(self):
        original = self.graph.endpoints
        shared = replace(original[1], node_id="n0", tx_constraint_ids=("n0.tx",), rx_constraint_ids=("n0.rx",))
        revised = replace(self.study, graph=replace(self.graph, endpoints=(original[0], shared) + original[2:],
                          constraints=tuple(item for item in self.graph.constraints if item.owner_id != "n1")))
        graph = build(revised, leaves={"l0": (original[0],) + original[2:4], "l1": (shared,) + original[4:]})
        placements = (RankPlacement(rank_id="a", node_id="n0", endpoint_id="e0"),
                      RankPlacement(rank_id="b", node_id="n0", endpoint_id="e1"),
                      RankPlacement(rank_id="c", node_id="n2", endpoint_id="e2"),
                      RankPlacement(rank_id="d", node_id="n4", endpoint_id="e4"))
        messages = (replace(self.study.traffic.messages[0], message_id="a-c", src_rank="a", dst_rank="c", group_id=None),
                    replace(self.study.traffic.messages[0], message_id="b-d", src_rank="b", dst_rank="d", group_id=None))
        cluster = ClusterSpec(cluster_id="rails", graph=graph, placements=placements)
        result = analyze_traffic(cluster, TrafficInput(messages=messages))
        self.assertEqual(next(item.service_bytes for item in result.resources if item.resource_id == "n0.tx"), 2097152)
        self.assertAlmostEqual(result.resource_time_lower_bound_s, 0.00008388608, delta=1e-18)
        queried = inspect_network(graph, source_endpoint_ids=("e0",)).reachability[0]
        self.assertEqual(queried.same_node_ids, ("e1",))
        self.assertNotIn("e1", queried.reachable_remote_ids)

    # Empty logical work has complete zero rows while unknown references remain errors before timing analysis.
    def test_empty_description_and_reference_errors(self):
        report = describe_traffic(self.cluster, TrafficInput(messages=()))
        self.assertEqual((report.message_count, report.logical_payload_bytes, report.node_matrix), (0, 0, ()))
        self.assertTrue(all(row.sent_payload_bytes == 0 for row in report.per_node))
        message = replace(self.study.traffic.messages[0], src_rank="missing")
        with self.assertRaisesRegex(ValueError, "unknown rank"):
            validate_traffic_references(self.cluster, TrafficInput(messages=(message,)))

    # The wider fixture has 6 local-leaf messages of 2 hops and 24 cross-leaf messages of 4 hops.
    def test_leaf_spine_byte_and_bound_reference(self):
        result = analyze_traffic(self.cluster, self.study.traffic)
        self.assertEqual(result.total_link_wire_bytes, 113246208)
        self.assertAlmostEqual(result.resource_time_lower_bound_s, 0.00067108864, delta=1e-18)
        self.assertEqual(next(item.service_bytes for item in result.resources if item.resource_id == "l0->s0"), 8388608)
        self.assertEqual(next(item.service_bytes for item in result.resources if item.resource_id == "l0->s1"), 0)
        self.assertEqual(next(item.service_bytes for item in result.resources if item.resource_id == "s0.internal"), 25165824)


if __name__ == "__main__":
    unittest.main()
