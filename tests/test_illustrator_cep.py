from __future__ import annotations

import os
import unittest
from unittest import mock
from typing import Any, Mapping

from mcp_adobe.illustrator import IllustratorAdapter
from mcp_adobe.illustrator_cep import SUPPORTED_LEGACY_TOOLS, call_legacy_tool
from mcp_adobe.mcp_stdio import illustrator_stdio_config


class RawCaller:
    def __init__(self, responses: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self.responses = dict(responses or {})
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((name, dict(arguments)))
        return self.responses.get(name, {"schemaVersion": "1.1", "execution": "succeeded", "ok": True})


class FilteredClient:
    connected = True
    supported_legacy_tools = SUPPORTED_LEGACY_TOOLS

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        if name == "list_fonts":
            return {"count": 1, "fonts": ["Illustrator CEP bridge"]}
        return {"tool": name, "arguments": dict(arguments)}


class IllustratorCepCompatibilityTests(unittest.TestCase):
    def test_health_maps_to_live_connection_status(self) -> None:
        raw = RawCaller(
            {
                "illustrator_connection_status": {
                    "data": {
                        "layers": {
                            "server": {"status": "ok"},
                            "panel": {"status": "ok"},
                            "illustrator": {"status": "ok"},
                        }
                    }
                }
            }
        )

        result = call_legacy_tool(raw, "list_fonts", {"limit": 1})

        self.assertEqual(
            raw.calls,
            [
                (
                    "illustrator_connection_status",
                    {"params": {"probe": False, "timeout": 5.0}},
                )
            ],
        )
        self.assertEqual(result["count"], 1)
        self.assertIn("connection", result)

    def test_health_reports_not_ready_without_throwing(self) -> None:
        raw = RawCaller(
            {
                "illustrator_connection_status": {
                    "data": {
                        "ready": False,
                        "blockedAt": "panel",
                        "layers": {
                            "server": {"status": "ok"},
                            "panel": {
                                "status": "down",
                                "busy": False,
                                "activeRequestId": None,
                            },
                            "illustrator": {"status": "unknown"},
                        },
                    }
                }
            }
        )

        result = call_legacy_tool(raw, "list_fonts", {})

        self.assertFalse(result["ready"])
        self.assertEqual(
            result["connection"]["data"]["blockedAt"],
            "panel",
        )
        self.assertEqual(
            raw.calls,
            [
                (
                    "illustrator_connection_status",
                    {"params": {"probe": False, "timeout": 5.0}},
                )
            ],
        )

    def test_health_can_request_one_explicit_probe(self) -> None:
        raw = RawCaller(
            {
                "illustrator_connection_status": {
                    "data": {
                        "ready": True,
                        "blockedAt": None,
                        "layers": {
                            "server": {"status": "ok"},
                            "panel": {"status": "ok", "busy": False},
                            "illustrator": {"status": "ok"},
                            "document": {"status": "ok"},
                        },
                    }
                }
            }
        )

        result = call_legacy_tool(raw, "list_fonts", {"probe": True, "timeout": 3})

        self.assertTrue(result["ready"])
        self.assertEqual(
            raw.calls,
            [
                (
                    "illustrator_connection_status",
                    {"params": {"probe": True, "timeout": 3.0}},
                )
            ],
        )

    def test_selection_uses_ephemeral_handle_and_converts_native_bounds(self) -> None:
        raw = RawCaller(
            {
                "illustrator_query_items": {
                    "data": {
                        "report": {
                            "documentIntent": {
                                "observed": {
                                    "context": {"artboardRect": [0, 420, 640, 0]}
                                }
                            },
                            "artifacts": {
                                "items": [
                                    {
                                        "itemRef": {
                                            "identity": {"itemId": None},
                                            "itemType": "PathItem",
                                        },
                                        "handle": "h-123",
                                        "name": "Logo",
                                        "type": "PathItem",
                                        "bounds": {
                                            "left": 100,
                                            "top": 300,
                                            "width": 80,
                                            "height": 40,
                                        },
                                    }
                                ]
                            }
                        }
                    }
                },
            }
        )

        result = call_legacy_tool(raw, "get_selection", {})

        self.assertEqual(result["selectionCount"], 1)
        item = result["items"][0]
        self.assertEqual(item["uuid"], "handle:h-123")
        self.assertEqual(item["bounds"]["x"], 100.0)
        self.assertEqual(item["bounds"]["y"], 120.0)
        self.assertEqual(item["bounds"]["width"], 80.0)
        self.assertEqual(item["bounds"]["height"], 40.0)
        self.assertEqual(raw.calls[0][0], "illustrator_query_items")
        self.assertEqual(raw.calls[0][1]["params"]["targets"], {"type": "selection"})
        self.assertTrue(raw.calls[0][1]["params"]["include_handles"])
        self.assertEqual(len(raw.calls), 1)

    def test_selection_prefers_persistent_id_over_ephemeral_handle(self) -> None:
        raw = RawCaller(
            {
                "illustrator_query_items": {
                    "data": {
                        "report": {
                            "artifacts": {
                                "items": [
                                    {
                                        "itemRef": {
                                            "identity": {"itemId": "probe-1"},
                                            "itemType": "PathItem",
                                        },
                                        "handle": "h-123",
                                        "name": "Probe",
                                        "type": "PathItem",
                                        "bounds": {
                                            "left": 100,
                                            "top": 300,
                                            "width": 80,
                                            "height": 40,
                                        },
                                    }
                                ]
                            }
                        }
                    }
                },
                "illustrator_execute_script": {
                    "data": {"artboardRect": [0, 420, 640, 0]}
                },
            }
        )

        result = call_legacy_tool(raw, "get_selection", {})

        self.assertEqual(result["selectionCount"], 1)
        self.assertEqual(result["items"][0]["uuid"], "probe-1")
        self.assertEqual(result["items"][0]["handle"], "h-123")

    def test_modify_object_translates_handle_and_position_to_element_modify(self) -> None:
        raw = RawCaller()

        call_legacy_tool(
            raw,
            "modify_object",
            {
                "uuid": "handle:h-123",
                "properties": {
                    "position": {"x": 112, "y": 46},
                    "opacity": 60,
                },
            },
        )

        self.assertEqual(len(raw.calls), 1)
        tool, arguments = raw.calls[0]
        self.assertEqual(tool, "illustrator_execute_task")
        operation = arguments["params"]["batch"]["operations"][0]
        self.assertEqual(operation["task"], "element_modify")
        self.assertEqual(operation["targets"], {"type": "handle", "handles": ["h-123"]})
        self.assertEqual(operation["params"], {"x": 112, "y": 46, "opacity": 60})
        self.assertTrue(arguments["params"]["batch"]["stopOnError"])

    def test_document_create_maps_to_canonical_document_tool(self) -> None:
        raw = RawCaller()

        call_legacy_tool(
            raw,
            "create_document",
            {"width": 640, "height": 420, "color_mode": "RGB", "name": "Gateway Probe"},
        )

        self.assertEqual(
            raw.calls,
            [
                (
                    "illustrator_document",
                    {
                        "params": {
                            "action": "create",
                            "width": 640,
                            "height": 420,
                            "color_mode": "RGB",
                            "name": "Gateway Probe",
                        }
                    },
                )
            ],
        )

    def test_select_objects_uses_bounded_identity_script_and_readback(self) -> None:
        raw = RawCaller(
            {
                "illustrator_execute_script": {"data": {"selectedCount": 1}},
                "illustrator_query_items": {
                    "data": {
                        "report": {
                            "artifacts": {
                                "items": [
                                    {
                                        "itemRef": {
                                            "identity": {"itemId": "probe-1"},
                                            "itemType": "PathItem",
                                        },
                                        "name": "Probe",
                                        "type": "PathItem",
                                        "bounds": {"left": 100, "top": 300, "width": 80, "height": 40},
                                    }
                                ]
                            }
                        }
                    }
                },
            }
        )

        result = call_legacy_tool(raw, "select_objects", {"uuids": ["probe-1"]})

        self.assertEqual(result["selectedCount"], 1)
        self.assertEqual(result["tokens"], ["probe-1"])
        self.assertEqual(raw.calls[0][0], "illustrator_execute_script")
        params = raw.calls[0][1]["params"]
        self.assertEqual(params["params"], {"tokens": ["probe-1"]})
        self.assertEqual(params["includes"], ["mcp_id", "handles"])
        self.assertFalse(params["read_only"])
        self.assertEqual(params["auto_assign_ids"], "off")
        self.assertIn("findItemsByMcpId", params["script"])
        self.assertIn("mcpResolveHandle", params["script"])
        self.assertEqual(raw.calls[1][0], "illustrator_query_items")

    def test_unproven_legacy_tools_are_not_exposed(self) -> None:
        for name in ("export_pdf", "create_gradient"):
            self.assertNotIn(name, SUPPORTED_LEGACY_TOOLS)
            with self.assertRaises(LookupError):
                call_legacy_tool(RawCaller(), name, {})

    def test_real_backend_metadata_filters_unproven_capabilities(self) -> None:
        info = IllustratorAdapter(FilteredClient()).info()

        self.assertEqual(info.upstream_repository, "jinkeda/Illustrator_MCP")
        self.assertEqual(info.upstream_snapshot, "5d7a3edc8ebc89a0fc56b059e1311d3b2bfca815")
        self.assertEqual(info.transport, "mcp+cep-websocket")
        self.assertIn("creative.health", info.common_capabilities)
        self.assertIn("creative.selection.update", info.common_capabilities)
        self.assertIn("creative.shape.rectangle", info.common_capabilities)
        self.assertIn("creative.undo", info.common_capabilities)
        self.assertNotIn("creative.document.export_pdf", info.common_capabilities)
        self.assertIn("creative.object.select", info.common_capabilities)
        self.assertNotIn("creative.gradient.create", info.common_capabilities)

    def test_config_uses_dedicated_upstream_python_and_fixed_panel_endpoint(self) -> None:
        custom_python = r"C:\MCPAdobe\illustrator\python.exe"
        with mock.patch.dict(os.environ, {"MCP_ADOBE_ILLUSTRATOR_PYTHON": custom_python}, clear=False):
            config = illustrator_stdio_config()

        self.assertEqual(config.command, custom_python)
        self.assertEqual(config.args, ("-B", "-m", "illustrator_mcp.server"))
        self.assertEqual(config.env["WS_HOST"], "127.0.0.1")
        self.assertEqual(config.env["WS_PORT"], "8081")
        self.assertEqual(config.compatibility, "illustrator-cep")
        self.assertGreaterEqual(config.startup_timeout_seconds, 90.0)


if __name__ == "__main__":
    unittest.main()
