"""One bounded live XD rectangle creation on the isolated disposable file.
No retry if a receipt exists. Does not edit the protected Panda originals."""
from __future__ import annotations
import asyncio, hashlib, json, os, subprocess
from pathlib import Path
from mcp import Client
from export_region_metadata import payload, unwrap

ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
ORIGINAL=ROOT/"MCP_Mode1_Panda_XD_38136531800.xd"
PANDA=ROOT/"mode2-isolated"/"Panda_Mode2_Editable_Experiment.xd"
TEST=ROOT/"mode2-disposable-native"/"Mode2_Undo_E2E_38584984023.xd"
RECEIPT=ROOT/"mode2-disposable-native"/"mode2_fill_rect_guid_receipt.json"
BASELINE="3a10e1510abc41eccd4485d6f852ea6ced7acc2cf50109e7c1bd123353589ed1"
DOC="98d6635b-3767-4254-b200-ec8442b69ad2"
NAME="MODE2_DISPOSABLE_FILL_RECT_GUID_E2E"
TARGET={"left":820,"top":500,"right":856,"bottom":528}

def validate_native():
    for p in (ORIGINAL,PANDA,TEST):
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=BASELINE:
            raise RuntimeError("MODE2_FILL_FIXTURE_NATIVE_HASH_CHANGED")

def matches(graph):
    result=[]
    def visit(nodes):
        for n in nodes:
            if n.get("name")==NAME:result.append(n)
            visit(n.get("children",[]))
    visit(graph.get("nodes",[]))
    return result

async def main():
    validate_native()
    if RECEIPT.exists():raise RuntimeError("MODE2_FILL_FIXTURE_RECEIPT_EXISTS_NO_REPLAY")
    async with Client("http://127.0.0.1:8787/mcp") as client:
        async def call(tool,cap,args=None):
            r=await asyncio.wait_for(client.call_tool(tool,{
                "application":"xd","capability":cap,"arguments":args or {}
            }),timeout=16)
            o=payload(r)
            if not isinstance(o,dict) or o.get("ok") is False:
                raise RuntimeError("MODE2_MCP_UNVERIFIED_"+cap)
            if isinstance(o.get("result"),dict):o=o["result"]
            o=unwrap(o)
            if not isinstance(o,dict):raise RuntimeError("MODE2_INVALID_MCP_PAYLOAD_"+cap)
            return o
        health=await call("creative_read","creative.health")
        graph=await call("creative_read","creative.scenegraph.list")
        selection=await call("creative_read","creative.selection.get")
        if (health.get("bridge_build")!="xd-ellipse-radius-geometry-v4" or
            health.get("pending_count")!=0 or
            graph.get("complete") is not True or graph.get("document_id")!=DOC or
            graph.get("node_count")!=33 or matches(graph) or
            len(selection.get("items",[]))!=1):
            raise RuntimeError("MODE2_FILL_FIXTURE_PRECONDITIONS_NOT_MET")
        print("MODE2_FILL_FIXTURE_PREWRITE=PASS",flush=True)
        receipt={"state":"intent","document_id":DOC,"name":NAME,"requested_bounds":TARGET}
        RECEIPT.write_text(json.dumps(receipt,indent=2),encoding="utf-8")
        # A call timeout is outcome-UNKNOWN. Never resend.
        queued=await call("creative_write","creative.shape.rectangle",{
            "name":NAME,"x":TARGET["left"],"y":TARGET["top"],
            "width":TARGET["right"]-TARGET["left"],
            "height":TARGET["bottom"]-TARGET["top"],
            "fill":"#445566"
        })
        op=queued.get("operation_id")
        if not op or queued.get("status")!="queued" or queued.get("pending_count")!=1:
            raise RuntimeError("MODE2_FILL_FIXTURE_QUEUE_UNKNOWN_NO_RETRY")
        receipt["state"]="queued"
        receipt["operation_id"]=op
        RECEIPT.write_text(json.dumps(receipt,indent=2),encoding="utf-8")
        print("MODE2_FILL_FIXTURE_QUEUED_ONCE="+str(op),flush=True)
        helper=Path(__file__).with_name("mode2_disposable_apply_once.ps1")
        subprocess.run(["powershell","-NoProfile","-NonInteractive",
            "-ExecutionPolicy","Bypass","-File",str(helper)],
            timeout=25,check=True)
        status={}
        for _ in range(24):
            status=await call("creative_read","xd.queue.status",{"operation_id":op})
            if status.get("status")!="queued":break
            await asyncio.sleep(.35)
        if status.get("status")!="applied":
            raise RuntimeError("MODE2_FILL_FIXTURE_APPLY_UNVERIFIED_NO_RETRY")
        after=await call("creative_read","creative.scenegraph.list")
        found=matches(after)
        if (after.get("complete") is not True or
            after.get("document_id")!=DOC or
            after.get("node_count")!=34 or len(found)!=1):
            raise RuntimeError("MODE2_FILL_FIXTURE_SCENE_NOT_PLUS_ONE")
        node=found[0]
        if node.get("type")!="Rectangle" or node.get("locked") is True or node.get("visible") is not True:
            raise RuntimeError("MODE2_FILL_FIXTURE_INVALID_NATIVE_NODE")
        actual=node.get("bounds")
        if not isinstance(actual,dict) or any(abs(actual.get(k,float("inf"))-v)>2 for k,v in TARGET.items()):
            raise RuntimeError("MODE2_FILL_FIXTURE_BAD_GLOBAL_BOUNDS")
        if not isinstance(node.get("id"),str) or len(node["id"])!=36:
            raise RuntimeError("MODE2_FILL_FIXTURE_UNVERIFIED_NATIVE_GUID")
        receipt.update(state="applied",node_id=node["id"],actual_bounds=actual)
        RECEIPT.write_text(json.dumps(receipt,indent=2),encoding="utf-8")
        validate_native()
        print("MODE2_FILL_FIXTURE_APPLIED_GUID="+node["id"],flush=True)
        print("MODE2_FILL_FIXTURE_CREATE_READBACK=PASS nodes=34",flush=True)
        print("MODE2_PROTECTED_AND_TEST_ON_DISK_UNCHANGED=PASS",flush=True)
        print("MODE2_FILL_UNDO_STILL_REQUIRED=True",flush=True)

if __name__=="__main__":
    asyncio.run(main())
