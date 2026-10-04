from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "real_e2e", Path(__file__).parents[1] / "scripts" / "real_e2e.py"
)
real_e2e = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(real_e2e)


class FakeClient:
    toolset: set[str] = set()

    def __init__(self, config):
        self.tool_names = frozenset(self.toolset)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if name == "photoshop_ping":
            return {"connected": True}
        if name == "photoshop_get_state":
            return {"hasDocument": False}
        if name == "get_document_info":
            return {"fileName": "x.ai"}
        if name == "photoshop_save_document":
            Path(arguments["path"]).write_bytes(b"psd")
        if name == "photoshop_export_as":
            Path(arguments["path"]).write_bytes(b"png")
        if name == "save_document":
            Path(arguments["path"]).write_bytes(b"ai")
        if name == "export":
            Path(arguments["output_path"]).write_bytes(b"png")
        return {"ok": True}


class PhotoshopClient(FakeClient):
    toolset = {
        "photoshop_ping",
        "photoshop_get_state",
        "photoshop_create_document",
        "photoshop_save_document",
        "photoshop_export_as",
        "photoshop_undo",
    }


class IllustratorClient(FakeClient):
    toolset = {"get_document_info", "create_document", "save_document", "export", "undo"}


class SmokeTests(unittest.TestCase):
    def test_photoshop_read_only(self):
        self.assertEqual(real_e2e.run("photoshop", client_factory=PhotoshopClient), 0)

    def test_photoshop_disconnected_ping_fails_before_state_or_write(self):
        class DisconnectedPhotoshopClient(PhotoshopClient):
            def call_tool(self, name, arguments):
                if name == "photoshop_ping":
                    self.calls.append((name, dict(arguments)))
                    return {"text": "Failed to connect to Photoshop"}
                return super().call_tool(name, arguments)

        self.assertEqual(real_e2e.run("photoshop", client_factory=DisconnectedPhotoshopClient), 1)

    def test_photoshop_write_verifies_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(
                real_e2e.run(
                    "photoshop", write=True, output_dir=Path(td), client_factory=PhotoshopClient
                ),
                0,
            )
            self.assertTrue((Path(td) / "mcp_adobe_smoke.psd").exists())
            self.assertTrue((Path(td) / "mcp_adobe_smoke.png").exists())

    def test_illustrator_read_only(self):
        self.assertEqual(real_e2e.run("illustrator", client_factory=IllustratorClient), 0)

    def test_illustrator_write_verifies_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(
                real_e2e.run(
                    "illustrator", write=True, output_dir=Path(td), client_factory=IllustratorClient
                ),
                0,
            )
            self.assertTrue((Path(td) / "mcp_adobe_smoke.ai").exists())
            self.assertTrue((Path(td) / "mcp_adobe_smoke.png").exists())

    def test_logical_error_true_fails(self):
        class LogicalErrorClient(IllustratorClient):
            def call_tool(self, name, arguments):
                if name == "get_document_info":
                    return {"error": True, "message": "Illustrator unavailable"}
                return super().call_tool(name, arguments)

        self.assertEqual(real_e2e.run("illustrator", write=True, client_factory=LogicalErrorClient), 1)

    def test_logical_success_false_fails(self):
        class LogicalFailureClient(IllustratorClient):
            def call_tool(self, name, arguments):
                if name == "create_document":
                    return {"success": False, "message": "create failed"}
                return super().call_tool(name, arguments)

        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(
                real_e2e.run(
                    "illustrator", write=True, output_dir=Path(td), client_factory=LogicalFailureClient
                ),
                1,
            )

    def test_logical_ok_false_fails(self):
        class LogicalFailureClient(PhotoshopClient):
            def call_tool(self, name, arguments):
                if name == "photoshop_get_state":
                    return {"ok": False, "message": "state failed"}
                return super().call_tool(name, arguments)

        self.assertEqual(real_e2e.run("photoshop", client_factory=LogicalFailureClient), 1)

    def test_missing_tool_fails(self):
        class Missing(FakeClient):
            toolset = {"photoshop_ping"}

        self.assertEqual(real_e2e.run("photoshop", client_factory=Missing), 1)


if __name__ == "__main__":
    unittest.main()
