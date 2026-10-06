from __future__ import annotations

import json
import unittest
from typing import Any, Mapping

from mcp_adobe import CapabilityRegistry, ExecutionPolicy, OperationUnknownError, PhotoshopAdapter


class FakeClient:
    def __init__(
        self,
        *,
        connected: bool = True,
        timeout_tools: set[str] | None = None,
        state: dict[str, Any] | None = None,
    ) -> None:
        self._connected = connected
        self.timeout_tools = timeout_tools or set()
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.state = state or {
            "hasDocument": True,
            "document": {"name": "Demo.psd"},
            "activeLayer": {
                "name": "Selected Layer",
                "opacity": 100,
                "blendMode": "BlendMode.NORMAL",
                "visible": True,
                "locked": False,
                "bounds": {"left": 10, "top": 20, "right": 110, "bottom": 120},
            },
        }

    @property
    def connected(self) -> bool:
        return self._connected

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        args = dict(arguments)
        self.calls.append((name, args))
        if name in self.timeout_tools:
            raise TimeoutError(name)
        if name == "photoshop_ping":
            return {"text": "Successfully connected to Photoshop"}
        if name == "photoshop_get_state":
            return {"content": [{"type": "text", "text": json.dumps(self.state)}]}

        layer = self.state.get("activeLayer")
        if isinstance(layer, dict):
            if name == "photoshop_move_layer":
                bounds = layer.get("bounds")
                if isinstance(bounds, dict):
                    dx = float(args["deltaX"])
                    dy = float(args["deltaY"])
                    bounds["left"] = float(bounds["left"]) + dx
                    bounds["right"] = float(bounds["right"]) + dx
                    bounds["top"] = float(bounds["top"]) + dy
                    bounds["bottom"] = float(bounds["bottom"]) + dy
            elif name == "photoshop_set_layer_opacity":
                layer["opacity"] = args["opacity"]
            elif name == "photoshop_set_layer_blend_mode":
                layer["blendMode"] = f"BlendMode.{args['blendMode']}"
            elif name == "photoshop_rename_layer":
                layer["name"] = args["name"]
            elif name == "photoshop_set_layer_visibility":
                layer["visible"] = args["visible"]
            elif name == "photoshop_set_layer_locked":
                layer["locked"] = args["locked"]
        return {"tool": name, "arguments": args}


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
        self.assertIn("creative.selection.move", info.common_capabilities)
        self.assertIn("creative.selection.update", info.common_capabilities)

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

    def test_live_selection_move_reads_active_layer_then_verifies_requested_delta(self) -> None:
        client = FakeClient()
        adapter = PhotoshopAdapter(client)
        result = adapter.execute("creative.selection.move", {"deltaX": 12, "deltaY": -4})

        self.assertEqual(
            [name for name, _ in client.calls],
            ["photoshop_get_state", "photoshop_move_layer", "photoshop_get_state"],
        )
        self.assertEqual(result["selection_source"], "live-photoshop-active-layer")
        self.assertEqual(result["selected_layer_name"], "Selected Layer")
        self.assertEqual(result["outcome"], "verified")
        self.assertEqual(result["verification"]["status"], "verified")
        self.assertEqual(result["verification"]["deltaX"], 12.0)
        self.assertEqual(result["verification"]["deltaY"], -4.0)

    def test_live_selection_update_reads_active_layer_then_verifies_opacity(self) -> None:
        client = FakeClient()
        adapter = PhotoshopAdapter(client)
        result = adapter.execute(
            "creative.selection.update",
            {"properties": {"opacity": 60}},
        )

        self.assertEqual(
            client.calls,
            [
                ("photoshop_get_state", {}),
                ("photoshop_set_layer_opacity", {"opacity": 60}),
                ("photoshop_get_state", {}),
            ],
        )
        self.assertEqual(result["selected_layer_name"], "Selected Layer")
        self.assertEqual(result["outcome"], "verified")
        self.assertEqual(result["verification"]["value"], 60)

    def test_live_selection_update_supports_rename_without_cached_layer_name(self) -> None:
        client = FakeClient()
        adapter = PhotoshopAdapter(client)
        result = adapter.execute(
            "creative.selection.update",
            {"properties": {"name": "Human Selected"}},
        )
        self.assertEqual(client.calls[1], ("photoshop_rename_layer", {"name": "Human Selected"}))
        self.assertEqual(result["selected_layer_name"], "Selected Layer")
        self.assertEqual(result["outcome"], "verified")

    def test_live_selection_update_rejects_multiple_properties_before_mutation(self) -> None:
        client = FakeClient()
        adapter = PhotoshopAdapter(client)
        with self.assertRaises(ValueError):
            adapter.execute(
                "creative.selection.update",
                {"properties": {"opacity": 50, "visible": True}},
            )
        self.assertEqual(client.calls, [("photoshop_get_state", {})])

    def test_live_selection_rejects_missing_active_layer_before_mutation(self) -> None:
        client = FakeClient(state={"hasDocument": True, "document": {"name": "Empty.psd"}, "activeLayer": None})
        adapter = PhotoshopAdapter(client)
        with self.assertRaises(RuntimeError):
            adapter.execute("creative.selection.move", {"deltaX": 1, "deltaY": 2})
        self.assertEqual(client.calls, [("photoshop_get_state", {})])

    def test_live_selection_read_timeout_is_not_unknown_mutation(self) -> None:
        adapter = PhotoshopAdapter(FakeClient(timeout_tools={"photoshop_get_state"}))
        with self.assertRaises(TimeoutError):
            adapter.execute("creative.selection.move", {"deltaX": 1, "deltaY": 2})

    def test_live_selection_mutation_timeout_becomes_unknown_after_target_resolution(self) -> None:
        client = FakeClient(timeout_tools={"photoshop_move_layer"})
        adapter = PhotoshopAdapter(client)
        with self.assertRaises(OperationUnknownError) as ctx:
            adapter.execute("creative.selection.move", {"deltaX": 1, "deltaY": 2})
        self.assertEqual(ctx.exception.capability, "creative.selection.move")
        self.assertEqual(ctx.exception.upstream_tool, "photoshop_move_layer")
        self.assertEqual(client.calls[0], ("photoshop_get_state", {}))
        self.assertEqual(client.calls[1], ("photoshop_move_layer", {"deltaX": 1, "deltaY": 2}))

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

    def test_registry_allows_live_selection_move_after_readiness_probe(self) -> None:
        client = FakeClient()
        registry = CapabilityRegistry()
        registry.register(PhotoshopAdapter(client))
        result = registry.execute("photoshop", "creative.selection.move", {"deltaX": 3, "deltaY": 4})
        self.assertTrue(result["ok"])
        self.assertEqual(client.calls[0], ("photoshop_ping", {}))
        self.assertEqual(client.calls[1], ("photoshop_get_state", {}))
        self.assertEqual(client.calls[2], ("photoshop_move_layer", {"deltaX": 3, "deltaY": 4}))

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
