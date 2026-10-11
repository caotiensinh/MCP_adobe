"""Read only reconciliation of saved XD rectangles against intended positions."""
import asyncio,json,hashlib,os
from pathlib import Path
from mcp import Client
from panda_xd_mode1_e2e import STEPS
ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
SOURCE=ROOT/"MCP_Mode1_Panda_XD_38136531800.xd"
EXPECTED="3a10e1510abc41eccd4485d6f852ea6ced7acc2cf50109e7c1bd123353589ed1"
async def main():
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError("XD_RECT_DIAG_SOURCE_SHA_MISMATCH")
    checkpoint=json.loads((ROOT/"MCP_Mode1_Panda_XD_38136531800_ellipse_repair.json").read_text(encoding="utf8"))
    if checkpoint.get("pending") is not None or len(checkpoint.get("repaired",[]))!=21:raise RuntimeError("XD_RECT_DIAG_INCOMPLETE_ELLIPSE_REPAIR")
    async with Client("http://127.0.0.1:8787/mcp") as c:
        for cap in ("creative.health","creative.scenegraph.list"):
            r=await c.call_tool("creative_read",{"application":"xd","capability":cap,"arguments":{}})
            payload=r.structured_content or {}
            if r.is_error or payload.get("ok") is not True:raise RuntimeError("XD_RECT_DIAG_MCP_READ_ERROR "+cap)
            value=payload.get("result") or {}
            if cap=="creative.health":
                if value.get("bridge_build")!="xd-ellipse-radius-geometry-v4" or value.get("pending_count")!=0:
                    raise RuntimeError("XD_RECT_DIAG_BRIDGE_NOT_IDLE_V4")
            else:
                if value.get("document_id")!="98d6635b-3767-4254-b200-ec8442b69ad2":
                    raise RuntimeError("XD_RECT_DIAG_WRONG_DOCUMENT")
                artboards=value.get("nodes",[])
                if len(artboards)!=1:raise RuntimeError("XD_RECT_DIAG_ARTBOARD_COUNT_BAD")
                nodes=artboards[0].get("children",[])
                if len(nodes)!=32:raise RuntimeError("XD_RECT_DIAG_NODE_COUNT_BAD")
                byName={n["name"]:n for n in nodes}
                results=[]
                for name,cap,args in STEPS:
                    if cap!="creative.shape.rectangle":continue
                    node=byName.get(name)
                    if not node or node.get("type")!="Rectangle":raise RuntimeError("XD_RECT_DIAG_RECTANGLE_IDENTITY_WRONG "+name)
                    bounds=node.get("bounds")
                    if not bounds:raise RuntimeError("XD_RECT_DIAG_RECTANGLE_HAS_NO_BOUNDS "+name)
                    offset=(bounds["left"]-args["x"],bounds["top"]-args["y"])
                    results.append({"name":name,"guid":node["id"],"actual":[bounds["left"],bounds["top"]],"target":[args["x"],args["y"]],"offset":offset})
                print("XD_RECT_DIAG_LIVE_BOUNDS="+json.dumps(results),flush=True)
                if len(results)!=11 or any(x["offset"]!=(491,220) for x in results):
                    raise RuntimeError("XD_RECT_DIAG_OFFSETS_NOT_UNIFORM_REFUSE_RECT_REPAIR")
                print("XD_RECT_DIAG_11_UNIFORM_SHIFT=PASS offsetX=491 offsetY=220",flush=True)
asyncio.run(main())
