"""Link arithmetic against hand counts and exact rational references."""

from dataclasses import replace
from fractions import Fraction
import unittest

from clustermodel.fabric.links.model import LinkParams, estimate_link


# Explicit ideal framing keeps the 200 Gbit/s -> 25 GB/s dimensional reference easy to inspect.
def raw_link(**changes) -> LinkParams:
    values = dict(link_id="ab", src_port_id="a", dst_port_id="b", rate_basis="raw_line",
                  startup_s=1e-6, propagation_s=1e-6, capacity_kind="declared_ceiling",
                  source_ref="manual:test/v1", coverage=("isolated ideal link",),
                  line_rate_bps=200_000_000_000, coding_efficiency=1,
                  max_payload_bytes=4096, header_bytes=0, trailer_bytes=0, alignment_bytes=1)
    return LinkParams(**{**values, **changes})


# Effective payload service includes its protocol adjustment; framing intentionally remains unspecified.
def effective_link(**changes) -> LinkParams:
    values = dict(link_id="ab", src_port_id="a", dst_port_id="b", rate_basis="effective_payload",
                  startup_s=0, propagation_s=0, capacity_kind="effective_service",
                  source_ref="manual:test-payload/v1", coverage=("effective service for declared size range",),
                  payload_bandwidth_Bps=1_000_000_000)
    return LinkParams(**{**values, **changes})


# Boundary cases test rate basis, frame rounding, unknowns and numerical representability.
class LinkTests(unittest.TestCase):
    # One decimal MB needs exactly 40 us serialization at 200 Gbit/s, plus 2 us declared latency.
    def test_dimensional_reference(self):
        params = raw_link()
        result = estimate_link(params, 1_000_000)
        self.assertEqual(params.service_capacity_Bps, 25_000_000_000)
        self.assertEqual((result.packet_count, result.wire_bytes, result.service_bytes), (245, 1_000_000, 1_000_000))
        self.assertAlmostEqual(result.serialization_s, float(Fraction(40, 1_000_000)), delta=1e-18)
        self.assertAlmostEqual(result.isolated_time_s, float(Fraction(42, 1_000_000)), delta=1e-18)

    # A 1024-byte full payload frame is 1088 B; a one-byte tail frame is 64 B, for 1152 B total.
    def test_tail_packet_and_alignment(self):
        params = raw_link(max_payload_bytes=1024, header_bytes=24, trailer_bytes=8, alignment_bytes=64)
        result = estimate_link(params, 1025)
        self.assertEqual((result.packet_count, result.wire_bytes), (2, 1152))
        self.assertEqual(estimate_link(params, 1024).wire_bytes, 1088)
        self.assertEqual(estimate_link(params, 2048).wire_bytes, 2176)

    # Coding scales frame service capacity once; packet overhead already belongs to the numerator.
    def test_coding_is_applied_once(self):
        params = raw_link(line_rate_bps=8000, coding_efficiency=0.8, max_payload_bytes=100,
                          header_bytes=10, startup_s=0, propagation_s=0)
        result = estimate_link(params, 100)
        self.assertEqual(result.wire_bytes, 110)
        self.assertEqual(params.service_capacity_Bps, 800)
        self.assertEqual(result.serialization_s, float(Fraction(11, 80)))

    # Nonempty effective-service profiles cannot claim packet/wire counters they do not define.
    def test_effective_profile_unknown_wire(self):
        result = estimate_link(effective_link(), 1000)
        self.assertEqual(result.service_bytes, 1000)
        self.assertEqual(result.service_byte_basis, "payload")
        self.assertIsNone(result.packet_count)
        self.assertIsNone(result.wire_bytes)
        self.assertIn("does not specify", result.wire_unknown_reason)
        self.assertEqual(result.isolated_time_s, 1e-6)

    # Zero is no work under either representation, even if the nonempty profile has a minimum size.
    def test_empty_query(self):
        for params in (raw_link(profile_min_payload_bytes=64), effective_link(startup_s=3)):
            with self.subTest(params=params.rate_basis):
                result = estimate_link(params, 0)
                self.assertTrue(result.empty)
                self.assertEqual((result.packet_count, result.wire_bytes, result.service_bytes), (0, 0, 0))
                self.assertEqual(result.isolated_time_s, 0)
                self.assertIsNone(result.wire_unknown_reason)

    # Profile limits concern whole message size, independently of per-packet MTU.
    def test_profile_domain(self):
        params = raw_link(profile_min_payload_bytes=64, profile_max_payload_bytes=1024)
        for size in (63, 1025):
            with self.assertRaisesRegex(ValueError, "out_of_domain"):
                estimate_link(params, size)
        self.assertEqual(estimate_link(params, 64).payload_bytes, 64)
        self.assertEqual(estimate_link(params, 1024).payload_bytes, 1024)

    # Payload and raw profiles must never be blended into a second protocol-efficiency discount.
    def test_reject_mixed_or_missing_rate_fields(self):
        for changes in ({"payload_bandwidth_Bps": 100}, {"header_bytes": None}, {"line_rate_bps": None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                raw_link(**changes)
        for changes in ({"header_bytes": 0}, {"line_rate_bps": 100}, {"coding_efficiency": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                effective_link(**changes)

    # Integer counts reject bool/fractional values, and finite rate/latency rules cover numerical extremes.
    def test_invalid_parameters(self):
        cases = ({"line_rate_bps": 0}, {"line_rate_bps": True}, {"line_rate_bps": float("inf")},
                 {"coding_efficiency": 0}, {"coding_efficiency": 1.01}, {"coding_efficiency": float("nan")},
                 {"max_payload_bytes": 0}, {"max_payload_bytes": 1.5}, {"alignment_bytes": True},
                 {"header_bytes": -1}, {"startup_s": -1}, {"propagation_s": float("inf")},
                 {"dst_port_id": "a"}, {"rate_basis": "wire"}, {"capacity_kind": "unknown"},
                 {"profile_min_payload_bytes": 0}, {"profile_max_payload_bytes": 0},
                 {"schema_version": "network-link/v2"}, {"source_ref": ""})
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                raw_link(**changes)

    # Derived underflow/overflow is rejected instead of producing zero-capacity or infinite time metrics.
    def test_nonfinite_derived_values(self):
        for changes in ({"line_rate_bps": 5e-324}, {"startup_s": 1e308, "propagation_s": 1e308}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                raw_link(**changes)
        with self.assertRaises(ValueError):
            estimate_link(effective_link(payload_bandwidth_Bps=5e-324), 1)
        with self.assertRaises(ValueError):
            estimate_link(raw_link(), 10**400)

    # Workload counts stay exact; booleans and floating byte counts are not accepted as messages.
    def test_invalid_message_counts(self):
        for size in (-1, True, 1.0, "10", None):
            with self.subTest(size=size), self.assertRaises((TypeError, ValueError)):
                estimate_link(raw_link(), size)

    # Framing identity is stable under rate changes but changes with packetization semantics.
    def test_frame_identity(self):
        params = raw_link()
        self.assertEqual(params.frame_format_id, replace(params, line_rate_bps=100e9).frame_format_id)
        self.assertNotEqual(params.frame_format_id, replace(params, header_bytes=1).frame_format_id)
        self.assertIsNone(effective_link().frame_format_id)

    # Very large messages remain an arithmetic query rather than allocating one object per packet.
    def test_large_message_exact_counter(self):
        result = estimate_link(raw_link(max_payload_bytes=1), 10**18 + 1)
        self.assertEqual(result.packet_count, 10**18 + 1)
        self.assertEqual(result.wire_bytes, 10**18 + 1)

    # Queries leave parameters unchanged; independent rate/latency changes affect only their own terms.
    def test_independence_and_sensitivity(self):
        params = raw_link()
        original = estimate_link(params, 1000)
        fast = estimate_link(replace(params, line_rate_bps=400e9), 1000)
        delayed = estimate_link(replace(params, propagation_s=3e-6), 1000)
        self.assertEqual(estimate_link(params, 1000), original)
        self.assertEqual(fast.serialization_s, original.serialization_s / 2)
        self.assertAlmostEqual(delayed.isolated_time_s - original.isolated_time_s, 2e-6)


if __name__ == "__main__":
    unittest.main()
