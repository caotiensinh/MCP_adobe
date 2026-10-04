from __future__ import annotations

import asyncio
import logging
import unittest
from typing import Any, Mapping

from mcp import Client

from mcp_adobe.audit import SecurityAuditEvent
from mcp_adobe.core import PolicyError
from mcp_adobe.server import build_server


class CollectingAuditSink:
    def __init__(self) -> None:
        self.events: list[SecurityAuditEvent] = []

    def emit(self, event, access_token) -> None:
        self.events.append(event)


class LeakyRuntime:
    def __init__(self, *, policy: bool) -> None:
        self.policy = policy

    def describe(self):
        return ()

    def read(self, application: str, capability: str, arguments: Mapping[str, Any]):
        return {}

    def write(self, application: str, capability: str, arguments: Mapping[str, Any], *, allow_overwrite: bool = False):
        if self.policy:
            raise PolicyError("TOP-SECRET-POLICY-DETAIL")
        raise RuntimeError("TOP-SECRET-RUNTIME-DETAIL")

    def authorized_write(self, application, capability, arguments, **kwargs):
        return self.write(application, capability, arguments)

    def close(self) -> None:
        return


async def _call_write(server):
    async with Client(server) as client:
        return await client.call_tool(
            "creative_write",
            {
                "application": "photoshop",
                "capability": "creative.document.export",
                "arguments": {"path": "out.png"},
            },
        )


class RuntimeLogRedactionTests(unittest.TestCase):
    def _exercise(self, *, policy: bool) -> tuple[str, CollectingAuditSink]:
        sink = CollectingAuditSink()
        server = build_server(LeakyRuntime(policy=policy), audit_sink=sink)
        with self.assertLogs(level=logging.ERROR) as captured:
            result = asyncio.run(_call_write(server))
        self.assertTrue(result.is_error)
        return "\n".join(captured.output), sink

    def test_runtime_policy_message_is_not_logged(self) -> None:
        logs, sink = self._exercise(policy=True)
        self.assertNotIn("TOP-SECRET-POLICY-DETAIL", logs)
        self.assertIn("operation denied by runtime policy", logs)
        self.assertEqual(sink.events[-1].decision, "denied")
        self.assertEqual(sink.events[-1].reason, "runtime-policy-denied")
        self.assertIsNotNone(sink.events[-1].operation_id)

    def test_unexpected_runtime_message_is_not_logged(self) -> None:
        logs, sink = self._exercise(policy=False)
        self.assertNotIn("TOP-SECRET-RUNTIME-DETAIL", logs)
        self.assertIn("operation failed", logs)
        self.assertEqual(sink.events[-1].decision, "failed")
        self.assertEqual(sink.events[-1].reason, "runtime-error:RuntimeError")
        self.assertIsNotNone(sink.events[-1].operation_id)


if __name__ == "__main__":
    unittest.main()
