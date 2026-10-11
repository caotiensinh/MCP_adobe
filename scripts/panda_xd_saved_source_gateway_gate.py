"""Fail-closed XD saved document gateway refresh gate; read-only MCP calls."""
import asyncio,json,os,hashlib,sys
from pathlib import Path
from mcp import Client
ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
SOURCE=ROOT/"MCP_Mode1_Panda_XD_38136531800.xd"
SHA="d27eb3087d9dd4aa12fa055dfd1ae91f2e81e959235d31e4a430ff3be0645e39"
DOCUMENT="98d6635b-3767-4254-b200-ec8442b69ad2"
ARTBOARD="80f7938d-af52-4926-89ca-37442bbbe2cb"
FLAG=Path(os.environ["RUNNER_TEMP"])/"panda_xd_saved_source_gateway_refresh.flag"
async def read(c,cap):
    r=await c.call_tool("creative_read",{"application":"xd","capability":cap,"arguments":{}})
    p=r.structured_content
    if r.is_error or not isinstance(p,dict) or p.get("ok") is not True:
        raise RuntimeError("XD_SAVED_GATE_READ_FAILED "+cap+" "+str(r.content)[:350])
    return p.get("result") or {}
async def audit(c,allow_disconnected=False):
    if not SOURCE.is_file() or hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=SHA:
        raise RuntimeError("XD_SAVED_GATE_ORIGINAL_SHA_CHANGED_STOP")
    health=await read(c,"creative.health")
    if health.get("pending_count")!=0:
        raise RuntimeError("XD_SAVED_GATE_PENDING_OPERATION_PRESENT_STOP "+json.dumps(health))
    if health.get("bridge")!="connected":
        raise RuntimeError("XD_SAVED_GATE_UXP_BRIDGE_NOT_CONNECTED")
    scene=await read(c,"creative.scenegraph.list")
    nodes=scene.get("nodes") or []
    if scene.get("complete") is not True or scene.get("document_id")!=DOCUMENT:
        raise RuntimeError("XD_SAVED_GATE_WRONG_DOCUMENT")
    if len(nodes)!=1 or nodes[0].get("id")!=ARTBOARD or nodes[0].get("type")!="Artboard" or nodes[0].get("children"):
        raise RuntimeError("XD_SAVED_GATE_ARTBOARD_NOT_PRISTINE_STOP")
    print("XD_SAVED_GATE_SOURCE_GUARD=PASS document="+DOCUMENT+" artboard="+ARTBOARD,flush=True)
    result=await c.call_tool("creative_discover",{})
    payload=result.structured_content
    if result.is_error or not isinstance(payload,dict):
        raise RuntimeError("XD_SAVED_GATE_DISCOVER_FAILED")
    xd=next((i for i in payload.get("applications",[]) if i.get("application")=="xd"),None)
    if not isinstance(xd,dict):raise RuntimeError("XD_SAVED_GATE_XD_ADAPTER_MISSING")
    common=xd.get("common_capabilities") or []
    native=xd.get("native_capabilities") or []
    supported="creative.shape.ellipse" in common and "xd.export.png" in native
    print("XD_SAVED_GATE_CAPABILITIES="+json.dumps({"ellipse":"creative.shape.ellipse" in common,
        "png":"xd.export.png" in native,"bridge":health.get("bridge")}),flush=True)
    return supported
async def main():
    phase=sys.argv[1] if len(sys.argv)>1 else "before"
    if phase not in ("before","after"):raise RuntimeError("XD_SAVED_GATE_BAD_PHASE")
    async with Client("http://127.0.0.1:8787/mcp") as c:
        supported=await audit(c)
    if phase=="before":
        if supported:
            FLAG.unlink(missing_ok=True)
            print("XD_SAVED_GATE_RUNTIME_ALREADY_CURRENT=PASS",flush=True)
        else:
            FLAG.write_text("upgrade-required",encoding="utf-8")
            print("XD_SAVED_GATE_STALE_ADAPTER_CONFIRMED=PASS",flush=True)
    else:
        if not supported:raise RuntimeError("XD_SAVED_GATE_UPGRADE_NOT_VISIBLE")
        print("XD_SAVED_GATE_UPGRADED_GATEWAY=PASS",flush=True)
asyncio.run(main())
