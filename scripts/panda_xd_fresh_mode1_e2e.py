"""Fresh XD Mode 1 E2E after verified loss of old unsaved document.

Each mutation is one MCP write with an explicit UXP Apply action, a receipt,
full live scenegraph readback, and a persisted checkpoint. No bulk import.
"""
import asyncio
import json
import os
from pathlib import Path
from collections.abc import Mapping
from mcp import Client
from panda_xd_mode1_e2e import STEPS, call, apply_one, node_map, find, save_checkpoint
import panda_xd_mode1_e2e as old

RUN=os.environ.get("PANDA_XD_WORK_ID") or os.environ["GITHUB_RUN_ID"]
ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
CHECKPOINT=ROOT/f"MCP_Mode1_Panda_XD_{RUN}.json"
URL="http://127.0.0.1:8787/mcp"
SOURCE=ROOT/"MCP_Mode1_Panda_XD_38136531800.xd"
if not SOURCE.is_file() or SOURCE.stat().st_size<4096:
    raise RuntimeError("XD_SOURCE_NATIVE_ORIGINAL_MISSING_NO_WRITES")
# Checkpoint from prior LOST unsaved document is evidence only, never a source
# from which pixel paths or an already-applied operation is blindly replayed.
PREVIOUS=ROOT/"MCP_Mode1_Panda_XD_38114632173.json"

def persist(data):
    old.CHECKPOINT=CHECKPOINT
    return save_checkpoint(data)

async def checked_read(c,cap,args=None):
    p=await call(c,"creative_read",cap,args or {})
    v=p.get("result")
    if not isinstance(v,Mapping):
        raise RuntimeError("XD_READ_MISSING_VERIFIABLE_RESULT "+cap)
    return v

async def measured(c):
    info=await checked_read(c,"creative.health")
    if info.get("bridge")!="connected":raise RuntimeError("XD_NOT_CONNECTED")
    q=info.get("pending_count")
    if not isinstance(q,int):raise RuntimeError("XD_QUEUE_DEPTH_UNKNOWN")
    snap=await checked_read(c,"creative.scenegraph.list")
    if snap.get("complete") is not True or not snap.get("document_id"):
        raise RuntimeError("XD_INCOMPLETE_SCENEGRAPH")
    return snap,node_map(snap),q

async def receipt(c,op):
    status=await checked_read(c,"xd.queue.status",{"operation_id":op})
    if status.get("status") not in ("queued","applied","failed","rejected"):
        raise RuntimeError("XD_OPERATION_UNKNOWN_STOP "+str(status))
    return status

def verify_snapshot(snap,found,data):
    if snap["document_id"]!=data["document_id"]:
        raise RuntimeError("XD_DOCUMENT_SWITCH_DETECTED")
    expected={p["name"]:p["guid"] for p in data["proven"]}
    if expected!=found:raise RuntimeError("XD_SCENEGRAPH_MISMATCH_NO_NEW_WRITE "+
             json.dumps({"expected":expected,"actual":found}))
    if len(expected)!=len(data["proven"]):
        raise RuntimeError("XD_DUPLICATE_NAME_IN_CHECKPOINT")
    return len(expected)

async def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    if not PREVIOUS.exists():
        raise RuntimeError("XD_PREVIOUS_RUN_EVIDENCE_MISSING_REFUSE_FRESH_REBUILD")
    if len(json.loads(PREVIOUS.read_text(encoding="utf-8")).get("proven",[]))!=5:
        raise RuntimeError("XD_PREVIOUS_CHECKPOINT_NOT_FIVE_STOP")
    async with Client(URL) as c:
        snap,found,depth=await measured(c)
        if CHECKPOINT.exists():
            data=json.loads(CHECKPOINT.read_text(encoding="utf-8"))
            if data.get("run")!=RUN:raise RuntimeError("XD_RESUME_RUN_ID_MISMATCH")
            n=verify_snapshot(snap,found,data)
            print("XD_FRESH_RECONCILE=PASS "+json.dumps({"count":n,"document_id":snap["document_id"]}),flush=True)
        else:
            if depth!=0 or found:
                raise RuntimeError("XD_FRESH_DOCUMENT_NOT_EMPTY_STOP")
            if not snap.get("nodes") or not any(n.get("type")=="Artboard" for n in snap["nodes"]):
                raise RuntimeError("XD_FRESH_DOCUMENT_HAS_NO_REAL_ARTBOARD")
            data={"run":RUN,"document_id":snap["document_id"],"proven":[],
                  "pending":None,"former_lost_document_id":
                  "892cdc9e-115d-4ec9-aa93-a0b75e9c1de0"}
            if data["document_id"]==data["former_lost_document_id"]:
                raise RuntimeError("XD_NOT_A_FRESH_DOCUMENT_RECONCILE_INSTEAD")
            persist(data)
            print("XD_FRESH_REAL_ARTBOARD=PASS "+str(snap["document_id"]),flush=True)

        if len(data["proven"])==32 and data.get("pending") is None:
            print("XD_ALL_SHAPES_ALREADY_VERIFIED_NO_REPLAY",flush=True)
        for i in range(len(data["proven"])+1,len(STEPS)+1):
            name,cap,args=STEPS[i-1]
            snap,found,depth=await measured(c)
            count=verify_snapshot(snap,found,data)
            if count!=i-1:raise RuntimeError("XD_BEFORE_COUNT_WRONG")
            pending=data.get("pending")
            if pending:
                if pending.get("ordinal")!=i or pending.get("name")!=name:
                    raise RuntimeError("XD_PERSISTED_PENDING_BELONGS_TO_DIFFERENT_SHAPE")
                op=pending["operation_id"]
                if depth!=1:raise RuntimeError("XD_PERSISTED_QUEUE_DEPTH_WRONG")
            else:
                if depth!=0:raise RuntimeError("XD_PREEXISTING_QUEUE_NOT_OWNED")
                print("XD_MODE1_STROKE_START="+json.dumps({"ordinal":i,"name":name,
                    "capability":cap,"before":count}),flush=True)
                response=await call(c,"creative_write",cap,args)
                result=response.get("result") or {}
                op=result.get("operation_id")
                if result.get("status")!="queued" or not isinstance(op,str) or result.get("pending_count")!=1:
                    raise RuntimeError("XD_MUTATION_RETURNED_UNKNOWN_DO_NOT_REPLAY")
                data["pending"]={"ordinal":i,"name":name,"operation_id":op}
                persist(data)
            status=await receipt(c,op)
            if status["status"]=="queued":
                apply_one() # real XD UXP Apply keyboard shortcut, exactly once
                for _ in range(22):
                    status=await receipt(c,op)
                    if status["status"]!="queued":break
                    await asyncio.sleep(.35)
            if status["status"]!="applied":
                raise RuntimeError("XD_NOT_APPLIED_STOP_NO_REPLAY "+status["status"])
            snap,after,after_depth=await measured(c)
            if after_depth!=0 or len(after)!=i or name not in after:
                raise RuntimeError("XD_POST_APPLY_NOT_VISIBLE_IN_SCENEGRAPH")
            live_guid=after[name]
            receipt_guid=(status.get("result") or {}).get("guid")
            if receipt_guid and receipt_guid!=live_guid:
                raise RuntimeError("XD_GUID_DIFFERS_BETWEEN_RECEIPT_AND_SCENEGRAPH")
            for prior in data["proven"]:
                if after.get(prior["name"])!=prior["guid"]:
                    raise RuntimeError("XD_PRIOR_SHAPE_CHANGED_UNEXPECTEDLY")
            data["proven"].append({"ordinal":i,"name":name,"guid":live_guid,
                                   "operation_id":op,"status":"applied"})
            data["pending"]=None
            digest=persist(data)
            print("XD_MODE1_STROKE_READBACK="+json.dumps({"ordinal":i,
                "name":name,"nodeCount":len(after),"guid":live_guid,
                "operationStatus":"applied","checkpointSHA256":digest}),flush=True)
            await asyncio.sleep(.3)
        print("XD_MODE1_32_STROKES=PASS",flush=True)
        filename=f"MCP_Mode1_Panda_XD_{RUN}.png"
        exported=await call(c,"creative_write","xd.export.png",{"filename":filename})
        native=find(exported,"nativePath")
        if not isinstance(native,str) or not Path(native).is_file() or Path(native).stat().st_size<1000:
            raise RuntimeError("XD_RENDERED_PNG_FILE_NOT_FOUND")
        import shutil,hashlib
        source_png=Path(native)
        if source_png.read_bytes()[:8]!=b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("XD_NATIVE_PNG_SIGNATURE_INVALID")
        dest_png=ROOT/f"MCP_Mode1_Panda_XD_{RUN}.png"
        if dest_png.exists():
            raise RuntimeError("XD_NATIVE_PNG_CAPTURE_COLLISION_NO_OVERWRITE")
        shutil.copyfile(source_png,dest_png)
        if dest_png.stat().st_size != source_png.stat().st_size:
            raise RuntimeError("XD_NATIVE_PNG_CAPTURE_SIZE_MISMATCH")
        print("XD_NATIVE_PNG_EXPORT=PASS "+json.dumps({
            "application_native":native,"captured":str(dest_png),
            "bytes":dest_png.stat().st_size,
            "sha256":hashlib.sha256(dest_png.read_bytes()).hexdigest()
        }),flush=True)

if __name__=="__main__":
    asyncio.run(main())
