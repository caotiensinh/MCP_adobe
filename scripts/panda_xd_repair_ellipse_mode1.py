"""Repair 21 zero-radius Ellipses in LIVE XD, one MCP mutation and receipt per GUID.

Never reconstruct or edit .xd bytes directly. The existing 32 GUIDs, verified
on a native Adobe document, are preserved; only their degenerate radii change.
"""
import asyncio,hashlib,json,os,shutil
from collections.abc import Mapping
from pathlib import Path
from mcp import Client
from panda_xd_mode1_e2e import STEPS,node_map,apply_one,call
ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
SRC_ID="38136531800"
SOURCE=ROOT/f"MCP_Mode1_Panda_XD_{SRC_ID}.xd"
ORIGINAL=ROOT/f"MCP_Mode1_Panda_XD_{SRC_ID}.json"
REPAIR=ROOT/f"MCP_Mode1_Panda_XD_{SRC_ID}_ellipse_repair.json"
PNG=ROOT/f"MCP_Mode1_Panda_XD_{SRC_ID}_repaired.png"
SOURCE_SHA="598f79071cf7dbfc426f9fef50144cf94225d2e7bb384c89e2e4fe1d67fdad29"
DOCUMENT="98d6635b-3767-4254-b200-ec8442b69ad2"
ELLIPSES=[step for step in STEPS if step[1]=="creative.shape.ellipse"]

def persist(data):
    tmp=REPAIR.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(tmp,REPAIR)
    h=hashlib.sha256(REPAIR.read_bytes()).hexdigest()
    print("XD_GEOMETRY_CHECKPOINT="+json.dumps({"completed":len(data["repaired"]),
      "pending":data.get("pending"),"sha256":h}),flush=True)

def find_by_name(obj,name):
    if isinstance(obj,Mapping):
        if obj.get("name")==name:return obj
        for child in obj.values():
            f=find_by_name(child,name)
            if f is not None:return f
    elif isinstance(obj,list):
        for child in obj:
            f=find_by_name(child,name)
            if f is not None:return f
    return None

def verify_bounds(obj,params,zero=False):
    bounds=obj.get("bounds")
    if zero:
        if bounds is not None:
            raise RuntimeError("XD_ELLIPSE_WAS_NOT_ZERO_INITIAL "+str(obj.get("name")))
        return
    if not isinstance(bounds,Mapping):
        raise RuntimeError("XD_REPAIRED_ELLIPSE_MISSING_BOUNDS "+str(obj.get("name")))
    for prop,ref in (("left",params["x"]),("top",params["y"]),
                     ("right",params["x"]+params["width"]),("bottom",params["y"]+params["height"])):
        actual=bounds.get(prop)
        if not isinstance(actual,(float,int)) or abs(actual-ref)>2:
            raise RuntimeError("XD_ELLIPSE_GEOMETRY_MISMATCH "+json.dumps({
              "name":obj.get("name"),"property":prop,"expected":ref,"actual":actual}))

async def read(c,cap,params=None):
    r=await call(c,"creative_read",cap,params)
    data=r.get("result")
    if not isinstance(data,Mapping):raise RuntimeError("XD_REPAIR_NO_RESULT "+cap)
    return data

async def snapshot(c):
    health=await read(c,"creative.health")
    if health.get("bridge")!="connected" or health.get("bridge_build")!="xd-ellipse-radius-geometry-v4":
        raise RuntimeError("XD_REPAIR_PLUGIN_V4_NOT_LOADED")
    if not isinstance(health.get("pending_count"),int):
        raise RuntimeError("XD_REPAIR_QUEUE_DEPTH_UNKNOWN")
    scene=await read(c,"creative.scenegraph.list")
    if scene.get("complete") is not True or scene.get("document_id")!=DOCUMENT:
        raise RuntimeError("XD_REPAIR_LIVE_DOCUMENT_ID_MISMATCH")
    if len(node_map(scene))!=32:raise RuntimeError("XD_REPAIR_EXISTING_NODE_COUNT_CHANGED")
    return health,scene

async def main():
    if not SOURCE.is_file() or hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=SOURCE_SHA:
        raise RuntimeError("XD_REPAIR_NATIVE_SOURCE_SHA_CHANGED")
    original=json.loads(ORIGINAL.read_text(encoding="utf-8"))
    if len(original.get("proven",[]))!=32 or original.get("pending") is not None:
        raise RuntimeError("XD_REPAIR_ORIGINAL_32_NOT_VERIFIED")
    guids={p["name"]:p["guid"] for p in original["proven"]}
    if len(set(guids.values()))!=32:raise RuntimeError("XD_REPAIR_DUPLICATE_ORIGINAL_GUIDS")
    if REPAIR.exists():
        progress=json.loads(REPAIR.read_text(encoding="utf-8"))
        if progress.get("source_sha256")!=SOURCE_SHA or progress.get("document_id")!=DOCUMENT:
            raise RuntimeError("XD_REPAIR_CHECKPOINT_SOURCE_MISMATCH")
    else:
        progress={"document_id":DOCUMENT,"source_sha256":SOURCE_SHA,
                  "repaired":[],"pending":None}
        persist(progress)
    if [p["name"] for p in progress["repaired"]]!=[t[0] for t in ELLIPSES[:len(progress["repaired"])]]:
        raise RuntimeError("XD_REPAIR_PROGRESS_WRONG_ORDER")
    async with Client("http://127.0.0.1:8787/mcp") as c:
        for number,step in enumerate(ELLIPSES,1):
            name,_,params=step
            info,scene=await snapshot(c)
            obj=find_by_name(scene.get("nodes"),name)
            if not isinstance(obj,Mapping) or obj.get("id")!=guids[name] or obj.get("type")!="Ellipse":
                raise RuntimeError("XD_REPAIR_TARGET_GUID_OR_TYPE_MISMATCH "+name)
            if number<=len(progress["repaired"]):
                verify_bounds(obj,params)
                continue
            pending=progress.get("pending")
            if pending:
                if pending.get("ordinal")!=number or pending.get("guid")!=guids[name]:
                    raise RuntimeError("XD_REPAIR_PENDING_DIFFERENT_OBJECT")
                op=pending["operation_id"]
                if info["pending_count"]!=1:
                    # May already have been applied before checkpoint flush.
                    if info["pending_count"]!=0:raise RuntimeError("XD_REPAIR_PENDING_QUEUE_UNKNOWN")
            else:
                if info["pending_count"]!=0:raise RuntimeError("XD_REPAIR_FOREIGN_OPERATION_QUEUED")
                verify_bounds(obj,params,zero=True)
                print("XD_REPAIR_ONE_START="+json.dumps({"ordinal":number,"name":name,
                    "guid":guids[name],"width":params["width"],"height":params["height"]}),flush=True)
                p=await call(c,"creative_write","xd.queue.ellipse_geometry_repair",{
                    "document_id":DOCUMENT,"guid":guids[name],"name":name,
                    "width":params["width"],"height":params["height"],
                    "x":params["x"],"y":params["y"]})
                result=p.get("result") or {}
                op=result.get("operation_id")
                if result.get("status")!="queued" or not isinstance(op,str) or result.get("pending_count")!=1:
                    raise RuntimeError("XD_REPAIR_QUEUE_RECEIPT_UNKNOWN_STOP")
                progress["pending"]={"ordinal":number,"guid":guids[name],"operation_id":op}
                persist(progress)
            receipt=await read(c,"xd.queue.status",{"operation_id":op})
            status=receipt.get("status")
            if status=="queued":
                latest=await read(c,"creative.health")
                if latest.get("pending_count")!=1:
                    raise RuntimeError("XD_REPAIR_QUEUED_QUEUE_DEPTH_NOT_ONE")
                apply_one()
                for _ in range(22):
                    await asyncio.sleep(.32)
                    receipt=await read(c,"xd.queue.status",{"operation_id":op})
                    status=receipt.get("status")
                    if status!="queued":break
            if status!="applied":
                raise RuntimeError("XD_REPAIR_OPERATION_NOT_APPLIED_NO_REPLAY "+str(status))
            healthy,after=await snapshot(c)
            if healthy["pending_count"]!=0:raise RuntimeError("XD_REPAIR_NOT_IDLE_AFTER_APPLY")
            repaired=find_by_name(after["nodes"],name)
            if repaired.get("id")!=guids[name]:raise RuntimeError("XD_REPAIR_GUID_CHANGED_AFTER_MUTATION")
            verify_bounds(repaired,params)
            for old in progress["repaired"]:
                prev=find_by_name(after["nodes"],old["name"])
                oldstep=next(t for t in ELLIPSES if t[0]==old["name"])
                verify_bounds(prev,oldstep[2])
            record={"ordinal":number,"name":name,"guid":guids[name],
                    "operation_id":op,"status":"applied","bounds":repaired["bounds"]}
            progress["repaired"].append(record)
            progress["pending"]=None
            persist(progress)
            print("XD_REPAIR_ONE_READBACK="+json.dumps({"ordinal":number,"name":name,
                "guid":guids[name],"bounds":repaired["bounds"]}),flush=True)
        print("XD_REPAIR_ALL_ELLIPSES_LIVE=PASS count="+str(len(ELLIPSES)),flush=True)
        if PNG.exists():raise RuntimeError("XD_REPAIR_PNG_ALREADY_EXISTS_REFUSE_EXPORT_OVERWRITE")
        filename=f"MCP_Mode1_Panda_XD_{SRC_ID}_repaired.png"
        resp=await call(c,"creative_write","xd.export.png",{"filename":filename})
        from panda_xd_mode1_e2e import find
        source=find(resp,"nativePath")
        if not isinstance(source,str) or not Path(source).is_file():
            raise RuntimeError("XD_REPAIR_NATIVE_PNG_EXPORT_NOT_CONFIRMED")
        raw=Path(source).read_bytes()
        if len(raw)<4000 or raw[:8]!=b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("XD_REPAIR_EXPORT_INVALID_PNG")
        PNG.write_bytes(raw)
        print("XD_REPAIR_EXPORTED_REAL_XD_PNG=PASS "+json.dumps({"path":str(PNG),
            "bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}),flush=True)

if __name__=="__main__":
    asyncio.run(main())
