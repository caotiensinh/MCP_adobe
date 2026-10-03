from __future__ import annotations

import unittest
from typing import Any, Mapping

from mcp_adobe import CapabilityRegistry, IllustratorAdapter, OperationUnknownError


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
        return {"tool": name, "arguments": dict(arguments)}


class IllustratorAdapterTests(unittest.TestCase):
    def test_metadata_is_pinned(self) -> None:
        info = IllustratorAdapter(FakeClient(), version="30.0").info()
        self.assertEqual(info.application, "illustrator")
        self.assertEqual(info.upstream_repository, "ie3jp/illustrator-mcp-server")
        self.assertEqual(info.upstream_snapshot, "57c5c101a5192c61535493f39b653e6f92b8eb29")
        self.assertTrue(info.undo_supported)

    def test_subset_maps_to_upstream_tools(self) -> None:
        client = FakeClient()
        adapter = IllustratorAdapter(client)
        expected = {
            "creative.document.info": "get_document_info",
            "creative.document.structure": "get_document_structure",
            "creative.selection.get": "get_selection",
            "creative.document.create": "create_document",
            "creative.document.open": "open_document",
            "creative.document.save": "save_document",
            "creative.document.export": "export",
            "creative.document.export_pdf": "export_pdf",
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
