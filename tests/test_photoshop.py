from __future__ import annotations

import unittest
from typing import Any, Mapping

from mcp_adobe import CapabilityRegistry, ExecutionPolicy, OperationUnknownError, PhotoshopAdapter


class FakeClient:
    def __init__(self, *, connected: bool = True, timeout_tools: set[str] | None = None) -> None:
        self._connected = connected
        self.timeout_tools = timeout_tools or set()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @property
    def connected(self) -> bool:
        return self._connected

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((name, dict(arguments)))
        if name in self.timeout_tools:
            raise TimeoutError(name)
        if name == "photoshop_ping":
            return {"text": "Successfully connected to Photoshop"}
        return {"tool": name, "arguments": dict(arguments)}


class PhotoshopAdapterTests(unittest.TestCase):
    def test_metadata_is_pinned_and_connected(self) -> None:
        adapter = PhotoshopAdapter(FakeClient(), version="27.0")
        info = adapter.info()
        self.assertEqual(info.application, "photoshop")
        self.assertTrue(info.connected)
        self.assertEqual(info.version, "27.0")
        self.assertEqual(info.upstream_repository, "alisaitteke/photoshop-mcp")
        self.assertEqual(info.upstream_snapshot, "ecd502c666f0e5b3889d3ef7bc42e5b3eb1119c2")
        self.assertTrue(info.undo_supported)
        self.assertIn("creative.context.get", info.common_capabilities)

    def test_bounded_interaction_surface_maps_to_exact_upstream_tools(self) -> None:
        client = FakeClient()
        adapter = PhotoshopAdapter(client)
        expected = {
            "creative.health": "photoshop_ping",
            "creative.capabilities": "photoshop_get_capabilities",
            "creative.context.get": "photoshop_get_state",
            "creative.document.info": "photoshop_get_state",
            "creative.document.preview": "photoshop_get_preview",
            "creative.selection.get": "photoshop_get_state",
            "creative.layer.list": "photoshop_get_layers",
            "creative.document.create": "photoshop_create_document",
            "creative.document.open": "photoshop_open_image",
            "creative.document.save": "photoshop_save_document",
            "creative.document.export": "photoshop_export_as",
            "creative.layer.select": "photoshop_select_layer_by_name",
            "creative.layer.create": "photoshop_create_layer",
            "creative.layer.rename": "photoshop_rename_layer",
            "creative.layer.delete": "photoshop_delete_layer",
            "creative.text.create": "photoshop_create_text_layer",
            "creative.text.update": "photoshop_update_text_content",
            "creative.object.move": "photoshop_move_layer",
            "creative.object.scale": "photoshop_scale_layer",
            "creative.object.rotate": "photoshop_rotate_layer",
            "creative.style.fill": "photoshop_fill_layer",
            "creative.style.opacity": "photoshop_set_layer_opacity",
            "creative.style.blend_mode": "photoshop_set_layer_blend_mode",
            "creative.selection.rectangle": "photoshop_select_rectangle",
            "creative.selection.ellipse": "photoshop_select_ellipse",
            "creative.selection.clear": "photoshop_deselect",
            "creative.mask.create": "photoshop_create_layer_mask",
            "creative.mask.delete": "photoshop_delete_layer_mask",
            "creative.undo": "photoshop_undo",
            "creative.redo": "photoshop_redo",
        }
        for capability, upstream_tool in expected.items():
            result = adapter.execute(capability, {})
            self.assertEqual(client.calls[-1][0], upstream_tool)
            if capability == "creative.context.get":
                self.assertEqual(result["context_source"], "live-photoshop-state")

    def test_open_path_is_translated_to_file_path(self) -> None:
        client = FakeClient()
        adapter = PhotoshopAdapter(client)
        adapter.execute("creative.document.open", {"path": "C:/work/photo.jpg"})
        self.assertEqual(client.calls[-1], ("photoshop_open_image", {"filePath": "C:/work/photo.jpg"}))

    def test_gateway_only_overwrite_flag_is_not_sent_upstream(self) -> None:
        client = FakeClient()
        adapter = PhotoshopAdapter(client)
        adapter.execute("creative.document.export", {"path": "C:/out/result.png", "format": "PNG", "overwrite": True})
        self.assertEqual(client.calls[-1], ("photoshop_export_as", {"path": "C:/out/result.png", "format": "PNG"}))

    def test_read_timeout_remains_timeout(self) -> None:
        adapter = PhotoshopAdapter(FakeClient(timeout_tools={"photoshop_get_state"}))
        with self.assertRaises(TimeoutError):
            adapter.execute("creative.document.info", {})

    def test_mutating_timeout_becomes_unknown_not_failure(self) -> None:
        adapter = PhotoshopAdapter(FakeClient(timeout_tools={"photoshop_create_document"}))
        with self.assertRaises(OperationUnknownError) as ctx:
            adapter.execute("creative.document.create", {"width": 100, "height": 100})
        self.assertEqual(ctx.exception.capability, "creative.document.create")
        self.assertEqual(ctx.exception.upstream_tool, "photoshop_create_document")

    def test_registry_allows_normal_bounded_transform_after_readiness_probe(self) -> None:
        client = FakeClient()
        registry = CapabilityRegistry()
        registry.register(PhotoshopAdapter(client))
        result = registry.execute("photoshop", "creative.object.move", {"deltaX": 12, "deltaY": 0})
        self.assertTrue(result["ok"])
        self.assertEqual(client.calls[0][0], "photoshop_ping")
        self.assertEqual(client.calls[-1], ("photoshop_move_layer", {"deltaX": 12, "deltaY": 0}))

    def test_registry_blocks_destructive_interaction_without_explicit_authorization(self) -> None:
        client = FakeClient()
        registry = CapabilityRegistry()
        registry.register(PhotoshopAdapter(client))
        with self.assertRaises(PermissionError):
            registry.execute("photoshop", "creative.layer.delete", {})
        self.assertEqual(client.calls, [])

    def test_registry_blocks_native_script_before_upstream_call(self) -> None:
        client = FakeClient()
        registry = CapabilityRegistry()
        registry.register(PhotoshopAdapter(client))
        with self.assertRaises(PermissionError):
            registry.execute("photoshop", "photoshop.execute_script", {"code": "alert('x')"})
        self.assertEqual(client.calls, [])

    def test_registry_can_enable_native_script_explicitly(self) -> None:
        client = FakeClient()
        registry = CapabilityRegistry()
        registry.register(PhotoshopAdapter(client))
        result = registry.execute("photoshop", "photoshop.execute_script", {"code": "return 1"}, policy=ExecutionPolicy(allow_native_script=True))
        self.assertTrue(result["ok"])
        self.assertEqual(client.calls[0][0], "photoshop_ping")
        self.assertEqual(client.calls[-1][0], "photoshop_execute_script")


if __name__ == "__main__":
    unittest.main()
