"""Read-only native .xd geometry and live scenegraph guard before UXP v4 reload."""
import asyncio,hashlib,json,os,zipfile
from pathlib import Path
from mcp import Client
from panda_xd_mode1_e2e import STEPS,node_map
ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
PATH=ROOT/"MCP_Mode1_Panda_XD_38136531800.xd"
RECEIPTS=ROOT/"MCP_Mode1_Panda_XD_38136531800.json"
ORIGINAL_SHA="598f79071cf7dbfc426f9fef50144cf94225d2e7bb384c89e2e4fe1d67fdad29"
DOC="98d6635b-3767-4254-b200-ec8442b69ad2"
async def main():
    if not PATH.is_file() or hashlib.sha256(PATH.read_bytes()).hexdigest()!=ORIGINAL_SHA:
        raise RuntimeError("XD_ELLIPSE_PREFLIGHT_ORIGINAL_SHA_CHANGED")
    saved=json.loads(RECEIPTS.read_text(encoding="utf-8"))
    if len(saved["proven"])!=32 or saved.get("pending") is not None:
        raise RuntimeError("XD_ELLIPSE_PREFLIGHT_32_RECEIPTS_NOT_COMPLETE")
    with zipfile.ZipFile(PATH) as archive:
        agc=[x for x in archive.namelist() if x.endswith("/graphics/graphicContent.agc") and x.startswith("artwork/artboard-")]
        if len(agc)!=1:raise RuntimeError("XD_ELLIPSE_PREFLIGHT_ARTBOARD_ARCHIVE_AMBIGUOUS")
        graphics=json.loads(archive.read(agc[0]))
        shapes=graphics["children"][0]["artboard"]["children"]
        if len(shapes)!=32:raise RuntimeError("XD_ELLIPSE_PREFLIGHT_ARCHIVED_SHAPE_COUNT_WRONG")
        degenerate=[x["name"] for x in shapes if x.get("shape",{}).get("type")=="circle" and x["shape"].get("r")==0]
        expected={s[0] for s in STEPS if s[1]=="creative.shape.ellipse"}
        if set(degenerate)!=expected or len(degenerate)!=21:
            raise RuntimeError("XD_ELLIPSE_PREFLIGHT_ZERO_RADIUS_UNEXPECTED "+repr(degenerate))
        print("XD_ELLIPSE_PREFLIGHT_ARCHIVE=PASS zero_radius=21 shapes=32",flush=True)
    async with Client("http://127.0.0.1:8787/mcp") as c:
        for cap in ("creative.health","creative.scenegraph.list"):
            r=await c.call_tool("creative_read",{"application":"xd","capability":cap,"arguments":{}})
            p=r.structured_content
            if r.is_error or not isinstance(p,dict) or p.get("ok") is not True:
                raise RuntimeError("XD_ELLIPSE_PREFLIGHT_MCP_READ_FAILED "+cap)
            v=p.get("result") or {}
            if cap=="creative.health":
                if v.get("bridge")!="connected" or v.get("pending_count")!=0:
                    raise RuntimeError("XD_ELLIPSE_PREFLIGHT_BRIDGE_NOT_IDLE")
                print("XD_ELLIPSE_PREFLIGHT_BRIDGE="+str(v.get("bridge_build")),flush=True)
            else:
                if v.get("document_id")!=DOC or v.get("complete") is not True or len(node_map(v))!=32:
                    raise RuntimeError("XD_ELLIPSE_PREFLIGHT_WRONG_LIVE_DOCUMENT")
                flat={}
                def visit(x):
                    if isinstance(x,dict):
                        if x.get("name") in expected:flat[x["name"]]=x
                        for y in x.values():visit(y)
                    elif isinstance(x,list):
                        for y in x:visit(y)
                visit(v.get("nodes"))
                if len(flat)!=21 or any(x.get("bounds") is not None for x in flat.values()):
                    raise RuntimeError("XD_ELLIPSE_PREFLIGHT_LIVE_GEOMETRY_ALREADY_CHANGED")
                print("XD_ELLIPSE_PREFLIGHT_LIVE=PASS zero_bounds=21 shapes=32",flush=True)
    print("XD_ELLIPSE_PREFLIGHT_SAFE_TO_RELOAD=PASS",flush=True)
asyncio.run(main())
