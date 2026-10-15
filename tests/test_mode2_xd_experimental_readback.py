from __future__ import annotations

import copy
import unittest

from scripts.mode2_xd_experimental_readback import find_selected_node


DOC = "98d6635b-3767-4254-b200-ec8442b69ad2"
GUID = "130fdb64-c691-4374-ab46-66fd3f9e077c"
BOUNDS = {"left": 484, "top": 166, "right": 584, "bottom": 280}
NODE = {"id": GUID, "name": "Panda Right Ear", "bounds": BOUNDS,
        "visible": True, "locked": False, "children": []}
GRAPH = {"document_id": DOC, "complete": True, "nodes": [NODE]}
SELECTION = {"items": [{"guid": GUID}]}


class Mode2ExperimentalReadbackTests(unittest.TestCase):
    def test_unique_live_target_matches_scenegraph(self):
        result = find_selected_node(GRAPH, SELECTION)
        self.assertEqual(result, {"document_id": DOC, "node_id": GUID, "bounds": BOUNDS})

    def test_reject_missing_duplicate_or_incomplete(self):
        cases = [
            (GRAPH, {"items": []}),
            (GRAPH, {"items": [{"guid": GUID}, {"guid": GUID}]}),
            (GRAPH, {"items": [{"guid": "stale"}]}),
            ({**GRAPH, "complete": False}, SELECTION),
            ({**GRAPH, "nodes": [NODE, NODE]}, SELECTION),
            ({**GRAPH, "nodes": [{"id": "other", "children": [NODE, NODE]}]}, SELECTION),
        ]
        for graph, selection in cases:
            with self.subTest(graph=graph, selection=selection), self.assertRaises(ValueError):
                find_selected_node(graph, selection)

    def test_reject_hidden_locked_bad_bounds(self):
        for change in (
            {"visible": False}, {"locked": True}, {"bounds": None},
            {"bounds": {**BOUNDS, "right": BOUNDS["left"]}},
            {"bounds": {**BOUNDS, "left": float("nan")}},
            {"bounds": {**BOUNDS, "left": True}},
        ):
            graph = copy.deepcopy(GRAPH)
            graph["nodes"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                find_selected_node(graph, SELECTION)


if __name__ == "__main__":
    unittest.main()
