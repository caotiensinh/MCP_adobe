from __future__ import annotations
import unittest
from scripts.capture_bound_region_pair import compare_snapshots,stable_fingerprint


def snapshot():
    return {"application":"photoshop","document_identity":"doc-1","width":900,"height":600,
            "layers":[{"id":5,"name":"Title","bounds":{"left":10,"top":10,"right":200,"bottom":80}}]}


class PreviewPairTests(unittest.TestCase):
    def test_identical_metadata_stable(self):
        a=snapshot()
        self.assertEqual(compare_snapshots(a,dict(a)),stable_fingerprint(a))

    def test_changed_document_is_rejected(self):
        a=snapshot(); b=snapshot(); b["document_identity"]="doc-2"
        with self.assertRaisesRegex(ValueError,"changed"):
            compare_snapshots(a,b)

    def test_layer_bounds_change_is_rejected(self):
        import copy
        a=snapshot(); b=copy.deepcopy(a)
        b["layers"][0]["bounds"]["right"]=250
        with self.assertRaisesRegex(ValueError,"changed"):
            compare_snapshots(a,b)


if __name__=="__main__":
    unittest.main()
