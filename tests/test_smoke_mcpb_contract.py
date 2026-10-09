from __future__ import annotations

import unittest

from scripts.smoke_mcpb import EXPECTED_APPLICATIONS, EXPECTED_TOOLS, _validate_discovery_contract


def _valid_payload() -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    by_name = {
        application: {
            "application": application,
            "connected": application != "xd",
            "transport_connected": application != "xd",
            "connection_semantics": "transport_only",
            "readiness_probe": "creative.health",
            "readiness_status": "not_probed",
        }
        for application in EXPECTED_APPLICATIONS
    }
    payload: dict[str, object] = {
        "applications": list(by_name.values()),
        "connection_contract": {
            "connected_means": "transport_connected",
            "application_ready_requires": "declared_readiness_probe",
            "discovery_probes_application": False,
        },
    }
    return payload, by_name


class PackagedDiscoveryContractTests(unittest.TestCase):
    def test_packaged_surface_requires_visual_live_build(self) -> None:
        self.assertEqual(
            EXPECTED_TOOLS,
            {
                "creative_discover",
                "creative_read",
                "creative_write",
                "creative_live_build",
                "creative_authorized_write",
            },
        )

    def test_valid_contract_reports_transport_and_readiness_separately(self) -> None:
        payload, by_name = _valid_payload()

        readiness = _validate_discovery_contract(payload, by_name)

        self.assertEqual(set(readiness), EXPECTED_APPLICATIONS)
        self.assertTrue(readiness["photoshop"]["transport_connected"])
        self.assertFalse(readiness["xd"]["transport_connected"])
        self.assertEqual(readiness["illustrator"]["readiness_probe"], "creative.health")
        self.assertEqual(readiness["illustrator"]["readiness_status"], "not_probed")

    def test_missing_top_level_connection_contract_fails(self) -> None:
        payload, by_name = _valid_payload()
        payload.pop("connection_contract")

        with self.assertRaisesRegex(AssertionError, "connection contract drifted"):
            _validate_discovery_contract(payload, by_name)

    def test_transport_connected_must_match_legacy_connected(self) -> None:
        payload, by_name = _valid_payload()
        by_name["photoshop"]["transport_connected"] = False

        with self.assertRaisesRegex(AssertionError, "transport_connected must mirror"):
            _validate_discovery_contract(payload, by_name)

    def test_discovery_must_not_claim_application_was_probed(self) -> None:
        payload, by_name = _valid_payload()
        by_name["xd"]["readiness_status"] = "ready"

        with self.assertRaisesRegex(AssertionError, "discovery must remain non-probing"):
            _validate_discovery_contract(payload, by_name)

    def test_all_builtin_adapters_must_keep_declared_health_capability(self) -> None:
        payload, by_name = _valid_payload()
        by_name["illustrator"]["readiness_probe"] = None

        with self.assertRaisesRegex(AssertionError, "readiness_probe drifted"):
            _validate_discovery_contract(payload, by_name)


if __name__ == "__main__":
    unittest.main()
