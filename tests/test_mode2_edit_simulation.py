from __future__ import annotations
import copy
import unittest
from mcp_adobe.mode2_edit_guard import authorize_edit_plan
from mcp_adobe.mode2_edit_simulation import simulate_reversible_edit


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.bounds={"left":10,"top":20,"right":30,"bottom":40}
        self.layer={"id":"node-1","bounds":dict(self.bounds),"visible":True,"locked":False,"background":False,"fill":"#000000"}
        self.doc={"application":"xd","document_identity":"test-document","generation":2,"preview_sha256":"a"*64,"saved_native_sha256":"b"*64}
        self.selection={**{k:self.doc[k] for k in ("application","document_identity","generation","preview_sha256")},"status":"ambiguous","execute_automatically":False,"candidates":[{"layer_id":"node-1","layer_bounds":dict(self.bounds)},{"layer_id":"node-2","layer_bounds":dict(self.bounds)}]}

    def proposal(self,op=None):
        return authorize_edit_plan(selection=self.selection,confirmed_layer_id="node-1",live_document=self.doc,live_layer=self.layer,operation=op or {"kind":"set_fill","parameters":{"color":"#D73034"}},preview_verified=True,user_confirmed=True)

    def test_round_trip_without_host_write(self):
        original=copy.deepcopy(self.layer)
        result=simulate_reversible_edit(proposal=self.proposal(),current_document=self.doc,current_layer=self.layer)
        self.assertTrue(result["simulation_passed"])
        self.assertEqual(result["before_sha256"],result["undo_sha256"])
        self.assertNotEqual(result["before_sha256"],result["after_sha256"])
        self.assertEqual(result["changed_node"]["fill"],"#D73034")
        self.assertEqual(self.layer,original)
        self.assertFalse(result["native_file_written"])
        self.assertFalse(result["host_readback_verified"])

    def test_stale_document_and_tampered_plan(self):
        p=self.proposal()
        with self.assertRaisesRegex(ValueError,"changed document"):
            simulate_reversible_edit(proposal=p,current_document={**self.doc,"generation":3},current_layer=self.layer)
        with self.assertRaisesRegex(ValueError,"digest mismatch"):
            simulate_reversible_edit(proposal={**p,"node_id":"other"},current_document=self.doc,current_layer=self.layer)
        with self.assertRaisesRegex(ValueError,"bounds changed"):
            simulate_reversible_edit(proposal=p,current_document=self.doc,current_layer={**self.layer,"bounds":{**self.bounds,"right":40}})

    def test_move_and_opacity_and_nonfinite_refused(self):
        for op in ({"kind":"translate","parameters":{"dx":5,"dy":-3}},{"kind":"set_opacity","parameters":{"opacity":0.5}}):
            result=simulate_reversible_edit(proposal=self.proposal(op),current_document=self.doc,current_layer=self.layer)
            self.assertEqual(result["before_sha256"],result["undo_sha256"])
        for op in ({"kind":"set_opacity","parameters":{"opacity":float("nan")}},{"kind":"translate","parameters":{"dx":float("inf"),"dy":0}}):
            with self.assertRaises(ValueError):
                self.proposal(op)


if __name__ == "__main__":
    unittest.main()
