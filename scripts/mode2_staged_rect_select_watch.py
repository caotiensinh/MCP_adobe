"""Real 8766 XD controlled GUID stage -> user menu selection watch, no document edits."""
from __future__ import annotations
import argparse,json,time,os
from pathlib import Path
from mcp_adobe.xd_bridge import XdWebSocketBridgeClient
from mcp_adobe.xd_mode2_experimental import ExperimentalXdMode2Adapter,EXPERIMENTAL_BRIDGE_BUILD
DOC="98d6635b-3767-4254-b200-ec8442b69ad2"
NAME="MODE2_DISPOSABLE_FILL_RECT_GUID_E2E"
ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"/"mode2-disposable-native"
RECEIPT=ROOT/"mode2_fill_rect_guid_receipt.json"

def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.get("children",[]))

def classify_ticket_status(value, guid):
    """Return the only safe next action without changing Adobe XD state.

    Live active tickets are reusable for the same GUID only. Expired tickets
    are evicted lazily by the experimental UXP's read-only stage handler.
    """
    if not isinstance(value, dict):
        raise RuntimeError("MODE2_SELECTION_TICKET_STATUS_UNVERIFIED")
    state = value.get("status")
    if state == "none":
        if value.get("node_id") is not None:
            raise RuntimeError("MODE2_SELECTION_TICKET_NONE_HAS_NODE")
        return "stage_new"
    if state == "expired":
        # Do not reuse an expired one; bridge stage can evict it safely.
        return "stage_new"
    if state == "awaiting_user_menu":
        if (value.get("node_id") != guid or value.get("document_id") != DOC):
            raise RuntimeError("MODE2_SELECTION_TICKET_TARGET_CONFLICT")
        remaining = value.get("expires_in_seconds")
        if type(remaining) is not int or remaining < 25 or remaining > 90:
            raise RuntimeError("MODE2_SELECTION_TICKET_TOO_SHORT_OR_INVALID")
        return "use_existing"
    raise RuntimeError("MODE2_SELECTION_TICKET_UNKNOWN_STATE")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--wait-seconds",type=int,default=85)
    opt=ap.parse_args()
    if opt.wait_seconds<20 or opt.wait_seconds>90:raise ValueError("bad timeout")
    intent=json.loads(RECEIPT.read_text(encoding="utf-8"))
    if (intent.get("state")!="applied" or intent.get("document_id")!=DOC or
        intent.get("name")!=NAME or not isinstance(intent.get("node_id"),str)):
        raise RuntimeError("MODE2_RECT_CREATION_RECEIPT_NOT_ATTESTED")
    guid=intent["node_id"]
    bridge=XdWebSocketBridgeClient(host="127.0.0.1",port=8766,startup_timeout_seconds=7,call_timeout_seconds=12)
    try:
        bridge.start()
        deadline=time.monotonic()+opt.wait_seconds
        while not bridge.connected and time.monotonic()<deadline:time.sleep(.3)
        if not bridge.connected:raise RuntimeError("MODE2_EXPERIMENTAL_PLUGIN_NOT_CONNECTED")
        if bridge.plugin_info.get("bridgeBuild")!=EXPERIMENTAL_BRIDGE_BUILD:raise RuntimeError("MODE2_WRONG_UXP_BUILD")
        h=bridge.call_tool("xd.health",{})
        g=bridge.call_tool("xd.scenegraph.snapshot",{})
        targets=[n for n in walk(g.get("nodes",[])) if n.get("id")==guid or n.get("name")==NAME]
        if (g.get("complete") is not True or g.get("document_id")!=DOC or
            g.get("node_count")!=34 or len(targets)!=1 or
            h.get("pending_count")!=0 or targets[0].get("id")!=guid or
            targets[0].get("type")!="Rectangle" or
            targets[0].get("locked") is True or targets[0].get("visible") is not True):
            raise RuntimeError("MODE2_NEW_RECT_LIVE_SCENE_NOT_ATTESTED")
        node=targets[0]
        bounds=node.get("bounds")
        expected=intent.get("actual_bounds")
        if not isinstance(bounds,dict) or not isinstance(expected,dict) or any(
            abs(bounds[k]-expected[k])>.1 for k in ("left","top","right","bottom")
        ):raise RuntimeError("MODE2_NEW_RECT_RECEIPT_BOUNDS_DIVERGED")
        print("MODE2_NEW_RECT_LIVE_UID="+guid,flush=True)
        prepare={"document_id":DOC,"node_id":guid,"name":NAME,
                 "isolated_test_copy":True,"bounds":bounds}
        status_before=bridge.call_tool("xd.mode2.selection.status",{})
        action=classify_ticket_status(status_before,guid)
        print("MODE2_SELECTION_TICKET_PRECHECK="+str(status_before.get("status"))+
              " ACTION="+action,flush=True)
        if action=="stage_new":
            staged=bridge.call_tool("xd.mode2.selection.stage_disposable",prepare)
            if staged.get("status")!="awaiting_user_menu" or staged.get("node_id")!=guid:
                raise RuntimeError("MODE2_NEW_RECT_STAGE_UNVERIFIED")
        after_stage=bridge.call_tool("xd.mode2.selection.status",{})
        if classify_ticket_status(after_stage,guid)!="use_existing":
            raise RuntimeError("MODE2_NEW_RECT_STAGED_TICKET_NOT_ACTIVE")
        print("MODE2_STAGED_DISPOSABLE_RECT_AWAITING_MENU=PASS",flush=True)
        while time.monotonic()<deadline:
            selected=bridge.call_tool("xd.selection.get",{}).get("items",[])
            if len(selected)==1 and selected[0].get("guid")==guid:
                print("MODE2_NEW_RECT_MENU_SELECTION_GUID="+guid,flush=True)
                break
            if len(selected)>1:raise RuntimeError("MODE2_UNEXPECTED_MULTI_SELECTION")
            time.sleep(.35)
        else:raise RuntimeError("MODE2_EXPLICIT_MENU_SELECTION_NOT_OBSERVED")
        adapter=ExperimentalXdMode2Adapter(bridge,writes_enabled=False)
        result=adapter.execute("xd.mode2.node.inspect",{
            "document_id":DOC,"node_id":guid,"bounds":bounds
        })
        proof=result["result"]
        if (proof.get("node_id")!=guid or proof.get("bounds")!=bounds or
            proof.get("selection_count")!=1):raise RuntimeError("MODE2_NEW_RECT_INSPECT_MISMATCH")
        a=bridge.call_tool("xd.scenegraph.snapshot",{})
        if a.get("node_count")!=34 or a.get("document_id")!=DOC:
            raise RuntimeError("MODE2_SELECTION_MODIFIED_SCENE")
        if bridge.call_tool("xd.health",{}).get("pending_count")!=0:
            raise RuntimeError("MODE2_SELECTION_LEFT_PENDING_QUEUE")
        print("MODE2_NEW_RECT_EXPLICIT_SELECT_AND_INSPECT=PASS",flush=True)
        print("MODE2_NEW_RECT_NO_FILL_ATTEMPTED=True",flush=True)
    finally:bridge.close()
if __name__=="__main__":main()
