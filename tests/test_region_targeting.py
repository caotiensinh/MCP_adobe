from __future__ import annotations
import unittest
from mcp_adobe.region_targeting import (
    Rect, candidates_in_region, document_rect_from_viewport, resolve_annotation,
)


class RegionTargetingTests(unittest.TestCase):
    def setUp(self):
        self.stroke = {"left": 210, "top": 120, "right": 310, "bottom": 220}
        self.viewport = {"left": 10, "top": 20, "scale": 2}
        self.document = {"width": 600, "height": 400}

    def test_scale_and_offset(self):
        region = document_rect_from_viewport(stroke=self.stroke, viewport=self.viewport, document=self.document)
        self.assertEqual(region, Rect(100, 50, 150, 100))

    def test_outside_selection_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside document"):
            document_rect_from_viewport(
                stroke={**self.stroke, "right": 2010}, viewport=self.viewport, document=self.document
            )

    def test_rotated_viewport_rejected(self):
        with self.assertRaisesRegex(ValueError, "rotated"):
            document_rect_from_viewport(
                stroke=self.stroke, viewport={**self.viewport, "rotation": 30}, document=self.document
            )

    def test_disambiguates_overlapping_layers(self):
        layers = [
            {"id": 4, "name": "Headline", "bounds": {"left": 105, "top": 60, "right": 145, "bottom": 95}},
            {"id": 5, "name": "Shape", "bounds": {"left": 100, "top": 50, "right": 150, "bottom": 100}},
        ]
        result = resolve_annotation(
            stroke=self.stroke, viewport=self.viewport, document=self.document, layers=layers,
            document_identity="doc-A", expected_document_identity="doc-A",
        )
        self.assertEqual(result["status"], "ambiguous")
        self.assertTrue(result["requires_confirmation"])
        self.assertEqual([x["layer_id"] for x in result["candidates"]], [5, 4])

    def test_rejects_stale_document(self):
        with self.assertRaisesRegex(ValueError, "document changed"):
            resolve_annotation(
                stroke=self.stroke, viewport=self.viewport, document=self.document, layers=[],
                document_identity="doc-new", expected_document_identity="doc-old",
            )

    def test_filters_hidden_locked_background(self):
        bounds = {"left": 100, "top": 50, "right": 150, "bottom": 100}
        layers = [{"id": 1, "bounds": bounds, "visible": False}, {"id": 2, "bounds": bounds, "locked": True},
                  {"id": 3, "bounds": bounds, "background": True}, {"id": 4, "name": "Good", "bounds": bounds}]
        found = candidates_in_region(Rect(100, 50, 150, 100), layers)
        self.assertEqual([x["layer_id"] for x in found], [4])

    def test_no_candidate_is_not_a_write(self):
        result = resolve_annotation(
            stroke=self.stroke, viewport=self.viewport, document=self.document, layers=[],
            document_identity="doc-A", expected_document_identity="doc-A",
        )
        self.assertEqual(result["status"], "no_candidate")
        self.assertTrue(result["requires_confirmation"])


if __name__ == "__main__":
    unittest.main()
