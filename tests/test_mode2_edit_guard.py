from __future__ import annotations

import copy
import unittest
from mcp_adobe.mode2_edit_guard import authorize_edit_plan


class GuardedMode2Tests(unittest.TestCase):
    def setUp(self):
        self.bounds = {"left": 1, "top": 2, "right": 21, "bottom": 22}
        self.selection = {
            "execute_automatically": False, "status": "ambiguous",
            "application": "xd", "document_identity": "doc-1", "generation": 7,
            "preview_sha256": "a" * 64,
            "candidates": [
                {"layer_id": "n-1", "layer_bounds": self.bounds},
                {"layer_id": "n-2", "layer_bounds": self.bounds},
            ],
        }
        self.document = {
            "application": "xd", "document_identity": "doc-1", "generation": 7,
            "preview_sha256": "a" * 64, "saved_native_sha256": "b" * 64,
        }
        self.layer = {"id": "n-1", "bounds": self.bounds,
                      "visible": True, "locked": False, "background": False}
        self.kw = dict(selection=self.selection, confirmed_layer_id="n-1",
                       live_document=self.document, live_layer=self.layer,
                       operation={"kind": "set_fill", "parameters": {"color": "#D73034"}},
                       preview_verified=True, user_confirmed=True)

    def test_ambiguity_must_have_explicit_node_confirmation(self):
        p = authorize_edit_plan(**self.kw)
        self.assertEqual(p["node_id"], "n-1")
        self.assertEqual(p["operation"]["parameters"]["color"], "#D73034")
        self.assertFalse(p["execute_automatically"])
        self.assertEqual(len(p["proposal_sha256"]), 64)
        with self.assertRaisesRegex(ValueError, "not unique"):
            authorize_edit_plan(**{**self.kw, "confirmed_layer_id": "noncandidate"})
        with self.assertRaisesRegex(ValueError, "not unique"):
            duplicated = {**self.selection, "candidates": self.selection["candidates"] + [self.selection["candidates"][0]]}
            authorize_edit_plan(**{**self.kw, "selection": duplicated})

    def test_stale_document_and_layer_rejected(self):
        for key, v in (("generation", 8), ("document_identity", "doc-2"),
                       ("preview_sha256", "c" * 64)):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "stale document"):
                authorize_edit_plan(**{**self.kw, "live_document": {**self.document, key: v}})
        with self.assertRaisesRegex(ValueError, "bounds changed"):
            authorize_edit_plan(**{**self.kw, "live_layer": {**self.layer, "bounds": {**self.bounds, "right": 30}}})

    def test_no_permission_no_writes(self):
        for key in ("preview_verified", "user_confirmed"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "confirmation"):
                authorize_edit_plan(**{**self.kw, key: False})
        with self.assertRaisesRegex(ValueError, "untrusted executable"):
            authorize_edit_plan(**{**self.kw, "selection": {**self.selection, "execute_automatically": True}})
        for k, value in (("visible", False), ("locked", True), ("background", True)):
            with self.subTest(k=k), self.assertRaisesRegex(ValueError, "not editable"):
                authorize_edit_plan(**{**self.kw, "live_layer": {**self.layer, k: value}})

    def test_reject_unknown_or_invalid_operations(self):
        for operation in (
            {"kind": "delete_layer", "parameters": {"id": "n-1"}},
            {"kind": "set_fill", "parameters": {"color": "red"}},
            {"kind": "set_opacity", "parameters": {"opacity": float("nan")}},
            {"kind": "translate", "parameters": {"dx": 9000, "dy": 0}},
        ):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                authorize_edit_plan(**{**self.kw, "operation": operation})


if __name__ == "__main__":
    unittest.main()
