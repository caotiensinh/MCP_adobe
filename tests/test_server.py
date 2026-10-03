from __future__ import annotations

import asyncio
import unittest
from typing import Any, Mapping

from mcp import Client

from mcp_adobe.core import AdapterInfo, RiskClass
from mcp_adobe.server import build_server


class FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False
        self._info = AdapterInfo(
            application="photoshop",
            connected=True,
            version="test",
            common_capabilities=frozenset(
                {
                    "creative.document.info",
                    "creative.document.create",
                    "creative.document.export",
                }
            ),
            native_capabilities=frozenset({"photoshop.execute_script"}),
            capability_risks={
                "creative.document.info": RiskClass.READ,
                "creative.document.create": RiskClass.WRITE_REVERSIBLE,
                "creative.document.export": RiskClass.FILE_WRITE,
                "photoshop.execute_script": RiskClass.NATIVE_SCRIPT,
            },
            writes_enabled=True,
            undo_supported=True,
            transport="fake",
            upstream_repository="example/fake",
            upstream_snapshot="abc123",
        )

    def describe(self) -> tuple[AdapterInfo, ...]:
        return (self._info,)

    def read(self, application: str, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = {
            "application": application,
            "capability": capability,
            "arguments": dict(arguments),
        }
        self.calls.append(("read", payload))
        return {"mode": "read", **payload}

    def write(
        self,
        application: str,
        capability: str,
        arguments: Mapping[str, Any],
        *,
        allow_overwrite: bool = False,
    ) -> Mapping[str, Any]:
        payload = {
            "application": application,
            "capability": capability,
            "arguments": dict(arguments),
            "allow_overwrite": allow_overwrite,
        }
        self.calls.append(("write", payload))
        return {"mode": "write", **payload}

    def authorized_write(
        self,
        application: str,
        capability: str,
        arguments: Mapping[str, Any],
        *,
        allow_overwrite: bool = False,
        allow_destructive: bool = False,
        allow_native_script: bool = False,
        allow_external_ai: bool = False,
    ) -> Mapping[str, Any]:
        payload = {
            "application": application,
            "capability": capability,
            "arguments": dict(arguments),
            "allow_overwrite": allow_overwrite,
            "allow_destructive": allow_destructive,
            "allow_native_script": allow_native_script,
            "allow_external_ai": allow_external_ai,
        }
        self.calls.append(("authorized_write", payload))
        return {"mode": "authorized_write", **payload}

    def close(self) -> None:
        self.closed = True


class McpServerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = FakeRuntime()
        self.server = build_server(self.runtime)

    async def _with_client(self, action):
        async with Client(self.server) as client:
            return await action(client)

    def test_tools_are_exposed_with_conservative_annotations(self) -> None:
        async def scenario(client):
            return await client.list_tools()

        listed = asyncio.run(self._with_client(scenario))
        tools = {tool.name: tool for tool in listed.tools}
        self.assertEqual(
            set(tools),
            {
                "creative_discover",
                "creative_read",
                "creative_write",
                "creative_authorized_write",
            },
        )
        self.assertTrue(tools["creative_discover"].annotations.read_only_hint)
        self.assertTrue(tools["creative_read"].annotations.read_only_hint)
        self.assertFalse(tools["creative_write"].annotations.read_only_hint)
        self.assertFalse(tools["creative_write"].annotations.destructive_hint)
        self.assertTrue(tools["creative_authorized_write"].annotations.destructive_hint)

    def test_discover_returns_structured_capability_metadata(self) -> None:
        async def scenario(client):
            return await client.call_tool("creative_discover", {})

        result = asyncio.run(self._with_client(scenario))
        payload = result.structured_content
        self.assertIsNotNone(payload)
        self.assertEqual(payload["applications"][0]["application"], "photoshop")
        self.assertEqual(
            payload["applications"][0]["capability_risks"]["creative.document.info"],
            "read",
        )
        self.assertEqual(payload["transports"], ["stdio", "streamable-http"])

    def test_read_write_and_authorized_write_route_to_distinct_runtime_paths(self) -> None:
        async def scenario(client):
            read = await client.call_tool(
                "creative_read",
                {
                    "application": "photoshop",
                    "capability": "creative.document.info",
                    "arguments": {"detail": True},
                },
            )
            write = await client.call_tool(
                "creative_write",
                {
                    "application": "photoshop",
                    "capability": "creative.document.export",
                    "arguments": {"path": "out.png"},
                    "allow_overwrite": True,
                },
            )
            high_risk = await client.call_tool(
                "creative_authorized_write",
                {
                    "application": "photoshop",
                    "capability": "photoshop.execute_script",
                    "arguments": {"script": "noop"},
                    "allow_native_script": True,
                },
            )
            return read, write, high_risk

        read, write, high_risk = asyncio.run(self._with_client(scenario))
        self.assertEqual(read.structured_content["mode"], "read")
        self.assertEqual(write.structured_content["mode"], "write")
        self.assertTrue(write.structured_content["allow_overwrite"])
        self.assertEqual(high_risk.structured_content["mode"], "authorized_write")
        self.assertTrue(high_risk.structured_content["allow_native_script"])
        self.assertEqual([name for name, _ in self.runtime.calls], ["read", "write", "authorized_write"])


if __name__ == "__main__":
    unittest.main()
