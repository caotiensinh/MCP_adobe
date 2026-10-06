from __future__ import annotations

import unittest
from typing import Any, Mapping

from mcp_adobe import CapabilityRegistry, ExecutionPolicy, IllustratorAdapter, OperationUnknownError


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
        if name == "list_fonts":
            return {"count": 1, "fonts": ["Arial"]}
        return {"tool": name, "arguments": dict(arguments)}


class IllustratorAdapterTests(unittest.TestCase):
    def test_metadata_is_pinned(self) -> None:
        info = IllustratorAdapter(FakeClient(), version="30.0").info()
        self.assertEqual(info.application, "illustrator")
        self.assertEqual(info.upstream_repository, "ie3jp/illustrator-mcp-server")
        self.assertEqual(info.upstream_snapshot, "57c5c101a5192c61535493f39b653e6f92b8eb29")
        self.assertTrue(info.undo_supported)

    def test_bounded_interaction_surface_maps_to_upstream_tools(self) -> None:
        client = FakeClient()
        adapter = IllustratorAdapter(client)
        expected = {
            "creative.document.info": "get_document_info",
            "creative.document.structure": "get_document_structure",
            "creative.selection.get": "get_selection",
            "creative.artboard.list": "get_artboards",
            "creative.layer.list": "get_layers",
            "creative.path.list": "get_path_items",
            "creative.group.list": "get_groups",
            "creative.text.list": "list_text_frames",
            "creative.object.find": "find_objects",
            "creative.document.create": "create_document",
            "creative.document.open": "open_document",
            "creative.document.save": "save_document",
            "creative.document.export": "export",
            "creative.document.export_pdf": "export_pdf",
            "creative.shape.rectangle": "create_rectangle",
            "creative.shape.ellipse": "create_ellipse",
            "creative.path.create": "create_path",
            "creative.text.create": "create_text_frame",
            "creative.object.update": "modify_object",
            "creative.object.select": "select_objects",
            "creative.object.group": "group_objects",
            "creative.object.ungroup": "ungroup_objects",
            "creative.object.z_order": "set_z_order",
            "creative.object.move_to_layer": "move_to_layer",
            "creative.gradient.create": "create_gradient",
            "creative.object.delete": "delete_objects",
            "creative.undo": "undo",
        }
        for capability, tool in expected.items():
            adapter.execute(capability, {})
            self.assertEqual(client.calls[-1][0], tool)

    def test_export_path_translates_to_output_path(self) -> None:
        client = FakeClient()
        adapter = IllustratorAdapter(client)
        adapter.execute(
            "creative.document.export",
            {"path": "C:/out/design.png", "format": "png", "target": "artboard:0"},
        )
        self.assertEqual(
            client.calls[-1],
            ("export", {
                "output_path": "C:/out/design.png",
                "format": "png",
                "target": "artboard:0",
            }),
        )

    def test_save_keeps_path_and_overwrite_for_upstream_guard(self) -> None:
        client = FakeClient()
        adapter = IllustratorAdapter(client)
        adapter.execute(
            "creative.document.save",
            {"mode": "save_as", "path": "C:/out/design.ai", "overwrite": False},
        )
        self.assertEqual(
            client.calls[-1],
            ("save_document", {
                "mode": "save_as",
                "path": "C:/out/design.ai",
                "overwrite": False,
            }),
        )

    def test_registry_allows_bounded_object_update_after_readiness_probe(self) -> None:
        client = FakeClient()
        registry = CapabilityRegistry()
        registry.register(IllustratorAdapter(client))
        result = registry.execute(
            "illustrator",
            "creative.object.update",
            {"uuid": "object-1", "x": 120, "y": 80},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(client.calls[0], ("list_fonts", {"limit": 1}))
        self.assertEqual(
            client.calls[-1],
            ("modify_object", {"uuid": "object-1", "x": 120, "y": 80}),
        )

    def test_registry_blocks_object_delete_without_explicit_authorization(self) -> None:
        client = FakeClient()
        registry = CapabilityRegistry()
        registry.register(IllustratorAdapter(client))
        with self.assertRaises(PermissionError):
            registry.execute("illustrator", "creative.object.delete", {"uuids": ["object-1"]})
        self.assertEqual(client.calls, [])

        result = registry.execute(
            "illustrator",
            "creative.object.delete",
            {"uuids": ["object-1"]},
            policy=ExecutionPolicy(allow_destructive=True),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(client.calls[0], ("list_fonts", {"limit": 1}))
        self.assertEqual(client.calls[-1][0], "delete_objects")

    def test_mutating_timeout_becomes_unknown(self) -> None:
        adapter = IllustratorAdapter(FakeClient(timeout_tools={"create_document"}))
        with self.assertRaises(OperationUnknownError):
            adapter.execute("creative.document.create", {"width": 100, "height": 100})

    def test_registry_blocks_disconnected_client(self) -> None:
        registry = CapabilityRegistry()
        registry.register(IllustratorAdapter(FakeClient(connected=False)))
        with self.assertRaises(RuntimeError):
            registry.execute("illustrator", "creative.document.info")


if __name__ == "__main__":
    unittest.main()
