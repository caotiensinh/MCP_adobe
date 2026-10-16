"""Adobe XD panda Mode 1: one queued write, one Apply UI command, one receipt + scenegraph readback per shape."""
import asyncio, hashlib, json, os, subprocess, time
from collections.abc import Mapping
from pathlib import Path
from mcp import Client

ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
RUN=os.environ.get("PANDA_XD_RESUME_RUN_ID") or os.environ.get("GITHUB_RUN_ID","local")
CHECKPOINT=ROOT/f"MCP_Mode1_Panda_XD_{RUN}.json"
URL="http://127.0.0.1:8787/mcp"
def rgb(c):return "#%02X%02X%02X"%c
def rect(n,x,y,w,h,c):return (n,"creative.shape.rectangle",{"name":n,"x":x,"y":y,"width":w,"height":h,"fill":rgb(c)})
def oval(n,x,y,w,h,c):return (n,"creative.shape.ellipse",{"name":n,"x":x,"y":y,"width":w,"height":h,"fill":rgb(c)})
S=(242,249,248);G=(164,205,147);K=(39,45,49);W=(247,246,235);B=(74,153,65);H=(220,173,108)
STEPS=[
    rect("01 XD Panda Garden",0,0,880,640,S),
    rect("02 XD Bamboo Meadow",0,568,880,72,G),
    rect("03 XD Bamboo Stalk",590,242,18,302,B),
    rect("04 XD Bamboo Joint 1",584,302,31,8,(51,113,54)),
    rect("05 XD Bamboo Joint 2",584,390,31,8,(51,113,54)),
    oval("06 XD Bamboo Upper Leaf",606,265,61,28,B),
    oval("07 XD Bamboo Middle Leaf",540,350,61,28,B),
    oval("08 XD Panda Left Foot",285,500,120,71,K),
    oval("09 XD Panda Right Foot",480,500,120,71,K),
    oval("10 XD Panda Left Ear",297,166,100,114,K),
    oval("11 XD Panda Right Ear",484,166,100,114,K),
    oval("12 XD Panda Black Body",303,331,275,233,K),
    oval("13 XD Panda White Belly",353,359,185,187,W),
    oval("14 XD Panda Left Arm",258,349,95,154,K),
    oval("15 XD Panda Right Arm",538,341,97,152,K),
    oval("16 XD Panda White Head",320,189,240,218,W),
    oval("17 XD Panda Left Eye Patch",353,250,77,95,K),
    oval("18 XD Panda Right Eye Patch",453,250,77,95,K),
    oval("19 XD Panda Left Eye",389,280,22,27,W),
    oval("20 XD Panda Right Eye",480,280,22,27,W),
    oval("21 XD Panda Nose",423,337,35,24,K),
    oval("22 XD Panda Smile",417,368,46,9,(118,91,89)),
    oval("23 XD Paw Holding Bamboo",563,408,67,66,K),
    oval("24 XD Non La Wide Brim",293,182,297,34,(175,120,69)),
    rect("25 XD Non La Cone Lower",330,159,224,23,H),
    rect("26 XD Non La Cone Middle",361,134,165,25,H),
    rect("27 XD Non La Cone Upper",393,108,99,26,H),
    rect("28 XD Non La Tip",430,77,25,31,H),
    rect("29 XD Non La Highlight",441,105,10,75,(243,205,150)),
    rect("30 XD Non La Chin Strap",372,196,7,153,(157,96,51)),
    oval("31 XD Pink Flower",214,590,20,20,(241,150,174)),
    oval("32 XD Yellow Flower",689,585,20,20,(248,208,92)),
]
def walk(x):
    yield x
    if isinstance(x,Mapping):
        for a in x.values():yield from walk(a)
    elif isinstance(x,(list,tuple)):
        for a in x:yield from walk(a)
def find(x,key):
    for a in walk(x):
        if isinstance(a,Mapping) and key in a:return a[key]
    return None
def node_map(x):
    result={}
    for a in walk(x):
        if isinstance(a,Mapping) and a.get("name") in {t[0] for t in STEPS}:
            guid=a.get("id") or a.get("guid")
            if guid: result[a["name"]]=str(guid)
    return result
def apply_one():
    """Apply one previously verified queued XD operation through hot UIA host.

    The caller must still inspect the exact queue status and live scenegraph.
    No fallback/rerun when the worker reports an uncertain UI invocation.
    """
    from panda_xd_apply_hot import apply_one as hot_apply_once
    hot_apply_once()

async def call(c,tool,cap,args=None):
    r=await c.call_tool(tool,{"application":"xd","capability":cap,"arguments":args or {}})
    p=r.structured_content
    print("XD_MCP_RESULT="+json.dumps({"cap":cap,"error":r.is_error,"result":str(p)[:1000]},default=str),flush=True)
    if r.is_error or not isinstance(p,dict) or p.get("ok") is not True:
        raise RuntimeError("XD_MCP_OPERATION_UNKNOWN_NO_REPLAY "+cap)
    return p
async def snapshot(c):
    p=await call(c,"creative_read","creative.scenegraph.list")
    data=p.get("result") or {}
    if data.get("complete") is not True and find(p,"complete") is not True:
        raise RuntimeError("XD_SCENEGRAPH_INCOMPLETE")
    return node_map(data)

# State verified in GitHub run 38114632173 and read-only run 38131002152.
PREVIOUS_DOCUMENT_ID="892cdc9e-115d-4ec9-aa93-a0b75e9c1de0"
PREVIOUS_PENDING_OPERATION="xd-1791696933689-5"
PREVIOUS_RESUME_RUN_ID="38114632173"

def save_checkpoint(data):
    payload=json.dumps(data,indent=2,ensure_ascii=False)
    tmp=CHECKPOINT.with_suffix(".json.tmp")
    tmp.write_text(payload,encoding="utf-8")
    os.replace(tmp,CHECKPOINT)
    digest=hashlib.sha256(CHECKPOINT.read_bytes()).hexdigest()
    print("XD_CHECKPOINT_PERSISTED="+json.dumps({
        "count":len(data.get("proven",[])),
        "pending":data.get("pending"),
        "sha256":digest
    }),flush=True)
    return digest

async def read_receipt(c,op):
    payload=await call(c,"creative_read","xd.queue.status",{"operation_id":op})
    result=payload.get("result")
    if not isinstance(result,Mapping):raise RuntimeError("XD_RECEIPT_RESULT_NOT_MAPPING")
    return result

async def live_snapshot(c):
    result=await call(c,"creative_read","creative.scenegraph.list")
    snap=result.get("result")
    if not isinstance(snap,Mapping) or snap.get("complete") is not True:
        raise RuntimeError("XD_LIVE_SCENEGRAPH_NOT_COMPLETE")
    return snap,node_map(snap)

async def health_pending(c):
    health=await call(c,"creative_read","creative.health")
    info=health.get("result") or {}
    if info.get("bridge")!="connected":
        raise RuntimeError("XD_PLUGIN_NOT_CONNECTED_NO_WRITE")
    count=info.get("pending_count")
    if not isinstance(count,int) or count<0:
        raise RuntimeError("XD_PLUGIN_PENDING_COUNT_UNKNOWN_NO_WRITE")
    return count

def assert_existing_exactly(checkpoint,live,doc_id):
    saved=checkpoint.get("proven",[])
    if not isinstance(saved,list):raise RuntimeError("XD_CHECKPOINT_PROVEN_NOT_LIST")
    if len(saved)>len(STEPS):raise RuntimeError("XD_CHECKPOINT_TOO_MANY")
    if doc_id!=PREVIOUS_DOCUMENT_ID:
        raise RuntimeError("XD_ACTIVE_DOCUMENT_CHANGED_NO_WRITE "+str(doc_id))
    expected={}
    for idx,item in enumerate(saved,1):
        if item.get("ordinal")!=idx or item.get("name")!=STEPS[idx-1][0] or item.get("status")!="applied":
            raise RuntimeError("XD_CHECKPOINT_INVALID_ORDER_OR_RECEIPT")
        guid=item.get("guid")
        if not isinstance(guid,str) or not guid:
            raise RuntimeError("XD_CHECKPOINT_GUID_MISSING")
        expected[item["name"]]=guid
    if live!=expected:
        raise RuntimeError("XD_SCENEGRAPH_CHANGED_STOP_NO_REPLAY "+
                           json.dumps({"expected":expected,"observed":live}))
    print("XD_RECONCILED_EXACT_LIVE_STATE=PASS "+json.dumps({
        "document_id":doc_id,"applied":len(saved),"guids":expected
    }),flush=True)

async def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    if not CHECKPOINT.exists():
        raise RuntimeError("XD_RESUME_CHECKPOINT_MISSING_NO_NEW_DOCUMENT")
    checkpoint=json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    if checkpoint.get("run")!=RUN or RUN!=PREVIOUS_RESUME_RUN_ID:
        raise RuntimeError("XD_RESUME_TARGET_IS_NOT_PROVEN_RUN")
    async with Client(URL) as c:
        pending=await health_pending(c)
        snap,found=await live_snapshot(c)
        doc_id=snap.get("document_id")
        assert_existing_exactly(checkpoint,found,doc_id)
        start=len(checkpoint["proven"])+1
        if start<5: raise RuntimeError("XD_REPLAY_GUARD_CHECKPOINT_BEFORE_FOUR")
        for i in range(start,len(STEPS)+1):
            name,cap,args=STEPS[i-1]
            snap,found=await live_snapshot(c)
            assert_existing_exactly(checkpoint,found,snap.get("document_id"))
            pending=await health_pending(c)
            saved_pending=checkpoint.get("pending")
            if saved_pending is not None:
                if saved_pending.get("ordinal")!=i or saved_pending.get("name")!=name:
                    raise RuntimeError("XD_PENDING_CHECKPOINT_MISMATCH")
                op=saved_pending.get("operation_id")
                if not isinstance(op,str) or not op:
                    raise RuntimeError("XD_PENDING_CHECKPOINT_ID_MISSING")
            elif i==5 and len(checkpoint["proven"])==4:
                # Previous run stopped before SendKeys because the foreground
                # request failed. Operation 5 remains queued, as proven by
                # read-only run 38131002152. Do not queue it a second time.
                op=PREVIOUS_PENDING_OPERATION
                saved_pending={"ordinal":i,"name":name,"operation_id":op}
                checkpoint["pending"]=saved_pending
                save_checkpoint(checkpoint)
            else:
                if pending!=0:
                    raise RuntimeError("XD_FOREIGN_QUEUE_NOT_IDLE_NO_NEW_WRITE")
                print("XD_MODE1_STROKE_START="+json.dumps({"ordinal":i,"name":name,"cap":cap}),flush=True)
                response=await call(c,"creative_write",cap,args)
                result=response.get("result") or {}
                op=result.get("operation_id")
                if result.get("status")!="queued" or not isinstance(op,str) or result.get("pending_count")!=1:
                    raise RuntimeError("XD_CREATE_RECEIPT_NOT_EXACT_QUEUED_STOP")
                checkpoint["pending"]={"ordinal":i,"name":name,"operation_id":op}
                save_checkpoint(checkpoint)

            receipt=await read_receipt(c,op)
            status=receipt.get("status")
            print("XD_PENDING_OPERATION_RECONCILED="+json.dumps({
                "ordinal":i,"operation_id":op,"status":status,"pending_count":pending
            }),flush=True)
            if status=="queued":
                if await health_pending(c)!=1:
                    raise RuntimeError("XD_QUEUED_RECEIPT_BUT_QUEUE_COUNT_NOT_ONE")
                # One UXP application command, only after the Windows XD PID
                # is verified as true foreground. Not an MCP drawing replay.
                apply_one()
                for attempt in range(24):
                    receipt=await read_receipt(c,op)
                    status=receipt.get("status")
                    if status in ("applied","failed","rejected"):break
                    await asyncio.sleep(0.3)
            if status!="applied":
                raise RuntimeError("XD_MUTATION_NOT_APPLIED_NO_REPLAY "+str(status))
            snap,after=await live_snapshot(c)
            if snap.get("document_id")!=PREVIOUS_DOCUMENT_ID:
                raise RuntimeError("XD_ACTIVE_DOCUMENT_SWITCHED_AFTER_APPLY")
            if len(after)!=i or name not in after or await health_pending(c)!=0:
                raise RuntimeError("XD_LIVE_SCENEGRAPH_NOT_MATCHING_APPLIED_OP")
            guid=after[name]
            applied_guid=(receipt.get("result") or {}).get("guid")
            if applied_guid and applied_guid!=guid:
                raise RuntimeError("XD_RECEIPT_GUID_NOT_LIVE_GUID")
            for old in checkpoint["proven"]:
                if after.get(old["name"])!=old["guid"]:
                    raise RuntimeError("XD_PRIOR_VERIFIED_OBJECT_CHANGED")
            rec={"ordinal":i,"name":name,"guid":guid,"operation_id":op,"status":"applied"}
            checkpoint["proven"].append(rec)
            checkpoint["pending"]=None
            digest=save_checkpoint(checkpoint)
            print("XD_MODE1_STROKE_READBACK="+json.dumps({
                "ordinal":i,"name":name,"nodeCount":len(after),
                "guid":guid,"receipt":"applied","checkpointSHA256":digest
            }),flush=True)
            await asyncio.sleep(0.25)
        print("XD_MODE1_SCENEGRAPH_32_STROKES=PASS",flush=True)
        exported=await call(c,"creative_write","xd.export.png",
                            {"filename":f"MCP_Mode1_Panda_XD_{RUN}.png"})
        native=find(exported,"nativePath")
        if not isinstance(native,str) or not Path(native).is_file() or Path(native).stat().st_size<1000:
            raise RuntimeError("XD_NATIVE_PNG_EXPORT_NOT_VERIFIED")
        print("XD_NATIVE_PNG_EXPORT=PASS "+json.dumps({
            "nativePath":native,"bytes":Path(native).stat().st_size
        }),flush=True)

if __name__ == "__main__":
    asyncio.run(main())
