from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from mcp_adobe.illustrator import IllustratorAdapter
from mcp_adobe.photoshop import PhotoshopAdapter
from mcp_adobe.verification import capture_file_snapshot, evaluate_file_snapshot
from mcp_adobe.xd import XdAdapter


class FileWritingClient:
    def __init__(self, *, create_output: bool = True) -> None:
        self.create_output = create_output
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @property
    def connected(self) -> bool:
        return True

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        args = dict(arguments)
        self.calls.append((name, args))
        if self.create_output:
            raw_path = args.get("path") or args.get("output_path")
            if isinstance(raw_path, str) and raw_path:
                path = Path(raw_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"verified-output")
        return {"tool": name, "arguments": args}


class XdQueueClient:
    @property
    def connected(self) -> bool:
        return True

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        if name.startswith("xd.queue.") and name != "xd.queue.status":
            return {
                "status": "queued",
                "approval_required": True,
                "operation_id": "xd-op-42",
            }
        return {"status": "ok"}


class OperationOutcomeTests(unittest.TestCase):
    def test_new_file_becomes_verified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.png"
            snapshot = capture_file_snapshot({"path": str(path)})
            path.write_bytes(b"abc")
            outcome, verification = evaluate_file_snapshot(snapshot)
            self.assertEqual(outcome, "verified")
            self.assertEqual(verification["evidence"], "file-created")
            self.assertEqual(verification["bytes"], 3)

    def test_preexisting_unchanged_file_is_not_fake_verified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "existing.ai"
            path.write_bytes(b"same")
            snapshot = capture_file_snapshot({"path": str(path)})
            outcome, verification = evaluate_file_snapshot(snapshot)
            self.assertEqual(outcome, "accepted_unverified")
            self.assertEqual(verification["reason"], "preexisting-file-unchanged")

    def test_photoshop_export_verifies_created_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "photoshop.png"
            result = PhotoshopAdapter(FileWritingClient()).execute(
                "creative.document.export",
                {"path": str(path), "format": "PNG"},
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["outcome"], "verified")
            self.assertEqual(result["verification"]["evidence"], "file-created")

    def test_illustrator_export_verifies_created_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "illustrator.png"
            result = IllustratorAdapter(FileWritingClient()).execute(
                "creative.document.export",
                {"path": str(path), "format": "png", "target": "artboard:0"},
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["outcome"], "verified")
            self.assertEqual(result["verification"]["evidence"], "file-created")

    def test_missing_file_after_upstream_success_is_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.png"
            result = PhotoshopAdapter(FileWritingClient(create_output=False)).execute(
                "creative.document.export",
                {"path": str(path), "format": "PNG"},
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["outcome"], "accepted_unverified")
            self.assertEqual(result["verification"]["reason"], "output-file-not-observed")

    def test_reversible_write_is_explicitly_unverified(self) -> None:
        result = PhotoshopAdapter(FileWritingClient(create_output=False)).execute(
            "creative.document.create",
            {"width": 100, "height": 100},
        )
        self.assertEqual(result["outcome"], "accepted_unverified")
        self.assertEqual(result["verification"]["reason"], "no-deterministic-postcondition")

    def test_xd_queue_reports_pending_user_approval(self) -> None:
        result = XdAdapter(XdQueueClient()).execute(
            "xd.queue.rectangle_create",
            {"width": 320, "height": 180},
        )
        self.assertEqual(result["outcome"], "pending_user_approval")
        self.assertEqual(result["verification"]["operation_id"], "xd-op-42")

    def test_read_operation_is_not_misreported_as_verified_write(self) -> None:
        result = PhotoshopAdapter(FileWritingClient(create_output=False)).execute(
            "creative.health",
            {},
        )
        self.assertEqual(result["outcome"], "read")
        self.assertEqual(result["verification"]["status"], "not_applicable")


if __name__ == "__main__":
    unittest.main()
