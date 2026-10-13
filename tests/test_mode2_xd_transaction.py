from __future__ import annotations
import copy
import unittest

from mcp_adobe.mode2_edit_guard import fingerprint
from mcp_adobe.mode2_xd_transaction import execute_guarded_xd_edit


class MockXD:
    def __init__(self):
        self.node={"id":"node-1","bounds":{"left":10,"top":10,"right":30,"bottom":30},"visible":True,"locked":False,"fill":"#000000"}
        self.original=copy.deepcopy(self.node)
        self.edits=0
    def read_document(self):
        return {"document_identity":"doc","generation":3,"preview_sha256":"a"*64,
                "isolated_copy":True,"native_path":"copy.xd"}
    def read_layer(self, node_id):
        return copy.deepcopy(self.node)
    def edit_layer(self, node_id, operation, *, expected_generation):
        self.edits+=1
        self.node["fill"]=operation["parameters"]["color"]
    def undo(self):
        self.node=copy.deepcopy(self.original)
    def save_native(self): pass
    def read_native_sha256(self): return "b"*64


class XDTransactionTests(unittest.TestCase):
    def setUp(self):
        self.proposal={"schema":"mcp-adobe-mode2-guarded-edit/v1","application":"xd",
          "document_identity":"doc","generation":3,"preview_sha256":"a"*64,
          "baseline_native_sha256":"b"*64,"node_id":"node-1",
          "node_bounds":{"left":10,"top":10,"right":30,"bottom":30},
          "operation":{"kind":"set_fill","parameters":{"color":"#D73034"}},
          "execute_automatically":False}
        self.proposal["proposal_sha256"]=fingerprint(self.proposal)
        self.copy={"is_copy":True,"origin_readonly":True,"native_sha256":"b"*64,"path":"copy.xd"}
    def run_it(self, mock=None, **kw):
        mock=mock or MockXD()
        return execute_guarded_xd_edit(proposal=self.proposal,gateway=mock,isolated_copy=self.copy,**kw)
    def test_dry_run_never_calls_gateway(self):
        result=self.run_it(gateway=None) if False else execute_guarded_xd_edit(proposal=self.proposal,gateway=object(),isolated_copy=self.copy)
        self.assertEqual(result["status"],"dry_run")
    def test_verified_round_trip_with_mock_host(self):
        mock=MockXD()
        result=self.run_it(mock,allow_live_mutation=True)
        self.assertEqual(result["status"],"verified_undo")
        self.assertEqual(mock.edits,1)
        self.assertEqual(result["node_before_sha256"],result["node_undo_sha256"])
    def test_no_mutation_without_verified_copy_or_undo_api(self):
        mock=MockXD()
        with self.assertRaisesRegex(ValueError,"isolated test copy"):
            execute_guarded_xd_edit(proposal=self.proposal,gateway=mock,isolated_copy={"is_copy":False},allow_live_mutation=True)
        self.assertEqual(mock.edits,0)
        with self.assertRaisesRegex(ValueError,"lacks verified"):
            execute_guarded_xd_edit(proposal=self.proposal,gateway=object(),isolated_copy=self.copy,allow_live_mutation=True)
    def test_unknown_mutation_is_never_replayed(self):
        class Broken(MockXD):
            def undo(self): pass
        mock=Broken()
        with self.assertRaisesRegex(RuntimeError,"outcome uncertain"):
            self.run_it(mock,allow_live_mutation=True)
        self.assertEqual(mock.edits,1)
    def test_tampering_refused(self):
        changed={**self.proposal,"node_id":"another"}
        with self.assertRaisesRegex(ValueError,"tampered"):
            execute_guarded_xd_edit(proposal=changed,gateway=MockXD(),isolated_copy=self.copy,allow_live_mutation=True)


if __name__=="__main__": unittest.main()
