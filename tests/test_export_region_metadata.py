from __future__ import annotations

import unittest
from scripts.export_region_metadata import normalize_snapshot


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


if __name__ == "__main__":
    unittest.main()
