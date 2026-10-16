"""Read-only evidence before and after ONE GUI Apply of the saved XD repair operation."""
import asyncio,hashlib,json,os,sys
from pathlib import Path
from mcp import Client
from panda_xd_mode1_e2e import STEPS
ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
CHECKPOINT=ROOT/"MCP_Mode1_Panda_XD_38136531800_ellipse_repair.json"
ORIGINAL=ROOT/"MCP_Mode1_Panda_XD_38136531800.xd"
OP="xd-1791723425452-1"
GUID="dd3a2134-9a3f-4a3e-a1a2-12655ab97d92"
DOC="98d6635b-3767-4254-b200-ec8442b69ad2"
SHA="598f79071cf7dbfc426f9fef50144cf94225d2e7bb384c89e2e4fe1d67fdad29"
NAME="06 XD Bamboo Upper Leaf"
async def checked(c,cap,params=None):
    r=await c.call_tool("creative_read",{"application":"xd","capability":cap,"arguments":params or {}})
    p=r.structured_content
    if r.is_error or not isinstance(p,dict) or p.get("ok") is not True:
        raise RuntimeError("XD_RESUME_HOST_READ_FAILED "+cap+" "+str(r.content)[:300])
    return p.get("result") or {}
def find(tree):
    if isinstance(tree,dict):
        if tree.get("name")==NAME:return tree
        for v in tree.values():
            result=find(v)
            if result is not None:return result
    if isinstance(tree,list):
        for v in tree:
            result=find(v)
            if result is not None:return result
    return None
async def main():
    phase=sys.argv[1]
    if phase not in ("before","after"):raise RuntimeError("XD_RESUME_PHASE_INVALID")
    d=json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    if (d.get("document_id")!=DOC or len(d.get("repaired",[]))!=0 or
        d.get("pending")!={"ordinal":1,"guid":GUID,"operation_id":OP}):
        raise RuntimeError("XD_RESUME_CHECKPOINT_NOT_EXACT")
    if not ORIGINAL.is_file() or hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()!=SHA:
        raise RuntimeError("XD_RESUME_ORIGINAL_CHANGED")
    async with Client("http://127.0.0.1:8787/mcp") as c:
        h=await checked(c,"creative.health")
        g=await checked(c,"creative.scenegraph.list")
        op=await checked(c,"xd.queue.status",{"operation_id":OP})
        if h.get("bridge_build")!="xd-ellipse-radius-geometry-v4" or g.get("document_id")!=DOC:
            raise RuntimeError("XD_RESUME_WRONG_PLUGIN_OR_DOCUMENT")
        node=find(g.get("nodes"))
        if not isinstance(node,dict) or node.get("id")!=GUID or node.get("type")!="Ellipse":
            raise RuntimeError("XD_RESUME_WRONG_NODE")
        if phase=="before":
            if h.get("pending_count")!=1 or op.get("status")!="queued" or node.get("bounds") is not None:
                raise RuntimeError("XD_RESUME_EXPECTED_QUEUED_ZERO_RADIUS "+str(op))
            print("XD_RESUME_EXACT_OPERATION_QUEUED=PASS "+OP,flush=True)
        else:
            bounds=node.get("bounds")
            if h.get("pending_count")!=0 or op.get("status")!="applied" or not isinstance(bounds,dict):
                raise RuntimeError("XD_RESUME_POST_APPLY_NOT_VERIFIED "+json.dumps({
                    "pending":h.get("pending_count"),"receipt":op,"bounds":bounds},default=str)[:600])
            target=next(x[2] for x in STEPS if x[0]==NAME)
            for key,expect in (("left",target["x"]),("top",target["y"]),
                ("right",target["x"]+target["width"]),("bottom",target["y"]+target["height"])):
                actual=bounds.get(key)
                if not isinstance(actual,(int,float)) or abs(actual-expect)>2:
                    raise RuntimeError("XD_RESUME_REPAIRED_BOUNDS_MISMATCH "+key+" "+str(actual))
            print("XD_RESUME_EXACT_OPERATION_APPLIED=PASS "+json.dumps({"operation":OP,"bounds":bounds}),flush=True)
asyncio.run(main())
