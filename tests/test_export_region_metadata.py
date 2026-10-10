from __future__ import annotations

import unittest
from scripts.export_region_metadata import normalize_snapshot, normalize_xd_canvas_snapshot


class LiveMetadataNormalizationTests(unittest.TestCase):
    def test_normalizes_document_and_layer_bounds(self):
        data = normalize_snapshot(
            {"hasDocument": True, "document": {"id": 42, "width": 900, "height": 600}},
            {"layers": [{"id": 7, "name": "Title", "bounds": {
                "left": 10, "top": 20, "right": 300, "bottom": 80
            }}]},
        )
        self.assertEqual(data["document_identity"], "42")
        self.assertEqual(data["layers"][0]["bounds"]["right"], 300)

    def test_no_stable_document_identity_fails(self):
        with self.assertRaisesRegex(ValueError, "Document ID"):
            normalize_snapshot(
                {"hasDocument": True, "document": {"width": 900, "height": 600}},
                {"layers": [{"id": 1, "bounds": {
                    "left": 0, "top": 0, "right": 100, "bottom": 100
                }}]},
            )

    def test_no_bound_layers_fails_safely(self):
        with self.assertRaisesRegex(ValueError, "No layers"):
            normalize_snapshot(
                {"document": {"id": "doc-1", "width": 900, "height": 600}},
                {"layers": [{"id": 1, "name": "unknown size"}]},
            )

    def test_no_document_fails(self):
        with self.assertRaisesRegex(ValueError, "No active"):
            normalize_snapshot({"hasDocument": False}, {"layers": []})

    def test_illustrator_layer_list_supported(self):
        result = normalize_snapshot(
            {"document": {"id": "ai-doc", "width": 1200, "height": 800}},
            {"layers": [{"id": 3, "name": "Logo", "bounds": {"left": 2, "top": 3, "right": 90, "bottom": 80}}]},
            application="illustrator",
        )
        self.assertEqual(result["application"], "illustrator")
        self.assertEqual(result["layers"][0]["id"], 3)

    def test_xd_selected_object_supported(self):
        result = normalize_snapshot(
            {"document": {"id": "xd-doc", "width": 600, "height": 400}},
            {"selection": [{"id": "node-2", "name": "CTA", "bounds": {"left": 25, "top": 30, "right": 150, "bottom": 90}}]},
            application="xd",
        )
        self.assertEqual(result["application"], "xd")
        self.assertEqual(result["layers"][0]["id"], "node-2")

    def test_xd_no_selection_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "No layers"):
            normalize_snapshot(
                {"document": {"id": "xd-doc", "width": 600, "height": 400}},
                {"selection": []}, application="xd",
            )

    def test_unknown_application_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            normalize_snapshot({}, {}, application="premiere")

    def test_xd_complete_scenegraph_export(self):
        result = normalize_snapshot(
            {"document": {"id": "xd-scene", "width": 500, "height": 400}},
            {"document_id": "xd-scene", "complete": True, "nodes": [
                {"id": "rect1", "name": "Button", "bounds": {
                    "left": 10, "top": 10, "right": 120, "bottom": 60
                }}
            ]},
            application="xd",
        )
        self.assertEqual([x["id"] for x in result["layers"]], ["rect1"])

    def test_xd_scenegraph_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "mismatch"):
            normalize_snapshot(
                {"document": {"id": "current", "width": 500, "height": 400}},
                {"document_id": "stale", "complete": True, "nodes": []},
                application="xd",
            )

    def test_xd_global_bounds_rebased_to_artboard_frame(self):
        value = normalize_xd_canvas_snapshot(
            {"document_id": "xd-1", "complete": True, "nodes": [
                {"id": "node-1", "name": "Button", "bounds": {
                    "left": -80, "top": 70, "right": 20, "bottom": 120
                }}
            ]},
            {"document_id": "xd-1", "left": -100, "top": 50,
             "width": 400, "height": 300},
        )
        self.assertEqual(value["width"], 400)
        self.assertEqual(value["layers"][0]["bounds"],
                         {"left": 20.0, "top": 20.0, "right": 120.0, "bottom": 70.0})

    def test_xd_frame_document_mismatch_blocks(self):
        with self.assertRaisesRegex(ValueError, "mismatch"):
            normalize_xd_canvas_snapshot(
                {"document_id": "old", "complete": True, "nodes": []},
                {"document_id": "new", "left": 0, "top": 0, "width": 100, "height": 100},
            )


if __name__ == "__main__":
    unittest.main()
