from __future__ import annotations

import unittest
from typing import Any, Mapping

from mcp_adobe.core import CapabilityRegistry
from mcp_adobe.illustrator import IllustratorAdapter
from mcp_adobe.photoshop import PhotoshopAdapter
from mcp_adobe.xd import XdAdapter


class FakeClient:
    def __init__(
        self,
        responses: Mapping[str, Mapping[str, Any]] | None = None,
        *,
        connected: bool = True,
        errors: set[str] | None = None,
    ) -> None:
        self._connected = connected
        self.responses = {name: dict(value) for name, value in (responses or {}).items()}
        self.errors = errors or set()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @property
    def connected(self) -> bool:
        return self._connected

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((name, dict(arguments)))
        if name in self.errors:
            raise RuntimeError(f"simulated failure: {name}")
        return dict(self.responses.get(name, {"status": "ok", "tool": name}))


class PhotoshopReadinessTests(unittest.TestCase):
    def test_successful_ping_allows_write_and_is_cached(self) -> None:
        client = FakeClient(
            {
                "photoshop_ping": {"text": "Successfully connected to Photoshop"},
                "photoshop_create_document": {"documentId": 1},
            }
        )
        registry = CapabilityRegistry()
        registry.register(PhotoshopAdapter(client))

        registry.execute("photoshop", "creative.document.create", {"width": 100, "height": 100})
        registry.execute("photoshop", "creative.document.create", {"width": 200, "height": 200})

        self.assertEqual([name for name, _ in client.calls].count("photoshop_ping"), 1)
        self.assertEqual(
            [name for name, _ in client.calls].count("photoshop_create_document"),
            2,
        )

    def test_failed_ping_blocks_write_before_mutation(self) -> None:
        client = FakeClient(
            {
                "photoshop_ping": {"text": "Failed to connect to Photoshop"},
                "photoshop_create_document": {"documentId": 1},
            }
        )
        registry = CapabilityRegistry()
        registry.register(PhotoshopAdapter(client))

        with self.assertRaisesRegex(RuntimeError, "application is not ready: photoshop"):
            registry.execute("photoshop", "creative.document.create", {"width": 100, "height": 100})

        self.assertEqual(client.calls, [("photoshop_ping", {})])

    def test_read_remains_available_without_readiness_preflight(self) -> None:
        client = FakeClient(
            {
                "photoshop_get_state": {"hasDocument": False},
                "photoshop_ping": {"text": "Failed to connect to Photoshop"},
            }
        )
        registry = CapabilityRegistry()
        registry.register(PhotoshopAdapter(client))

        result = registry.execute("photoshop", "creative.document.info")

        self.assertEqual(result["result"], {"hasDocument": False})
        self.assertEqual(client.calls, [("photoshop_get_state", {})])

    def test_metadata_keeps_connected_as_transport_and_declares_readiness_probe(self) -> None:
        adapter = PhotoshopAdapter(FakeClient(connected=True))
        info = adapter.info()
        self.assertTrue(info.connected)
        self.assertEqual(info.readiness_probe, "creative.health")


class IllustratorReadinessTests(unittest.TestCase):
    def test_write_reuses_list_fonts_limit_one_as_app_probe(self) -> None:
        client = FakeClient(
            {
                "list_fonts": {"count": 1, "totalAvailable": 123, "fonts": [{"name": "ArialMT"}]},
                "create_document": {"created": True},
            }
        )
        registry = CapabilityRegistry()
        registry.register(IllustratorAdapter(client))

        registry.execute("illustrator", "creative.document.create", {"width": 100, "height": 100})

        self.assertEqual(client.calls[0], ("list_fonts", {"limit": 1}))
        self.assertEqual(client.calls[1][0], "create_document")

    def test_error_health_result_blocks_write(self) -> None:
        client = FakeClient(
            {
                "list_fonts": {"error": True, "message": "Illustrator is not available"},
                "create_document": {"created": True},
            }
        )
        registry = CapabilityRegistry()
        registry.register(IllustratorAdapter(client))

        with self.assertRaisesRegex(RuntimeError, "application is not ready: illustrator"):
            registry.execute("illustrator", "creative.document.create", {"width": 100, "height": 100})

        self.assertEqual(client.calls, [("list_fonts", {"limit": 1})])

    def test_explicit_health_capability_uses_list_fonts_limit_one(self) -> None:
        client = FakeClient(
            {"list_fonts": {"count": 0, "totalAvailable": 0, "fonts": []}}
        )
        registry = CapabilityRegistry()
        registry.register(IllustratorAdapter(client))

        result = registry.execute("illustrator", "creative.health")

        self.assertEqual(client.calls, [("list_fonts", {"limit": 1})])
        self.assertEqual(result["upstream_tool"], "list_fonts")
        self.assertEqual(result["outcome"], "read")


class XdReadinessTests(unittest.TestCase):
    def test_healthy_bridge_allows_approval_queue(self) -> None:
        client = FakeClient(
            {
                "xd.health": {"application": "xd", "status": "ok", "bridge": "connected"},
                "xd.queue.rectangle_create": {
                    "status": "queued",
                    "approval_required": True,
                    "operation_id": "xd-op-1",
                },
            }
        )
        registry = CapabilityRegistry()
        registry.register(XdAdapter(client))

        result = registry.execute(
            "xd",
            "xd.queue.rectangle_create",
            {"width": 100, "height": 100},
        )

        self.assertEqual(client.calls[0], ("xd.health", {}))
        self.assertEqual(client.calls[1][0], "xd.queue.rectangle_create")
        self.assertEqual(result["outcome"], "pending_user_approval")

    def test_unhealthy_bridge_blocks_queue_before_mutation(self) -> None:
        client = FakeClient(
            {
                "xd.health": {"application": "xd", "status": "error", "error": True},
                "xd.queue.rectangle_create": {
                    "status": "queued",
                    "approval_required": True,
                },
            }
        )
        registry = CapabilityRegistry()
        registry.register(XdAdapter(client))

        with self.assertRaisesRegex(RuntimeError, "application is not ready: xd"):
            registry.execute(
                "xd",
                "xd.queue.rectangle_create",
                {"width": 100, "height": 100},
            )

        self.assertEqual(client.calls, [("xd.health", {})])


if __name__ == "__main__":
    unittest.main()
