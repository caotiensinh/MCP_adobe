"""Regressions for the exact Illustrator health state that blocked live rectangle E2E.

Non-probing health intentionally has document.status=unknown even with an idle
CEP panel. Never treat that value as user content, and never treat it as
permission to CREATE until trusted probe returns none_open.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "scripts" / "adobe_ai_one_rectangle_measured_once.py"


def load_contract():
    fake = types.ModuleType("mcp")
    fake.Client = type("FakeClient", (), {})
    spec = importlib.util.spec_from_file_location("adobe_ai_preflight_contract_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        os.environ,
        {
            "USERPROFILE": tmp,
            "RUNNER_TEMP": tmp,
            "GITHUB_RUN_ID": "unit-test-preflight",
        },
    ), patch.dict(sys.modules, {"mcp": fake}):
        spec.loader.exec_module(module)
    return module


class IllustratorReadinessContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = load_contract()

    def state(self, *, doc="unknown", panel="ok", busy=False,
              unresolved=None, blocking=None, stale=False):
        return {
            "connection": {
                "data": {
                    "blockedAt": "document" if doc == "unknown" else None,
                    "blocking": blocking,
                    "execution": {
                        "unresolvedJobs": unresolved or [],
                        "activeJob": None,
                        "waiting": 0,
                    },
                    "layers": {
                        "panel": {
                            "status": panel,
                            "busy": busy,
                            "activeRequestId": None,
                            "heartbeatStale": stale,
                        },
                        "document": {"status": doc},
                    },
                },
            },
        }

    def test_nonprobing_unknown_document_is_safe_for_read_only_gate(self):
        self.contract.require_host_idle(self.state(), allow_no_doc=False)

    def test_nonprobing_unknown_is_not_permission_to_create_document(self):
        with self.assertRaisesRegex(RuntimeError, "FOREIGN_OR_UNSAVED_DOCUMENT"):
            self.contract.require_host_idle(self.state(), allow_no_doc=True)

    def test_verified_none_open_may_pass_final_document_gate(self):
        self.contract.require_host_idle(self.state(doc="none_open"), allow_no_doc=True)

    def test_existing_document_blocks_document_create(self):
        with self.assertRaisesRegex(RuntimeError, "FOREIGN_OR_UNSAVED_DOCUMENT"):
            self.contract.require_host_idle(self.state(doc="open"), allow_no_doc=True)

    def test_unknown_job_blocks_even_nonprobing_health(self):
        with self.assertRaisesRegex(RuntimeError, "FENCED_OR_BUSY"):
            self.contract.require_host_idle(
                self.state(unresolved=["job_625f841b04cb"]), allow_no_doc=False)

    def test_busy_panel_blocks(self):
        with self.assertRaisesRegex(RuntimeError, "PANEL_NOT_IDLE"):
            self.contract.require_host_idle(self.state(busy=True), allow_no_doc=False)

    def test_explicit_probe_fence_blocks(self):
        with self.assertRaisesRegex(RuntimeError, "BLOCKING_FENCE"):
            self.contract.require_host_idle(
                self.state(doc="none_open", blocking={"reason": "C014"}), allow_no_doc=True)


if __name__ == "__main__":
    unittest.main()
