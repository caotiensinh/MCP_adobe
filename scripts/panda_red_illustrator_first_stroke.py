"""First editable red Illustrator native checkpoint; not the full poster yet."""
import asyncio,hashlib,json,os
from pathlib import Path
from mcp import Client
from panda_red_poster_blueprint import WIDTH,HEIGHT,STEPS,validate

ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
RUN=os.environ["GITHUB_RUN_ID"]
NAME=f"MCP_KFP4_Red_AI_{RUN}"
NATIVE=ROOT/(NAME+".ai")
PNG=ROOT/(NAME+".png")
URL="http://127.0.0.1:8787/mcp"

async def readwrite(client,kind,cap,args=None,overwrite=False):
    params={"application":"illustrator","capability":cap,"arguments":args or {}}
    if overwrite:params["allow_overwrite"]=True
    r=await asyncio.wait_for(client.call_tool(kind,params),timeout=35)
    p=r.structured_content or {}
    if r.is_error or p.get("ok") is not True:
        raise RuntimeError("RED_AI_MCP_RESULT_UNKNOWN_NO_REPLAY "+cap+" "+str(r.content)[:350])
    value=p.get("result") or {}
    if isinstance(value,dict) and value.get("execution") in ("unknown","failed"):
        raise RuntimeError("RED_AI_UPSTREAM_EXECUTION_UNKNOWN_NO_REPLAY "+cap)
    print("RED_AI_MCP_STEP="+json.dumps({"cap":cap,"outcome":p.get("outcome"),
        "execution":value.get("execution") if isinstance(value,dict) else None},default=str),flush=True)
    return value

async def host(client):
    result=await readwrite(client,"creative_read","creative.health",{"probe":False,"timeout":5})
    bridge=(result.get("connection") or {}).get("data") or {}
    panel=(bridge.get("layers") or {}).get("panel") or {}
    running=bridge.get("execution") or {}
    if (panel.get("status")!="ok" or panel.get("busy") is not False
        or panel.get("heartbeatStale") is True or
        running.get("activeJob") is not None or
        running.get("waiting")!=0 or
        running.get("unresolvedJobs")):
        raise RuntimeError("RED_AI_DESKTOP_OR_HOST_BUSY_NO_WRITE")
    return bridge

async def doc(client):
    r=await readwrite(client,"creative_read","creative.document.info",{})
    if r.get("execution")!="succeeded":
        raise RuntimeError("RED_AI_DOCUMENT_READBACK_NOT_COMPLETE")
    data=r.get("data") or {}
    doc=data.get("document") or {}
    layers=data.get("layers") or []
    count=sum(int(x.get("itemCount") or 0) for x in layers)
    names=[i.get("name") for x in layers for i in (x.get("items") or [])]
    return doc,count,names

def checksum(p):return hashlib.sha256(p.read_bytes()).hexdigest()

async def main():
    validate()
    if NATIVE.exists() or PNG.exists():
        raise RuntimeError("RED_AI_NATIVE_TARGET_ALREADY_EXISTS_REFUSE_OVERWRITE")
    ROOT.mkdir(parents=True,exist_ok=True)
    async with Client(URL) as client:
        status=await host(client)
        if (status.get("layers") or {}).get("document",{}).get("status")=="ok":
            raise RuntimeError("RED_AI_EXISTING_DOCUMENT_OPEN_NO_CANVAS_MUTATION")
        await readwrite(client,"creative_write","creative.document.create",{
            "name":NAME,"width":WIDTH,"height":HEIGHT,"color_mode":"RGB"})
        document,count,names=await doc(client)
        if count!=0 or int(document.get("width",-1))!=WIDTH or int(document.get("height",-1))!=HEIGHT:
            raise RuntimeError("RED_AI_FRESH_ARTBOARD_GEOMETRY_INVALID")
        await readwrite(client,"creative_write","creative.document.save",{"file_path":str(NATIVE)})
        if not NATIVE.is_file() or NATIVE.stat().st_size<1000:
            raise RuntimeError("RED_AI_NATIVE_BLANK_CHECKPOINT_FAILED")
        before=checksum(NATIVE)
        step=STEPS[0]
        await host(client)
        await readwrite(client,"creative_write","creative.shape.rectangle",{
            "name":step["name"],"x":step["x"],"y":step["y"],
            "width":step["width"],"height":step["height"],
            "fill":{"r":188,"g":0,"b":0}})
        document,count,names=await doc(client)
        if count!=1 or step["name"] not in names:
            raise RuntimeError("RED_AI_FIRST_VECTOR_LAYER_MISSING_NO_REPLAY")
        await readwrite(client,"creative_write","creative.document.save",{})
        if checksum(NATIVE)==before:
            raise RuntimeError("RED_AI_CHECKPOINT_HAS_NO_NEW_VECTOR")
        await host(client)
        await readwrite(client,"creative_write","creative.document.export",{
            "output_path":str(PNG),"format":"png","scale":1,"overwrite":False})
        if not PNG.is_file() or PNG.stat().st_size<1000 or PNG.read_bytes()[:8]!=bytes((137,80,78,71,13,10,26,10)):
            raise RuntimeError("RED_AI_ADOBE_NATIVE_PNG_NOT_VERIFIED")
        print("RED_AI_FIRST_STROKE_NATIVE_ARTIFACTS=PASS "+json.dumps({
            "objects":count,"total_plan":len(STEPS),"native":str(NATIVE),
            "native_sha256":checksum(NATIVE),"png":str(PNG),
            "png_sha256":checksum(PNG),"image_approval":"NOT_FULL_POSTER"}),flush=True)

if __name__=="__main__":
    asyncio.run(main())
