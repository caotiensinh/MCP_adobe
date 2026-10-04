from __future__ import annotations

import asyncio
import unittest

from mcp import Client

from mcp_adobe.core import AdapterInfo, RiskClass
from mcp_adobe.server import build_server


class DiscoveryOnlyRuntime:
    def describe(self) -> tuple[AdapterInfo, ...]:
        return (
            AdapterInfo(
                application="photoshop",
                connected=True,
                version="test",
                common_capabilities=frozenset({"creative.document.info"}),
                capability_risks={"creative.document.info": RiskClass.READ},
                writes_enabled=True,
                transport="mcp",
                upstream_repository="example/photoshop",
                upstream_snapshot="abc123",
                readiness_probe="photoshop_ping",
            ),
        )


class DiscoveryReadinessMetadataTests(unittest.TestCase):
    def test_discovery_distinguishes_transport_from_application_readiness(self) -> None:
        server = build_server(DiscoveryOnlyRuntime())

        async def scenario():
            async with Client(server) as client:
                return await client.call_tool("creative_discover", {})

        result = asyncio.run(scenario())
        payload = result.structured_content
        self.assertIsNotNone(payload)

        app = payload["applications"][0]
        self.assertTrue(app["connected"])
        self.assertTrue(app["transport_connected"])
        self.assertEqual(app["connection_semantics"], "transport_only")
        self.assertEqual(app["readiness_probe"], "photoshop_ping")
        self.assertEqual(app["readiness_status"], "not_probed")

        contract = payload["connection_contract"]
        self.assertEqual(contract["connected_means"], "transport_connected")
        self.assertEqual(contract["application_ready_requires"], "declared_readiness_probe")
        self.assertFalse(contract["discovery_probes_application"])

    def test_adapter_without_probe_is_explicitly_not_declared(self) -> None:
        class NoProbeRuntime:
            def describe(self) -> tuple[AdapterInfo, ...]:
                return (
                    AdapterInfo(
                        application="custom",
                        connected=False,
                        common_capabilities=frozenset({"creative.health"}),
                        capability_risks={"creative.health": RiskClass.READ},
                    ),
                )

        server = build_server(NoProbeRuntime())

        async def scenario():
            async with Client(server) as client:
                return await client.call_tool("creative_discover", {})

        result = asyncio.run(scenario())
        app = result.structured_content["applications"][0]
        self.assertFalse(app["transport_connected"])
        self.assertIsNone(app["readiness_probe"])
        self.assertEqual(app["readiness_status"], "not_declared")


if __name__ == "__main__":
    unittest.main()
