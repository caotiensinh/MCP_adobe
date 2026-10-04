from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mcp_adobe.mcp_stdio import (
    McpSubprocessToolClient,
    UpstreamToolError,
    illustrator_stdio_config,
    photoshop_stdio_config,
)


class Text:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class TransportTests(unittest.TestCase):
    def test_photoshop_launcher_is_pinned(self) -> None:
        with patch.dict("os.environ", {}, clear=True), patch(
            "mcp_adobe.mcp_stdio._running_photoshop_path", return_value=None
        ):
            cfg = photoshop_stdio_config()
        self.assertEqual(cfg.command, "npx")
        self.assertEqual(cfg.args, ("-y", "@alisaitteke/photoshop-mcp@1.7.32"))
        self.assertEqual(cfg.env["PSMCP_FEEDBACK"], "0")
        self.assertEqual(cfg.env["PSMCP_UPDATE_CHECK"], "0")
        self.assertNotIn("PHOTOSHOP_PATH", cfg.env)

    def test_photoshop_launcher_forwards_explicit_path_override(self) -> None:
        custom = r"D:\Photoshop_Custom\Adobe Photoshop 2023\Photoshop.exe"
        with patch.dict("os.environ", {"PHOTOSHOP_PATH": custom}, clear=True), patch(
            "mcp_adobe.mcp_stdio._running_photoshop_path"
        ) as detect:
            cfg = photoshop_stdio_config()
        self.assertEqual(cfg.env["PHOTOSHOP_PATH"], custom)
        detect.assert_not_called()

    def test_photoshop_launcher_uses_running_process_when_override_missing(self) -> None:
        custom = r"D:\Photoshop_Custom\Adobe Photoshop 2023\Photoshop.exe"
        with patch.dict("os.environ", {}, clear=True), patch(
            "mcp_adobe.mcp_stdio._running_photoshop_path", return_value=custom
        ):
            cfg = photoshop_stdio_config()
        self.assertEqual(cfg.env["PHOTOSHOP_PATH"], custom)

    def test_illustrator_launcher_is_pinned(self) -> None:
        cfg = illustrator_stdio_config()
        self.assertEqual(cfg.args, ("-y", "illustrator-mcp-server@1.10.3"))

    def test_structured_result_is_reused(self) -> None:
        result = SimpleNamespace(is_error=False, structured_content={"ok": True}, content=[])
        self.assertEqual(McpSubprocessToolClient._normalize_result(result), {"ok": True})

    def test_json_text_result_is_decoded(self) -> None:
        payload = {"version": "27.0"}
        result = SimpleNamespace(
            is_error=False,
            structured_content=None,
            content=[Text(json.dumps(payload))],
        )
        self.assertEqual(McpSubprocessToolClient._normalize_result(result), payload)

    def test_plain_text_result_is_preserved(self) -> None:
        result = SimpleNamespace(
            is_error=False,
            structured_content=None,
            content=[Text("connected")],
        )
        self.assertEqual(McpSubprocessToolClient._normalize_result(result), {"text": "connected"})

    def test_tool_error_is_not_hidden(self) -> None:
        result = SimpleNamespace(
            is_error=True,
            structured_content=None,
            content=[Text("no active document")],
        )
        with self.assertRaisesRegex(UpstreamToolError, "no active document"):
            McpSubprocessToolClient._normalize_result(result)


if __name__ == "__main__":
    unittest.main()
