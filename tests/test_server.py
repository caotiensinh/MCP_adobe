from __future__ import annotations

import asyncio
import unittest
from typing import Any, Mapping

from mcp import Client
from mcp.server.auth.provider import AccessToken, TokenVerifier

from mcp_adobe.auth import HIGH_RISK_SCOPE, WRITE_SCOPE, OAuthResourceConfig
from mcp_adobe.core import AdapterInfo, RiskClass
from mcp_adobe.server import GatewayRuntime, build_server


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


class _NeverVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        return None


def _oauth_config(scopes: tuple[str, ...]) -> OAuthResourceConfig:
    return OAuthResourceConfig(
        issuer_url="http://127.0.0.1:9000",
        resource_url="http://127.0.0.1:9001/mcp",
        introspection_endpoint="http://127.0.0.1:9000/introspect",
        required_scopes=scopes,
    )


class McpServerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = FakeRuntime()
        self.server = build_server(self.runtime)

    async def _with_client(self, action, server=None):
        async with Client(server or self.server) as client:
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
                "creative_live_build",
                "creative_authorized_write",
            },
        )
        self.assertTrue(tools["creative_discover"].annotations.read_only_hint)
        self.assertTrue(tools["creative_read"].annotations.read_only_hint)
        self.assertFalse(tools["creative_write"].annotations.read_only_hint)
        self.assertFalse(tools["creative_write"].annotations.destructive_hint)
        self.assertFalse(tools["creative_live_build"].annotations.read_only_hint)
        self.assertFalse(tools["creative_live_build"].annotations.destructive_hint)
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
        self.assertIsNone(payload["oauth_policy"])

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

    def test_live_build_routes_reversible_steps_in_order(self) -> None:
        async def scenario(client):
            return await client.call_tool(
                "creative_live_build",
                {
                    "application": "photoshop",
                    "step_delay_ms": 0,
                    "steps": [
                        {
                            "label": "base",
                            "capability": "creative.document.create",
                            "arguments": {"width": 800, "height": 600},
                        },
                        {
                            "label": "second",
                            "capability": "creative.document.create",
                            "arguments": {"width": 640, "height": 480},
                        },
                    ],
                },
            )

        result = asyncio.run(self._with_client(scenario))
        self.assertFalse(result.is_error)
        payload = result.structured_content
        self.assertEqual(payload["mode"], "visual_live_build")
        self.assertEqual(payload["steps_total"], 2)
        self.assertEqual(payload["steps_completed"], 2)
        self.assertEqual([step["label"] for step in payload["steps"]], ["base", "second"])
        self.assertEqual([name for name, _ in self.runtime.calls], ["write", "write"])

    def test_live_build_logs_root_cause_with_operation_context(self) -> None:
        def fail_write(*args, **kwargs):
            raise RuntimeError("backend exploded")

        self.runtime.write = fail_write  # type: ignore[method-assign]

        async def scenario(client):
            return await client.call_tool(
                "creative_live_build",
                {
                    "application": "photoshop",
                    "step_delay_ms": 0,
                    "steps": [
                        {
                            "label": "first",
                            "capability": "creative.document.create",
                            "arguments": {"width": 800, "height": 600},
                        }
                    ],
                },
            )

        with self.assertLogs("mcp_adobe.server", level="ERROR") as captured:
            result = asyncio.run(self._with_client(scenario))

        self.assertTrue(result.is_error)
        joined = "\n".join(captured.output)
        self.assertNotIn("backend exploded", joined)
        self.assertIn("creative.document.create", joined)
        self.assertIn("operation_id=", joined)
        self.assertIn("cause_type=RuntimeError", joined)

    def test_live_build_rejects_file_writes_before_runtime(self) -> None:
        async def scenario(client):
            return await client.call_tool(
                "creative_live_build",
                {
                    "application": "photoshop",
                    "step_delay_ms": 0,
                    "steps": [
                        {
                            "label": "export",
                            "capability": "creative.document.export",
                            "arguments": {"path": "out.png"},
                        }
                    ],
                },
            )

        result = asyncio.run(self._with_client(scenario))
        self.assertTrue(result.is_error)
        self.assertEqual(self.runtime.calls, [])

    def test_oauth_access_only_profile_blocks_all_writes_before_runtime(self) -> None:
        server = build_server(
            self.runtime,
            oauth_config=_oauth_config(("creative:access",)),
            token_verifier=_NeverVerifier(),
        )

        async def scenario(client):
            normal = await client.call_tool(
                "creative_write",
                {
                    "application": "photoshop",
                    "capability": "creative.document.create",
                    "arguments": {},
                },
            )
            high = await client.call_tool(
                "creative_authorized_write",
                {
                    "application": "photoshop",
                    "capability": "photoshop.execute_script",
                    "arguments": {"script": "noop"},
                    "allow_native_script": True,
                },
            )
            return normal, high

        normal, high = asyncio.run(self._with_client(scenario, server))
        self.assertTrue(normal.is_error)
        self.assertTrue(high.is_error)
        self.assertEqual(self.runtime.calls, [])

    def test_oauth_write_profile_allows_normal_write_but_blocks_high_risk(self) -> None:
        server = build_server(
            self.runtime,
            oauth_config=_oauth_config(("creative:access", WRITE_SCOPE)),
            token_verifier=_NeverVerifier(),
        )

        async def scenario(client):
            normal = await client.call_tool(
                "creative_write",
                {
                    "application": "photoshop",
                    "capability": "creative.document.create",
                    "arguments": {},
                },
            )
            high = await client.call_tool(
                "creative_authorized_write",
                {
                    "application": "photoshop",
                    "capability": "photoshop.execute_script",
                    "arguments": {"script": "noop"},
                    "allow_native_script": True,
                },
            )
            return normal, high

        normal, high = asyncio.run(self._with_client(scenario, server))
        self.assertFalse(normal.is_error)
        self.assertEqual(normal.structured_content["mode"], "write")
        self.assertTrue(high.is_error)
        self.assertEqual([name for name, _ in self.runtime.calls], ["write"])

    def test_oauth_full_profile_allows_high_risk_and_reports_policy(self) -> None:
        scopes = ("creative:access", WRITE_SCOPE, HIGH_RISK_SCOPE)
        server = build_server(
            self.runtime,
            oauth_config=_oauth_config(scopes),
            token_verifier=_NeverVerifier(),
        )

        async def scenario(client):
            discovered = await client.call_tool("creative_discover", {})
            high = await client.call_tool(
                "creative_authorized_write",
                {
                    "application": "photoshop",
                    "capability": "photoshop.execute_script",
                    "arguments": {"script": "noop"},
                    "allow_native_script": True,
                },
            )
            return discovered, high

        discovered, high = asyncio.run(self._with_client(scenario, server))
        policy = discovered.structured_content["oauth_policy"]
        self.assertEqual(policy["required_scopes"], list(scopes))
        self.assertTrue(policy["normal_write_enabled"])
        self.assertTrue(policy["high_risk_write_enabled"])
        self.assertFalse(high.is_error)
        self.assertEqual(high.structured_content["mode"], "authorized_write")
        self.assertEqual([name for name, _ in self.runtime.calls], ["authorized_write"])


class _StartableBridge:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.starts = 0
        self.error = error

    def start(self) -> None:
        self.starts += 1
        if self.error is not None:
            raise self.error


class GatewayRuntimePrewarmTests(unittest.TestCase):
    def _runtime(self):
        runtime = object.__new__(GatewayRuntime)
        runtime._photoshop_client = _StartableBridge()
        runtime._illustrator_client = _StartableBridge()
        runtime._xd_client = _StartableBridge()
        return runtime

    def test_prewarm_deduplicates_and_starts_requested_bridges(self) -> None:
        runtime = self._runtime()
        result = runtime.prewarm(["illustrator", "xd", "illustrator"])
        self.assertEqual(result, {"illustrator": "started", "xd": "started"})
        self.assertEqual(runtime._illustrator_client.starts, 1)
        self.assertEqual(runtime._xd_client.starts, 1)
        self.assertEqual(runtime._photoshop_client.starts, 0)

    def test_prewarm_all_starts_each_bridge_once(self) -> None:
        runtime = self._runtime()
        result = runtime.prewarm(["all"])
        self.assertEqual(set(result), {"photoshop", "illustrator", "xd"})
        self.assertTrue(all(value == "started" for value in result.values()))

    def test_prewarm_best_effort_reports_failure_without_killing_host(self) -> None:
        runtime = self._runtime()
        runtime._illustrator_client = _StartableBridge(error=RuntimeError("boom"))
        result = runtime.prewarm(["illustrator", "xd"])
        self.assertTrue(result["illustrator"].startswith("error:RuntimeError:"))
        self.assertEqual(result["xd"], "started")

    def test_prewarm_strict_raises(self) -> None:
        runtime = self._runtime()
        runtime._illustrator_client = _StartableBridge(error=RuntimeError("boom"))
        with self.assertRaisesRegex(RuntimeError, "failed to prewarm illustrator"):
            runtime.prewarm(["illustrator"], strict=True)


if __name__ == "__main__":
    unittest.main()
