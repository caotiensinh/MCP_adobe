from __future__ import annotations
import unittest

from mcp_adobe.xd_scenegraph_targeting import flatten_scenegraph, normalize_xd_scenegraph
from mcp_adobe.region_targeting import Rect, candidates_in_region


def node(id, bounds=None, **extra):
    return {"id": id, "bounds": bounds or {"left": 20, "top": 30, "right": 200, "bottom": 130}, **extra}


class XdScenegraphTests(unittest.TestCase):
    def test_nested_nodes_region_hit_without_preselection(self):
        snap = {"document_id": "xd1", "complete": True, "nodes": [
            node("artboard", {"left": 0, "top": 0, "right": 500, "bottom": 400},
                 children=[node("label", {"left": 30, "top": 40, "right": 180, "bottom": 90})])
        ]}
        data = normalize_xd_scenegraph({"id": "xd1", "width": 500, "height": 400}, snap)
        self.assertEqual(data["application"], "xd")
        self.assertEqual([x["id"] for x in data["layers"]], ["artboard", "label"])
        hits = candidates_in_region(Rect(40, 45, 120, 75), data["layers"])
        self.assertIn("label", [h["layer_id"] for h in hits])

    def test_selection_only_snapshot_is_not_scenegraph(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            flatten_scenegraph({"nodes": [node("only-selected")]})

    def test_document_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "mismatch"):
            normalize_xd_scenegraph({"id": "doc2", "width": 500, "height": 400},
                                    {"complete": True, "document_id": "doc1", "nodes": [node("1")]})

    def test_duplicate_node_ids_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            flatten_scenegraph({"complete": True, "nodes": [node("1"), node("1")]})

    def test_hidden_and_locked_not_selectable(self):
        result = flatten_scenegraph({"complete": True, "nodes": [
            node("hidden", visible=False), node("locked", locked=True), node("visible")]})
        self.assertEqual([x["id"] for x in result], ["visible"])

    def test_parent_without_bounds_keeps_children(self):
        result = flatten_scenegraph({"complete": True, "nodes": [
            {"id": "group", "children": [node("child")]}]})
        self.assertEqual([x["id"] for x in result], ["child"])

    def test_invalid_leaf_bounds_rejected(self):
        with self.assertRaises(ValueError):
            flatten_scenegraph({"complete": True, "nodes": [{"id": "bad"}]})

    def test_node_count_limit(self):
        with self.assertRaisesRegex(ValueError, "limit"):
            flatten_scenegraph({"complete": True, "nodes": [node("a"), node("b")]}, max_nodes=1)

    def test_xd_adapter_scenegraph_is_read_only(self):
        from mcp_adobe import XdAdapter
        class FakeClient:
            connected = True
            def call_tool(self, name, args):
                if name != "xd.scenegraph.snapshot":
                    raise AssertionError(name)
                return {"document_id": "test", "complete": True, "nodes": []}
        adapter = XdAdapter(FakeClient())
        self.assertIn("creative.scenegraph.list", adapter.info().common_capabilities)
        result = adapter.execute("creative.scenegraph.list", {})
        self.assertEqual(result["outcome"], "read")
        self.assertEqual(result["bridge_method"], "xd.scenegraph.snapshot")


if __name__ == "__main__":
    unittest.main()
