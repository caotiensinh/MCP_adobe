"""Read-only safety gate for refreshing a stale XD gateway without touching Adobe GUI."""
import asyncio,json,os,sys
from collections.abc import Mapping
from pathlib import Path
from mcp import Client

URL="http://127.0.0.1:8787/mcp"
ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
CP=ROOT/"MCP_Mode1_Panda_XD_38114632173.json"
DOCUMENT_ID="892cdc9e-115d-4ec9-aa93-a0b75e9c1de0"
FLAG=Path(os.environ["RUNNER_TEMP"])/"xd_gateway_refresh_required.flag"

def walk(v):
    yield v
    if isinstance(v,dict):
        for y in v.values():yield from walk(y)
    elif isinstance(v,list):
        for y in v:yield from walk(y)

async def tool(c,name,args=None):
    response=await c.call_tool(name,args or {})
    if response.is_error or not isinstance(response.structured_content,dict):
        raise RuntimeError("XD_GATEWAY_READ_ONLY_TOOL_ERROR "+name+
                           " "+str(response.content)[:400])
    return response.structured_content

async def read(c,cap,args=None):
    result=await tool(c,"creative_read",{
        "application":"xd","capability":cap,"arguments":args or {}
    })
    if result.get("ok") is not True:
        raise RuntimeError("XD_GATEWAY_READ_ERROR "+cap)
    return result.get("result") or {}

async def verify(c,checkpoint):
    health=await read(c,"creative.health")
    if health.get("bridge")!="connected" or health.get("pending_count")!=0:
        raise RuntimeError("XD_GATEWAY_REFUSE_REFRESH_WHILE_QUEUE_NOT_IDLE "+
                           json.dumps(health))
    scene=await read(c,"creative.scenegraph.list")
    if scene.get("complete") is not True or scene.get("document_id")!=DOCUMENT_ID:
        raise RuntimeError("XD_GATEWAY_REFUSE_REFRESH_UNKNOWN_DOCUMENT")
    actual={}
    for node in walk(scene.get("nodes",[])):
        if isinstance(node,dict) and node.get("name", "").startswith(("01 XD","02 XD","03 XD",
                        "04 XD","05 XD","06 XD","07 XD","08 XD","09 XD",
                        "10 XD","11 XD","12 XD","13 XD","14 XD","15 XD",
                        "16 XD","17 XD","18 XD","19 XD","20 XD","21 XD",
                        "22 XD","23 XD","24 XD","25 XD","26 XD","27 XD",
                        "28 XD","29 XD","30 XD","31 XD","32 XD")):
            actual[node["name"]]=node.get("id")
    expected={v["name"]:v["guid"] for v in checkpoint["proven"]}
    if actual!=expected:
        raise RuntimeError("XD_GATEWAY_REFUSE_REFRESH_SCENEGRAPH_CHANGED "+
                           json.dumps({"expected":expected,"actual":actual}))
    print("XD_REFRESH_STATE_GUARD=PASS "+json.dumps({
        "document_id":DOCUMENT_ID,"verified_nodes":len(expected),
        "queue":0
    }),flush=True)
    discover=await tool(c,"creative_discover")
    apps=discover.get("applications") or []
    xd=next((x for x in apps if x.get("application")=="xd"),None)
    if not isinstance(xd,Mapping):
        raise RuntimeError("XD_GATEWAY_DISCOVERY_MISSING_ADAPTER")
    caps=xd.get("common_capabilities") or []
    native=xd.get("native_capabilities") or []
    return "creative.shape.ellipse" in caps and "xd.export.png" in native

async def main():
    phase=sys.argv[1]
    if phase not in ("before","after"):
        raise RuntimeError("expected before/after")
    cp=json.loads(CP.read_text(encoding="utf-8"))
    if cp.get("run")!="38114632173" or len(cp.get("proven",[]))<5 or cp.get("pending") is not None:
        raise RuntimeError("XD_GATEWAY_REFRESH_CHECKPOINT_NOT_FIVE_OR_QUEUE_UNKNOWN")
    async with Client(URL) as c:
        supported=await verify(c,cp)
        if phase=="before":
            if supported:
                FLAG.unlink(missing_ok=True)
                print("XD_GATEWAY_RUNTIME_ALREADY_CURRENT_NO_RESTART=PASS",flush=True)
            else:
                FLAG.write_text("refresh",encoding="ascii")
                print("XD_GATEWAY_STALE_ADAPTER_MEASURED_REFRESH_REQUIRED=PASS",flush=True)
        else:
            if not supported:
                raise RuntimeError("XD_GATEWAY_REFRESH_DID_NOT_LOAD_ELLIPSE_AND_PNG")
            print("XD_GATEWAY_REFRESH_VERIFIED_ELLIPSE_AND_PNG=PASS",flush=True)

asyncio.run(main())
