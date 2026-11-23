"""Direct topology invariants, physical attachment and cut accounting."""

from dataclasses import replace
import unittest

from clustermodel.fabric.links.model import LinkParams
from clustermodel.topology.graph import NetworkGraph, cut_capacity, get_link, reachable_endpoints
from contracts.hardware.network import BandwidthConstraint, NetworkEndpointSpec
from contracts.versions.json_codec import content_hash


# Several ports of a node intentionally reference the same NIC injection/receive resources.
def endpoint(node: str, port: str = "0") -> NetworkEndpointSpec:
    return NetworkEndpointSpec(endpoint_id=f"{node}.ep{port}", node_id=node, port_id=f"{node}.p{port}",
                               tx_constraint_ids=(f"{node}.tx",), rx_constraint_ids=(f"{node}.rx",),
                               source_ref="manual:test/v1", coverage=("external NIC boundary",))


# Small integer capacities make independent cut sums visible; no measured throughput is implied.
def resources(*nodes: str) -> tuple[BandwidthConstraint, ...]:
    return tuple(BandwidthConstraint(resource_id=f"{node}.{direction}", owner_id=node, capacity_Bps=25,
                                    byte_basis="payload", capacity_kind="declared_ceiling",
                                    source_ref="manual:test/v1", coverage=("shared NIC capacity",))
                 for node in nodes for direction in ("tx", "rx"))


# Effective-payload channels need no assumed packet format; all capacities are in B/s.
def link(name: str, src: str, dst: str, **changes) -> LinkParams:
    values = dict(link_id=name, src_port_id=src, dst_port_id=dst, rate_basis="effective_payload",
                  startup_s=0, propagation_s=0, capacity_kind="declared_ceiling", source_ref="manual:test/v1",
                  coverage=("isolated service",), payload_bandwidth_Bps=100)
    return LinkParams(**{**values, **changes})


# Two explicit directions have independently declared rates, demonstrating asymmetric full duplex.
def graph() -> NetworkGraph:
    return NetworkGraph(graph_id="fabric", endpoints=(endpoint("a"), endpoint("b")),
                        links=(link("ab", "a.p0", "b.p0"),
                               link("ba", "b.p0", "a.p0", payload_bandwidth_Bps=50)),
                        constraints=resources("a", "b"))


# C1 validates topology facts without implying switch forwarding, routing or contention execution.
class TopologyTests(unittest.TestCase):
    # Directed cuts must not sum the reverse direction or replace a capacity with NIC throughput.
    def test_directed_cut_and_reachability(self):
        value = graph()
        self.assertEqual(reachable_endpoints(value, "a.ep0"), ("b.ep0",))
        self.assertEqual(reachable_endpoints(value, "b.ep0"), ("a.ep0",))
        self.assertEqual(cut_capacity(value, ("a",)).capacity_Bps, 100)
        self.assertEqual(cut_capacity(value, ("b",)).capacity_Bps, 50)
        self.assertEqual(cut_capacity(value, ("a",)).byte_basis, "payload")
        self.assertEqual(get_link(value, "ab").src_port_id, "a.p0")

    # Empty/no-outgoing cuts are explicit zero link capacity, never an invented unreachable infinity.
    def test_empty_and_disconnected_graph(self):
        value = NetworkGraph(graph_id="fabric", endpoints=(endpoint("a"),), links=(), constraints=resources("a"))
        self.assertEqual(value.node_ids, ("a",))
        self.assertEqual(reachable_endpoints(value, "a.ep0"), ())
        for selected in ((), ("a",)):
            cut = cut_capacity(value, selected)
            self.assertTrue(cut.empty)
            self.assertEqual(cut.capacity_Bps, 0)
            self.assertIsNone(cut.byte_basis)
            self.assertIsNone(cut.capacity_kind)

    # Unordered input containers are owned/canonicalized, preserving identity across equivalent graphs.
    def test_canonical_order_and_isolation(self):
        original = graph()
        copied = list(reversed(original.endpoints))
        equivalent = replace(original, endpoints=copied, links=list(reversed(original.links)),
                             constraints=list(reversed(original.constraints)))
        copied.clear()
        self.assertEqual(content_hash(equivalent), content_hash(original))
        self.assertEqual(len(equivalent.endpoints), 2)

    # Duplicate definitions cannot be resolved by last-write-wins dictionaries.
    def test_duplicate_definitions_and_ports(self):
        value = graph()
        for name in ("endpoints", "links", "constraints"):
            items = getattr(value, name)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "duplicate"):
                replace(value, **{name: items + (items[0],)})
        with self.assertRaisesRegex(ValueError, "duplicate physical port_id"):
            replace(value, endpoints=(value.endpoints[0], replace(value.endpoints[1], port_id="a.p0")))

    # References are checked against actual resource owners, not merely matching string names.
    def test_dangling_and_wrong_owner_constraints(self):
        value = graph()
        with self.assertRaisesRegex(ValueError, "missing bandwidth"):
            replace(value, constraints=value.constraints[1:])
        wrong = replace(value.constraints[0], owner_id="b")
        with self.assertRaisesRegex(ValueError, "different owner"):
            replace(value, constraints=(wrong,) + value.constraints[1:])
        with self.assertRaisesRegex(ValueError, "unknown owner"):
            replace(value, constraints=(replace(wrong, owner_id="ghost"),) + value.constraints[1:])
        with self.assertRaisesRegex(ValueError, "graph_id"):
            replace(value, graph_id="a")

    # The direct graph does not grant local bridges or silently create ports.
    def test_missing_and_local_ports(self):
        value = graph()
        with self.assertRaisesRegex(ValueError, "missing endpoint port"):
            replace(value, links=(replace(value.links[0], src_port_id="absent"),))
        with self.assertRaisesRegex(ValueError, "unsupported_local_path"):
            NetworkGraph(graph_id="fabric", endpoints=(endpoint("a"), endpoint("a", "1")),
                         links=(link("local", "a.p0", "a.p1"),), constraints=resources("a"))

    # One port can have a full-duplex peer but cannot connect its directions to unrelated peers.
    def test_port_fanout_and_peer_conflict(self):
        eps, limits = (endpoint("a"), endpoint("b"), endpoint("c")), resources("a", "b", "c")
        ab = link("ab", "a.p0", "b.p0")
        for extra in (link("ac", "a.p0", "c.p0"), link("ca", "c.p0", "a.p0")):
            with self.subTest(extra=extra.link_id), self.assertRaises(ValueError):
                NetworkGraph(graph_id="fabric", endpoints=eps, links=(ab, extra), constraints=limits)

    # Two node ports share one NIC definition; a cut sum can exceed that independent NIC limit.
    def test_shared_nic_reference_is_not_duplicated(self):
        value = NetworkGraph(graph_id="fabric", endpoints=(endpoint("a"), endpoint("a", "1"), endpoint("b"), endpoint("c")),
                             links=(link("ab", "a.p0", "b.p0"), link("ac", "a.p1", "c.p0")),
                             constraints=resources("a", "b", "c"))
        self.assertEqual(len(value.constraints), 6)
        self.assertEqual(value.endpoints[0].tx_constraint_ids, value.endpoints[1].tx_constraint_ids)
        self.assertEqual(cut_capacity(value, ("a",)).capacity_Bps, 200)
        self.assertEqual(next(r.capacity_Bps for r in value.constraints if r.resource_id == "a.tx"), 25)

    # Shared half-duplex capacity is retained as an explicit additional resource, not doubled by directions.
    def test_shared_duplex_constraint(self):
        value = graph()
        shared = BandwidthConstraint(resource_id="medium", owner_id="fabric", capacity_Bps=50,
                                     byte_basis="payload", capacity_kind="declared_ceiling",
                                     source_ref="manual:test/v1", coverage=("half duplex combined service",))
        value = replace(value, links=tuple(replace(item, shared_constraint_ids=("medium",)) for item in value.links),
                        constraints=value.constraints + (shared,))
        self.assertEqual(cut_capacity(value, ("a",)).shared_constraint_ids, ("medium",))
        self.assertEqual(cut_capacity(value, ("b",)).shared_constraint_ids, ("medium",))
        self.assertEqual(sum(r.resource_id == "medium" for r in value.constraints), 1)

    # Frame constraints require a matching representation rather than treating effective payload as wire.
    def test_incompatible_frame_constraint(self):
        value = graph()
        changed = tuple(replace(r, byte_basis="frame", frame_format_id="wrong") if r.resource_id == "a.tx" else r
                        for r in value.constraints)
        with self.assertRaisesRegex(ValueError, "incompatible frame basis"):
            replace(value, constraints=changed)

    # A multi-link cut cannot silently add unlike service byte representations.
    def test_mixed_cut_basis_rejected(self):
        raw = link("ab", "a.p0", "b.p0", rate_basis="raw_line", payload_bandwidth_Bps=None,
                   line_rate_bps=800, coding_efficiency=1, max_payload_bytes=64,
                   header_bytes=0, trailer_bytes=0, alignment_bytes=1)
        value = NetworkGraph(graph_id="fabric", endpoints=(endpoint("a"), endpoint("a", "1"), endpoint("b"), endpoint("c")),
                             links=(raw, link("ac", "a.p1", "c.p0")), constraints=resources("a", "b", "c"))
        with self.assertRaisesRegex(ValueError, "incompatible_byte_basis"):
            cut_capacity(value, ("a",))

    # Wiring cycles across multiple ports are legal, but reaching a peer never forwards through its other NIC.
    def test_no_implicit_transit_on_a_wiring_cycle(self):
        eps = tuple(endpoint(node, port) for node in ("a", "b", "c") for port in ("0", "1"))
        value = NetworkGraph(graph_id="fabric", endpoints=eps, constraints=resources("a", "b", "c"),
                             links=(link("ab", "a.p0", "b.p0"), link("bc", "b.p1", "c.p0"),
                                    link("ca", "c.p1", "a.p1")))
        self.assertEqual(reachable_endpoints(value, "a.ep0"), ("b.ep0",))
        self.assertNotIn("c.ep0", reachable_endpoints(value, "a.ep0"))

    # Query identities, unsupported graph versions and malformed cut inputs are diagnosed explicitly.
    def test_query_and_version_errors(self):
        value = graph()
        for selected in (("missing",), ("a", "a"), "a"):
            with self.subTest(selected=selected), self.assertRaises((ValueError, TypeError)):
                cut_capacity(value, selected)
        with self.assertRaisesRegex(ValueError, "unknown endpoint"):
            reachable_endpoints(value, "missing")
        with self.assertRaisesRegex(ValueError, "unknown link"):
            get_link(value, "missing")
        with self.assertRaisesRegex(ValueError, "schema_version"):
            replace(value, schema_version="direct-network-graph/v2")


if __name__ == "__main__":
    unittest.main()
