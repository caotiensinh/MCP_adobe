"""Opt-in experimental Mode 2 MCP surface: no automatic live mutation."""
from __future__ import annotations

import copy
import unittest

from mcp_adobe.xd import XdAdapter
from mcp_adobe.xd_mode2_experimental import ExperimentalXdMode2Adapter


ARGS = {
    "document_id": "98d6635b-3767-4254-b200-ec8442b69ad2",
    "node_id": "130fdb64-c691-4374-ab46-66fd3f9e077c",
    "bounds": {"left": 484, "top": 166, "right": 584, "bottom": 280},
}
FILL = {**ARGS, "fill": "#A1B2C3", "isolated_test_copy": True, "user_confirmed": True}


class FakeExperimentalBridge:
    connected = True

    def __init__(self, timeout=False):
        self.calls = []
        self.timeout = timeout

    def call_tool(self, method, arguments):
        self.calls.append((method, copy.deepcopy(arguments)))
        if self.timeout:
            raise TimeoutError("unknown delivery")
        if method == "xd.mode2.node.inspect":
            return {"document_id": arguments["document_id"], "node_id": arguments["node_id"]}
        if method == "xd.queue.mode2_fill":
            return {"status": "queued", "approval_required": True, "operation_id": "test-op-1"}
        raise AssertionError("unexpected method " + method)


class XdMode2AdapterTests(unittest.TestCase):
    def test_ordinary_xd_adapter_remains_unchanged_and_no_mode2_dispatch(self):
        bridge = FakeExperimentalBridge()
        adapter = XdAdapter(bridge)
        self.assertNotIn("xd.mode2.node.inspect", adapter.info().native_capabilities)
        self.assertNotIn("xd.queue.mode2_fill", adapter.info().native_capabilities)
        self.assertFalse(adapter.info().undo_supported)
        for capability, args in (("xd.mode2.node.inspect", ARGS), ("xd.queue.mode2_fill", FILL)):
            with self.subTest(capability=capability), self.assertRaises(LookupError):
                adapter.execute(capability, args)
        self.assertEqual(bridge.calls, [])

    def test_inspect_is_read_only_with_exact_arguments(self):
        bridge = FakeExperimentalBridge()
        adapter = ExperimentalXdMode2Adapter(bridge, writes_enabled=False)
        self.assertIn("xd.mode2.node.inspect", adapter.info().native_capabilities)
        result = adapter.execute("xd.mode2.node.inspect", ARGS)
        self.assertEqual(result["bridge_method"], "xd.mode2.node.inspect")
        self.assertEqual(result["outcome"], "read")
        self.assertEqual(bridge.calls, [("xd.mode2.node.inspect", ARGS)])

    def test_fill_requires_explicit_opt_in_and_produces_approval_receipt(self):
        bridge = FakeExperimentalBridge()
        adapter = ExperimentalXdMode2Adapter(bridge)
        result = adapter.execute("xd.queue.mode2_fill", FILL)
        self.assertEqual(result["bridge_method"], "xd.queue.mode2_fill")
        self.assertEqual(result["outcome"], "pending_user_approval")
        self.assertEqual(result["result"]["status"], "queued")
        self.assertEqual(bridge.calls, [("xd.queue.mode2_fill", FILL)])
        self.assertFalse(adapter.info().undo_supported)

    def test_explicit_writes_disabled_even_when_experimental_opted_in(self):
        bridge = FakeExperimentalBridge()
        adapter = ExperimentalXdMode2Adapter(bridge, writes_enabled=False)
        with self.assertRaises(PermissionError):
            adapter.execute("xd.queue.mode2_fill", FILL)
        self.assertEqual(bridge.calls, [])

    def test_invalid_target_or_color_never_reaches_bridge(self):
        cases = [
            {"bounds": {**ARGS["bounds"], "right": 480}},
            {"bounds": {**ARGS["bounds"], "left": float("nan")}},
            {"bounds": {**ARGS["bounds"], "left": True}},
            {"bounds": {"left": 1, "right": 2}},
            {"document_id": ""},
            {"node_id": ""},
            {"node_id": None},
            {"fill": "#ZZZZZZ"},
            {"fill": "#000"},
            {"isolated_test_copy": False},
            {"user_confirmed": False},
            {"untrusted_extra": "1"},
        ]
        for change in cases:
            with self.subTest(change=change):
                bridge = FakeExperimentalBridge()
                adapter = ExperimentalXdMode2Adapter(bridge)
                with self.assertRaises(ValueError):
                    adapter.execute("xd.queue.mode2_fill", {**FILL, **change})
                self.assertEqual(bridge.calls, [])

    def test_inspect_cannot_sneak_in_write_parameters(self):
        bridge = FakeExperimentalBridge()
        adapter = ExperimentalXdMode2Adapter(bridge)
        with self.assertRaises(ValueError):
            adapter.execute("xd.mode2.node.inspect", FILL)
        self.assertEqual(bridge.calls, [])

    def test_write_timeout_must_be_unverified_not_auto_retried(self):
        from mcp_adobe.photoshop import OperationUnknownError
        bridge = FakeExperimentalBridge(timeout=True)
        adapter = ExperimentalXdMode2Adapter(bridge)
        with self.assertRaises(OperationUnknownError):
            adapter.execute("xd.queue.mode2_fill", FILL)
        self.assertEqual(len(bridge.calls), 1)


if __name__ == "__main__":
    unittest.main()
