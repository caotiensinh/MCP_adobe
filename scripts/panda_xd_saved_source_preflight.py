"""Read-only XD live saved-source E2E preflight on MRCAO."""
import asyncio,json,os,hashlib
from pathlib import Path
from mcp import Client
ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
FILE=ROOT/"MCP_Mode1_Panda_XD_38136531800.xd"
URL="http://127.0.0.1:8787/mcp"
async def main():
    if not FILE.is_file() or FILE.stat().st_size<4096:
        raise RuntimeError("XD_E2E_NATIVE_SOURCE_MISSING")
    print("XD_E2E_NATIVE_SOURCE="+json.dumps({"path":str(FILE),"bytes":FILE.stat().st_size,
          "sha256":hashlib.sha256(FILE.read_bytes()).hexdigest()}),flush=True)
    async with Client(URL) as c:
        for cap in ("creative.health","creative.document.info","creative.scenegraph.list"):
            r=await c.call_tool("creative_read",{"application":"xd","capability":cap,"arguments":{}})
            p=r.structured_content or {}
            data=p.get("result") or {}
            print("XD_E2E_READ="+json.dumps({"cap":cap,"tool_error":r.is_error,"ok":p.get("ok"),
                 "data":data},default=str)[:9000],flush=True)
            if r.is_error or p.get("ok") is not True:raise RuntimeError("XD_E2E_READ_FAILED_"+cap)
            if cap=="creative.health" and (data.get("bridge")!="connected" or data.get("pending_count")!=0):
                raise RuntimeError("XD_E2E_HOST_BRIDGE_OR_QUEUE_UNREADY")
            if cap=="creative.scenegraph.list":
                if data.get("complete") is not True or not data.get("document_id"):
                    raise RuntimeError("XD_E2E_SCENEGRAPH_NOT_LIVE")
                if not any(isinstance(n,dict) and n.get("type")=="Artboard" for n in data.get("nodes",[])):
                    raise RuntimeError("XD_E2E_REAL_ARTBOARD_MISSING")
                print("XD_E2E_SOURCE_DOCUMENT_ID="+str(data["document_id"]),flush=True)
        r=await c.call_tool("creative_discover",{})
        p=r.structured_content or {}
        apps=p.get("applications") or []
        xd=next((x for x in apps if x.get("application")=="xd"),None)
        if not isinstance(xd,dict):raise RuntimeError("XD_E2E_ADAPTER_NOT_DISCOVERED")
        common=xd.get("common_capabilities") or []
        native=xd.get("native_capabilities") or []
        print("XD_E2E_DISCOVER="+json.dumps({"common":common,"native":native}),flush=True)
        if "creative.shape.ellipse" not in common or "xd.export.png" not in native:
            raise RuntimeError("XD_E2E_RUNTIME_MISSING_ELLIPSE_OR_PNG_CAPABILITIES")
        print("XD_E2E_READ_ONLY_PREFLIGHT=PASS",flush=True)
asyncio.run(main())
