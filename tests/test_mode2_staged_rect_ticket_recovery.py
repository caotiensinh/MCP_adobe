"""Bounded selection-ticket decision tests; never contact XD or queue writes."""
from __future__ import annotations
import unittest
from scripts.mode2_staged_rect_select_watch import classify_ticket_status, DOC

GUID="9989e92f-7c9b-4721-9cdc-b5b5ea33cdf2"

class StageTicketTests(unittest.TestCase):
    def test_absent_ticket_can_be_staged(self):
        self.assertEqual(classify_ticket_status({"status":"none","node_id":None},GUID),"stage_new")

    def test_expired_ticket_is_not_reused(self):
        for value in (
            {"status":"expired","node_id":GUID,"document_id":DOC,"expires_in_seconds":0},
            {"status":"expired","node_id":"other","document_id":DOC,"expires_in_seconds":0},
        ):
            with self.subTest(value=value):
                self.assertEqual(classify_ticket_status(value,GUID),"stage_new")

    def test_live_ticket_for_same_guid_reused(self):
        for remaining in (25,35,90):
            with self.subTest(remaining=remaining):
                status={"status":"awaiting_user_menu","document_id":DOC,
                        "node_id":GUID,"expires_in_seconds":remaining}
                self.assertEqual(classify_ticket_status(status,GUID),"use_existing")

    def test_live_other_guid_or_doc_never_replaced(self):
        for value in (
            {"status":"awaiting_user_menu","node_id":"other","document_id":DOC,"expires_in_seconds":90},
            {"status":"awaiting_user_menu","node_id":GUID,"document_id":"other","expires_in_seconds":90},
        ):
            with self.subTest(value=value),self.assertRaisesRegex(RuntimeError,"TARGET_CONFLICT"):
                classify_ticket_status(value,GUID)

    def test_low_remaining_or_invalid_ttl_fails_closed(self):
        for remaining in (0,1,24,91,-1,None,True,"89",22.1):
            with self.subTest(remaining=remaining),self.assertRaisesRegex(RuntimeError,"TOO_SHORT_OR_INVALID"):
                classify_ticket_status({
                    "status":"awaiting_user_menu","node_id":GUID,"document_id":DOC,
                    "expires_in_seconds":remaining
                },GUID)

    def test_unknown_or_ambiguous_fails_closed(self):
        for value in (None,[],{},"none",{"status":"queued"},
                      {"status":"none","node_id":GUID}):
            with self.subTest(value=value),self.assertRaises(RuntimeError):
                classify_ticket_status(value,GUID)

if __name__=="__main__":
    unittest.main()
