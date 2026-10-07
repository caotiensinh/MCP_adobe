from __future__ import annotations

import unittest
from typing import Any, Mapping

from mcp_adobe import CapabilityRegistry, ExecutionPolicy, IllustratorAdapter, OperationUnknownError


class FakeClient:
    def __init__(
        self,
        *,
        connected: bool = True,
        timeout_tools: set[str] | None = None,
        selection_items: list[dict[str, Any]] | None = None,
    ) -> None:
        self._connected = connected
        self.timeout_tools = timeout_tools or set()
        self.selection_items = (
            selection_items
            if selection_items is not None
            else [{"uuid": "selected-1", "name": "Logo", "bounds": {"x": 100, "y": 50, "width": 80, "height": 40}}]
        )
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
        if name == "get_selection":
            return {
                "selectionCount": len(self.selection_items),
                "coordinateSystem": arguments.get("coordinate_system", "artboard-web"),
                "items": list(self.selection_items),
            }
        if name == "modify_object":
            return {
                "success": True,
                "uuid": arguments.get("uuid"),
                "verified": {"uuid": arguments.get("uuid")},
            }
        return {"tool": name, "arguments": dict(arguments)}


class IllustratorAdapterTests(unittest.TestCase):
    def test_metadata_is_pinned(self) -> None:
        info = IllustratorAdapter(FakeClient(), version="30.0").info()
        self.assertEqual(info.application, "illustrator")
        self.assertEqual(info.upstream_repository, "jinkeda/Illustrator_MCP")
        self.assertEqual(info.upstream_snapshot, "5d7a3edc8ebc89a0fc56b059e1311d3b2bfca815")
        self.assertEqual(info.transport, "mcp+cep-websocket")
        self.assertTrue(info.undo_supported)
        self.assertIn("creative.context.get", info.common_capabilities)
        self.assertIn("creative.selection.update", info.common_capabilities)
        self.assertIn("creative.selection.move", info.common_capabilities)
        self.assertIn("creative.job.status", info.common_capabilities)

    def test_health_preserves_probe_and_timeout_arguments(self) -> None:
        client = FakeClient()
        adapter = IllustratorAdapter(client)
        adapter.execute("creative.health", {"probe": True, "timeout": 7.5})
        self.assertEqual(
            client.calls[-1],
            ("list_fonts", {"limit": 1, "probe": True, "timeout": 7.5}),
        )

    def test_job_status_is_read_only_and_disables_export_finalization(self) -> None:
        client = FakeClient()
        adapter = IllustratorAdapter(client)
        result = adapter.execute(
            "creative.job.status",
            {"jobId": "job_readonly_1", "detail": "summary"},
        )
        self.assertEqual(
            client.calls[-1],
            (
                "illustrator_job_status",
                {"jobId": "job_readonly_1", "detail": "summary", "finalize_export": False},
            ),
        )
        self.assertEqual(result["outcome"], "read")

        before = list(client.calls)
        with self.assertRaisesRegex(ValueError, "finalize_export"):
            adapter.execute(
                "creative.job.status",
                {"jobId": "job_readonly_1", "finalize_export": True},
            )
        self.assertEqual(client.calls, before)

    def test_job_status_requires_job_id(self) -> None:
        client = FakeClient()
        adapter = IllustratorAdapter(client)
        with self.assertRaisesRegex(ValueError, "jobId"):
            adapter.execute("creative.job.status", {})
        self.assertEqual(client.calls, [])

    def test_live_context_reads_document_and_current_selection(self) -> None:
        client = FakeClient()
        adapter = IllustratorAdapter(client)
        result = adapter.execute("creative.context.get", {})
        self.assertEqual(client.calls, [("get_document_info", {}), ("get_selection", {})])
        self.assertEqual(result["context_source"], "live-document+selection")
        self.assertEqual(result["result"]["document"]["tool"], "get_document_info")
        self.assertEqual(result["result"]["selection"]["items"][0]["uuid"], "selected-1")

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
            "creative.job.status": "illustrator_job_status",
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

    def test_selection_update_rereads_live_selection_and_injects_uuid(self) -> None:
        client = FakeClient(selection_items=[{"uuid": "mouse-selected", "bounds": {"x": 10, "y": 20}}])
        registry = CapabilityRegistry()
        registry.register(IllustratorAdapter(client))

        result = registry.execute(
            "illustrator",
            "creative.selection.update",
            {"properties": {"opacity": 60}},
        )

        self.assertEqual(
            client.calls,
            [
                ("list_fonts", {"limit": 1}),
                ("get_selection", {}),
                ("modify_object", {"uuid": "mouse-selected", "properties": {"opacity": 60}}),
            ],
        )
        self.assertEqual(result["selection_source"], "live-get_selection")
        self.assertEqual(result["selected_uuid"], "mouse-selected")

    def test_selection_move_converts_delta_to_absolute_position_from_fresh_bounds(self) -> None:
        client = FakeClient(selection_items=[{"uuid": "mouse-selected", "bounds": {"x": 100, "y": 50}}])
        registry = CapabilityRegistry()
        registry.register(IllustratorAdapter(client))

        result = registry.execute(
            "illustrator",
            "creative.selection.move",
            {"deltaX": 12, "deltaY": -4},
        )

        self.assertEqual(
            client.calls[-1],
            (
                "modify_object",
                {
                    "uuid": "mouse-selected",
                    "properties": {"position": {"x": 112, "y": 46}},
                },
            ),
        )
        self.assertEqual(result["selected_uuid"], "mouse-selected")

    def test_selection_update_rejects_no_selection_before_mutation(self) -> None:
        client = FakeClient(selection_items=[])
        registry = CapabilityRegistry()
        registry.register(IllustratorAdapter(client))
        with self.assertRaisesRegex(ValueError, "no Illustrator object"):
            registry.execute(
                "illustrator",
                "creative.selection.update",
                {"properties": {"opacity": 60}},
            )
        self.assertEqual([name for name, _ in client.calls], ["list_fonts", "get_selection"])

    def test_selection_update_rejects_multiple_selection_before_mutation(self) -> None:
        client = FakeClient(
            selection_items=[
                {"uuid": "a", "bounds": {"x": 0, "y": 0}},
                {"uuid": "b", "bounds": {"x": 10, "y": 10}},
            ]
        )
        registry = CapabilityRegistry()
        registry.register(IllustratorAdapter(client))
        with self.assertRaisesRegex(ValueError, "exactly one Illustrator object"):
            registry.execute(
                "illustrator",
                "creative.selection.update",
                {"properties": {"opacity": 60}},
            )
        self.assertEqual([name for name, _ in client.calls], ["list_fonts", "get_selection"])

    def test_selection_read_timeout_is_not_misreported_as_unknown_mutation(self) -> None:
        client = FakeClient(timeout_tools={"get_selection"})
        registry = CapabilityRegistry()
        registry.register(IllustratorAdapter(client))
        with self.assertRaises(TimeoutError):
            registry.execute(
                "illustrator",
                "creative.selection.update",
                {"properties": {"opacity": 60}},
            )
        self.assertEqual([name for name, _ in client.calls], ["list_fonts", "get_selection"])

    def test_selection_modify_timeout_becomes_unknown_after_target_resolution(self) -> None:
        client = FakeClient(timeout_tools={"modify_object"})
        registry = CapabilityRegistry()
        registry.register(IllustratorAdapter(client))
        with self.assertRaises(OperationUnknownError) as ctx:
            registry.execute(
                "illustrator",
                "creative.selection.update",
                {"properties": {"opacity": 60}},
            )
        self.assertEqual(ctx.exception.capability, "creative.selection.update")
        self.assertEqual([name for name, _ in client.calls], ["list_fonts", "get_selection", "modify_object"])

    def test_export_path_translates_to_output_path(self) -> None:
        client = FakeClient()
        adapter = IllustratorAdapter(client)
        adapter.execute("creative.document.export", {"path": "C:/out/design.png", "format": "png", "target": "artboard:0"})
        self.assertEqual(client.calls[-1], ("export", {"output_path": "C:/out/design.png", "format": "png", "target": "artboard:0"}))

    def test_save_keeps_path_and_overwrite_for_upstream_guard(self) -> None:
        client = FakeClient()
        adapter = IllustratorAdapter(client)
        adapter.execute("creative.document.save", {"mode": "save_as", "path": "C:/out/design.ai", "overwrite": False})
        self.assertEqual(client.calls[-1], ("save_document", {"mode": "save_as", "path": "C:/out/design.ai", "overwrite": False}))

    def test_registry_allows_bounded_object_update_after_readiness_probe(self) -> None:
        client = FakeClient()
        registry = CapabilityRegistry()
        registry.register(IllustratorAdapter(client))
        result = registry.execute("illustrator", "creative.object.update", {"uuid": "object-1", "x": 120, "y": 80})
        self.assertTrue(result["ok"])
        self.assertEqual(client.calls[0], ("list_fonts", {"limit": 1}))
        self.assertEqual(client.calls[-1], ("modify_object", {"uuid": "object-1", "x": 120, "y": 80}))

    def test_registry_blocks_object_delete_without_explicit_authorization(self) -> None:
        client = FakeClient()
        registry = CapabilityRegistry()
        registry.register(IllustratorAdapter(client))
        with self.assertRaises(PermissionError):
            registry.execute("illustrator", "creative.object.delete", {"uuids": ["object-1"]})
        self.assertEqual(client.calls, [])
        result = registry.execute("illustrator", "creative.object.delete", {"uuids": ["object-1"]}, policy=ExecutionPolicy(allow_destructive=True))
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
