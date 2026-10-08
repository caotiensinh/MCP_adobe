from __future__ import annotations

import json
import socket
import threading
import time
import unittest
from typing import Any, Mapping

from mcp_adobe import CapabilityRegistry, OperationUnknownError, XdAdapter
from mcp_adobe.xd_bridge import XdWebSocketBridgeClient


class FakeXdClient:
    def __init__(self, *, connected: bool = True, fail_timeout: bool = False) -> None:
        self._connected = connected
        self.fail_timeout = fail_timeout
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @property
    def connected(self) -> bool:
        return self._connected

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((name, dict(arguments)))
        if self.fail_timeout:
            raise TimeoutError(name)
        if name == "xd.direct.rectangle_create":
            return {"status": "applied", "approval_required": False, "result": {"name": arguments.get("name")}}
        if name.startswith("xd.queue.") and name != "xd.queue.status":
            return {"status": "queued", "approval_required": True, "operation_id": "xd-test-1"}
        return {"status": "ok", "method": name}


class XdAdapterTests(unittest.TestCase):
    def test_metadata_models_xd_approval_boundary(self) -> None:
        adapter = XdAdapter(FakeXdClient())
        info = adapter.info()
        self.assertTrue(info.connected)
        self.assertEqual(info.application, "xd")
        self.assertEqual(info.transport, "uxp-websocket-approval")
        self.assertFalse(info.undo_supported)
        self.assertIn("creative.context.get", info.common_capabilities)
        self.assertIn("xd.queue.rectangle_create", info.native_capabilities)

    def test_live_context_reads_document_and_current_selection(self) -> None:
        client = FakeXdClient()
        adapter = XdAdapter(client)
        result = adapter.execute("creative.context.get", {})
        self.assertEqual(client.calls, [("xd.document.info", {}), ("xd.selection.get", {})])
        self.assertEqual(result["context_source"], "live-document+selection")
        self.assertEqual(result["result"]["document"]["method"], "xd.document.info")
        self.assertEqual(result["result"]["selection"]["method"], "xd.selection.get")

    def test_direct_rectangle_maps_to_live_bridge_method(self) -> None:
        client = FakeXdClient()
        registry = CapabilityRegistry()
        registry.register(XdAdapter(client))
        result = registry.execute(
            "xd",
            "creative.shape.rectangle",
            {"name": "XD Direct Probe", "width": 160, "height": 96, "x": 32, "y": 40, "fill": "#F05A67"},
        )
        self.assertEqual(
            [name for name, _ in client.calls],
            ["xd.health", "xd.direct.rectangle_create"],
        )
        self.assertEqual(client.calls[1][1]["name"], "XD Direct Probe")
        self.assertFalse(result["result"]["approval_required"])
        self.assertEqual(result["result"]["status"], "applied")

    def test_queue_rectangle_maps_to_exact_bridge_method(self) -> None:
        client = FakeXdClient()
        registry = CapabilityRegistry()
        registry.register(XdAdapter(client))
        result = registry.execute("xd", "xd.queue.rectangle_create", {"width": 320, "height": 180, "fill": "#112233"})
        self.assertEqual([name for name, _ in client.calls], ["xd.health", "xd.queue.rectangle_create"])
        self.assertEqual(client.calls[1][1]["width"], 320)
        self.assertTrue(result["result"]["approval_required"])

    def test_writes_can_be_disabled_by_gateway(self) -> None:
        client = FakeXdClient()
        registry = CapabilityRegistry()
        registry.register(XdAdapter(client, writes_enabled=False))
        with self.assertRaises(PermissionError):
            registry.execute("xd", "xd.queue.text_create", {"text": "hello"})
        self.assertEqual(client.calls, [])

    def test_read_capability_remains_available_when_writes_disabled(self) -> None:
        client = FakeXdClient()
        registry = CapabilityRegistry()
        registry.register(XdAdapter(client, writes_enabled=False))
        result = registry.execute("xd", "creative.document.info")
        self.assertEqual(result["bridge_method"], "xd.document.info")

    def test_mutating_timeout_is_unknown_outcome(self) -> None:
        adapter = XdAdapter(FakeXdClient(fail_timeout=True))
        with self.assertRaises(OperationUnknownError):
            adapter.execute("xd.queue.selection_fill", {"fill": "#ffffff"})

    def test_read_timeout_stays_timeout(self) -> None:
        adapter = XdAdapter(FakeXdClient(fail_timeout=True))
        with self.assertRaises(TimeoutError):
            adapter.execute("creative.health", {})


class XdBridgeTests(unittest.TestCase):
    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def test_loopback_handshake_and_request_response(self) -> None:
        from websockets.sync.client import connect

        port = self._free_port()
        bridge = XdWebSocketBridgeClient(port=port, startup_timeout_seconds=3.0, call_timeout_seconds=3.0)
        bridge.start()
        try:
            with connect(bridge.url) as websocket:
                websocket.send(json.dumps({"type": "hello", "application": "xd", "version": "57.1.12.2", "protocol": 1}))
                deadline = time.monotonic() + 2.0
                while not bridge.connected and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(bridge.connected)
                self.assertEqual(bridge.plugin_info["version"], "57.1.12.2")
                holder: dict[str, Any] = {}

                def invoke() -> None:
                    holder["result"] = bridge.call_tool("xd.health", {"probe": True})

                worker = threading.Thread(target=invoke)
                worker.start()
                request = json.loads(websocket.recv(timeout=2.0))
                self.assertEqual(request["method"], "xd.health")
                self.assertEqual(request["params"], {"probe": True})
                websocket.send(json.dumps({"id": request["id"], "ok": True, "result": {"application": "xd", "bridge": "connected"}}))
                worker.join(timeout=2.0)
                self.assertFalse(worker.is_alive())
                self.assertEqual(holder["result"]["application"], "xd")
        finally:
            bridge.close()

    def test_non_loopback_bind_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            XdWebSocketBridgeClient(host="0.0.0.0")


if __name__ == "__main__":
    unittest.main()
