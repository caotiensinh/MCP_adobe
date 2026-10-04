from __future__ import annotations

import asyncio
import unittest
from typing import Any, Mapping
from unittest.mock import patch
from uuid import UUID

from mcp import Client
from mcp.server.auth.provider import AccessToken, TokenVerifier

from mcp_adobe.audit import SecurityAuditEvent
from mcp_adobe.auth import OAuthResourceConfig
from mcp_adobe.photoshop import OperationUnknownError
from mcp_adobe.server import build_server


class CollectingAuditSink:
    def __init__(self) -> None:
        self.events: list[SecurityAuditEvent] = []

    def emit(self, event: SecurityAuditEvent, access_token: AccessToken | None) -> None:
        self.events.append(event)


class CorrelationRuntime:
    def __init__(self, mode: str = "verified") -> None:
        self.mode = mode
        self.calls = 0

    def describe(self):
        return ()

    def read(self, application: str, capability: str, arguments: Mapping[str, Any]):
        return {"mode": "read"}

    def write(
        self,
        application: str,
        capability: str,
        arguments: Mapping[str, Any],
        *,
        allow_overwrite: bool = False,
    ):
        self.calls += 1
        if self.mode == "unknown":
            raise OperationUnknownError(capability, "fake_write")
        if self.mode == "policy-denied":
            from mcp_adobe.core import PolicyError

            raise PolicyError("sensitive internal reason")
        if self.mode == "failed":
            raise RuntimeError("sensitive internal exception")
        return {
            "ok": True,
            "outcome": self.mode,
            "verification": {"status": self.mode},
        }

    def authorized_write(self, application, capability, arguments, **kwargs):
        return self.write(application, capability, arguments)

    def close(self) -> None:
        return


class NeverVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        return None


def access_only_config() -> OAuthResourceConfig:
    return OAuthResourceConfig(
        issuer_url="http://127.0.0.1:9000",
        resource_url="http://127.0.0.1:9001/mcp",
        introspection_endpoint="http://127.0.0.1:9000/introspect",
        required_scopes=("creative:access",),
    )


class OperationCorrelationTests(unittest.TestCase):
    @staticmethod
    async def call_write(server):
        async with Client(server) as client:
            return await client.call_tool(
                "creative_write",
                {
                    "application": "photoshop",
                    "capability": "creative.document.export",
                    "arguments": {"path": "out.png"},
                },
            )

    def test_success_returns_operation_id_and_audits_completed_outcome(self) -> None:
        sink = CollectingAuditSink()
        runtime = CorrelationRuntime("verified")
        server = build_server(runtime, audit_sink=sink)

        with patch("mcp_adobe.server.get_access_token", return_value=None):
            result = asyncio.run(self.call_write(server))

        self.assertFalse(result.is_error)
        operation_id = result.structured_content["operation_id"]
        UUID(operation_id)
        self.assertEqual(result.structured_content["outcome"], "verified")
        self.assertEqual([event.decision for event in sink.events], ["allowed", "completed"])
        self.assertEqual({event.operation_id for event in sink.events}, {operation_id})
        self.assertEqual(sink.events[-1].outcome, "verified")

    def test_timeout_audits_unknown_with_same_operation_id(self) -> None:
        sink = CollectingAuditSink()
        runtime = CorrelationRuntime("unknown")
        server = build_server(runtime, audit_sink=sink)

        with patch("mcp_adobe.server.get_access_token", return_value=None):
            result = asyncio.run(self.call_write(server))

        self.assertTrue(result.is_error)
        self.assertEqual([event.decision for event in sink.events], ["allowed", "unknown"])
        operation_ids = {event.operation_id for event in sink.events}
        self.assertEqual(len(operation_ids), 1)
        operation_id = next(iter(operation_ids))
        self.assertIsNotNone(operation_id)
        UUID(operation_id)
        self.assertEqual(sink.events[-1].outcome, "unknown")
        self.assertEqual(sink.events[-1].reason, "mutating-timeout")

    def test_runtime_policy_denial_is_correlated_without_leaking_reason(self) -> None:
        sink = CollectingAuditSink()
        server = build_server(CorrelationRuntime("policy-denied"), audit_sink=sink)

        with patch("mcp_adobe.server.get_access_token", return_value=None):
            result = asyncio.run(self.call_write(server))

        self.assertTrue(result.is_error)
        self.assertEqual([event.decision for event in sink.events], ["allowed", "denied"])
        self.assertEqual(sink.events[-1].reason, "runtime-policy-denied")
        self.assertNotIn("sensitive", sink.events[-1].reason)
        self.assertEqual(sink.events[0].operation_id, sink.events[1].operation_id)

    def test_unexpected_failure_is_correlated_without_exception_text(self) -> None:
        sink = CollectingAuditSink()
        server = build_server(CorrelationRuntime("failed"), audit_sink=sink)

        with patch("mcp_adobe.server.get_access_token", return_value=None):
            result = asyncio.run(self.call_write(server))

        self.assertTrue(result.is_error)
        self.assertEqual([event.decision for event in sink.events], ["allowed", "failed"])
        self.assertEqual(sink.events[-1].reason, "runtime-error:RuntimeError")
        self.assertNotIn("sensitive internal exception", sink.events[-1].reason)
        self.assertEqual(sink.events[0].operation_id, sink.events[1].operation_id)

    def test_profile_denial_has_operation_id_before_runtime(self) -> None:
        sink = CollectingAuditSink()
        runtime = CorrelationRuntime("verified")
        server = build_server(
            runtime,
            oauth_config=access_only_config(),
            token_verifier=NeverVerifier(),
            audit_sink=sink,
        )

        with patch("mcp_adobe.server.get_access_token", return_value=None):
            result = asyncio.run(self.call_write(server))

        self.assertTrue(result.is_error)
        self.assertEqual(runtime.calls, 0)
        self.assertEqual(len(sink.events), 1)
        self.assertEqual(sink.events[0].decision, "denied")
        self.assertEqual(sink.events[0].outcome, "denied")
        self.assertIsNotNone(sink.events[0].operation_id)
        UUID(sink.events[0].operation_id)


if __name__ == "__main__":
    unittest.main()
