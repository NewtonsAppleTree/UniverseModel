"""Independent validation of the network boundary without importing hardware models."""

from dataclasses import FrozenInstanceError, replace
import unittest

from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.hardware.network import BandwidthConstraint, NetworkEndpointSpec
from contracts.versions.json_codec import canonical_json, parse_json


# A payload constraint uses an explicit assumed service ceiling, not a measured device specification.
def resource(**changes) -> BandwidthConstraint:
    values = dict(resource_id="nic.tx", owner_id="node", capacity_Bps=25_000_000_000,
                  byte_basis="payload", capacity_kind="declared_ceiling", source_ref="manual:test/v1",
                  coverage=("NIC injection only",))
    return BandwidthConstraint(**{**values, **changes})


# Network contracts reject ambiguity before hardware models can consume the values.
class NetworkContractTests(unittest.TestCase):
    # Frozen values must own the reference sequences, not retain a caller's mutable list.
    def test_freeze_and_reference_identity(self):
        tx, coverage = ["nic.tx"], ["NIC boundary"]
        endpoint = NetworkEndpointSpec(endpoint_id="ep", node_id="node", port_id="port",
                                       tx_constraint_ids=tx, rx_constraint_ids=["nic.rx"],
                                       source_ref="manual:test/v1", coverage=coverage)
        tx.append("new")
        coverage[0] = "changed"
        self.assertEqual(endpoint.tx_constraint_ids, ("nic.tx",))
        self.assertEqual(endpoint.coverage, ("NIC boundary",))
        with self.assertRaises(FrozenInstanceError):
            endpoint.node_id = "another"

    # Units require a strictly positive finite numeric rate, with no bool/string conversion.
    def test_invalid_capacities(self):
        for value in (True, "25", None, 0, -1, float("nan"), float("inf"), 10**400):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                resource(capacity_Bps=value)
        self.assertEqual(resource(capacity_Bps=1).capacity_Bps, 1.0)

    # A frame representation requires its identity; payload must not also declare a frame format.
    def test_byte_basis_and_capacity_kind(self):
        for changes in ({"byte_basis": "bit"}, {"byte_basis": "frame"},
                        {"frame_format_id": "format"}, {"capacity_kind": "measured_peak"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                resource(**changes)
        frame = resource(byte_basis="frame", frame_format_id="format/v1", capacity_kind="effective_service")
        self.assertEqual(frame.frame_format_id, "format/v1")

    # Empty provenance, malformed identities and unknown schemas cannot silently acquire defaults.
    def test_source_identity_and_version(self):
        for changes in ({"source_ref": ""}, {"owner_id": " node"}, {"coverage": ()},
                        {"coverage": "not a list"}, {"coverage": [""]},
                        {"schema_version": "network-bandwidth/v2"}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                resource(**changes)

    # Duplicate references and missing injection/receive constraints cannot imply more/free capacity.
    def test_endpoint_reference_and_schema_errors(self):
        endpoint = NetworkEndpointSpec(endpoint_id="ep", node_id="node", port_id="port",
                                       tx_constraint_ids=("nic.tx",), rx_constraint_ids=("nic.rx",),
                                       source_ref="manual:test/v1", coverage=("NIC boundary",))
        for changes in ({"tx_constraint_ids": ()}, {"rx_constraint_ids": ("same", "same")},
                        {"tx_constraint_ids": "nic.tx"}, {"rx_constraint_ids": (True,)},
                        {"schema_version": "network-endpoint/v2"}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                replace(endpoint, **changes)

    # Strict configuration and serialization preserve the contract while rejecting undeclared fields.
    def test_configuration_roundtrip(self):
        expected = resource()
        values = parse_json(canonical_json(expected))
        self.assertEqual(resolve_dataclass(BandwidthConstraint, values), expected)
        with self.assertRaisesRegex(ValueError, "unknown or derived"):
            resolve_dataclass(BandwidthConstraint, {**values, "unlimited": True})


if __name__ == "__main__":
    unittest.main()
