"""First real Photoshop RED poster checkpoint, not full design or visual PASS.

This is intentionally a bounded acceptance unit: a new portrait PSD, one
independent MCP layer/selection/fill, real readback, save and PNG export.
Never write when a different document is active, and never auto-retry UNKNOWN.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path

from mcp import Client

from panda_red_poster_blueprint import STEPS, WIDTH, HEIGHT, validate

ROOT = Path(os.environ["USERPROFILE"]) / "Documents" / "MCPAdobe"
RUN = os.environ["GITHUB_RUN_ID"]
TARGET = ROOT / f"MCP_KFP4_Red_PS_{RUN}.psd"
PNG = ROOT / f"MCP_KFP4_Red_PS_{RUN}.png"
URL = "http://127.0.0.1:8787/mcp"


async def call(client, name, capability, arguments=None, *, allow_overwrite=False):
    params={"application":"photoshop","capability":capability,"arguments":arguments or {}}
    if name=="creative_authorized_write":
        if capability!="creative.style.fill":
            raise RuntimeError("RED_PS_UNAUTHORIZED_HIGH_RISK_CAPABILITY")
        params["allow_destructive"]=True
    if capability=="creative.document.save" and allow_overwrite:
        params["allow_overwrite"]=True
    result=await asyncio.wait_for(client.call_tool(name,params),timeout=35)
    payload=result.structured_content or {}
    if result.is_error or payload.get("ok") is not True:
        raise RuntimeError("RED_PS_MCP_UNKNOWN_NO_REPLAY "+capability+" "+str(result.content)[:400])
    outcome=payload.get("outcome")
    if outcome in ("unknown","failed","pending_user_approval"):
        raise RuntimeError("RED_PS_MCP_UNVERIFIED_UNKNOWN_NO_REPLAY "+capability+" "+str(payload)[:300])
    print("RED_PS_MCP_STEP="+json.dumps({"capability":capability,
        "outcome":outcome,"result":str(payload.get("result"))[:300]},ensure_ascii=False),flush=True)
    return payload.get("result") or {}


async def state(client):
    return await call(client,"creative_read","creative.document.info")


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    validate()
    if STEPS[0]["kind"] != "rectangle" or STEPS[0]["fill"]!="#BC0000":
        raise RuntimeError("RED_PS_BACKGROUND_BLUEPRINT_CHANGED")
    if TARGET.exists() or PNG.exists():
        raise RuntimeError("RED_PS_OUTPUT_EXISTS_NO_BLIND_OVERWRITE")
    ROOT.mkdir(parents=True,exist_ok=True)
    async with Client(URL) as c:
        await call(c,"creative_read","creative.health")
        initial=await state(c)
        if initial.get("hasDocument") is not False or initial.get("openDocumentCount")!=0:
            raise RuntimeError("RED_PS_FOREIGN_OR_UNSAVED_DOCUMENT_PRESENT_NO_WRITES")
        await call(c,"creative_write","creative.document.create",{
            "width":WIDTH,"height":HEIGHT,"resolution":72,"colorMode":"RGB"})
        created=await state(c)
        info=created.get("document") or {}
        if created.get("hasDocument") is not True or int(info.get("width",-1))!=WIDTH or int(info.get("height",-1))!=HEIGHT:
            raise RuntimeError("RED_PS_NEW_PORTRAIT_CANVAS_NOT_VERIFIED_NO_RETRY")
        await call(c,"creative_write","creative.document.save",{"path":str(TARGET),"format":"PSD"})
        if not TARGET.is_file() or TARGET.stat().st_size<1000:
            raise RuntimeError("RED_PS_BLANK_PSD_CHECKPOINT_NOT_PERSISTED")
        print("RED_PS_NEW_NATIVE_CHECKPOINT="+json.dumps({"path":str(TARGET),"bytes":TARGET.stat().st_size,
            "sha256":file_hash(TARGET)}),flush=True)
        step=STEPS[0]
        await call(c,"creative_write","creative.layer.create",{"name":step["name"]})
        layer=await state(c)
        if (layer.get("activeLayer") or {}).get("name")!=step["name"]:
            raise RuntimeError("RED_PS_LAYER_CREATE_NOT_READBACK")
        await call(c,"creative_write","creative.selection.rectangle",{
            "left":0,"top":0,"right":WIDTH,"bottom":HEIGHT})
        selected=await state(c)
        if (selected.get("document") or {}).get("hasSelection") is not True:
            raise RuntimeError("RED_PS_SELECTION_NOT_READBACK")
        await call(c,"creative_authorized_write","creative.style.fill",
            {"red":188,"green":0,"blue":0})
        painted=await state(c)
        active=painted.get("activeLayer") or {}
        bounds=active.get("bounds") or {}
        if active.get("name")!=step["name"] or any(
            abs(float(bounds.get(k,-999))-target)>3 for k,target in
            (("left",0),("top",0),("right",WIDTH),("bottom",HEIGHT))
        ):
            raise RuntimeError("RED_PS_PAINTED_PIXELS_WRONG_BOUNDS_NO_REPLAY "+str(bounds))
        await call(c,"creative_write","creative.selection.clear")
        verified=await call(c,"creative_read","creative.layer.list")
        if step["name"] not in str(verified):
            raise RuntimeError("RED_PS_BACKGROUND_LAYER_MISSING_AFTER_FILL")
        before=file_hash(TARGET)
        await call(c,"creative_write","creative.document.save",{"path":str(TARGET),"format":"PSD"},
            allow_overwrite=True)
        after=file_hash(TARGET)
        if not TARGET.is_file() or before==after:
            raise RuntimeError("RED_PS_NATIVE_PSD_DID_NOT_PERSIST_NEW_LAYER")
        print("RED_PS_FIRST_LAYER_PERSISTED="+json.dumps({"layer":step["name"],"bounds":bounds,
            "bytes":TARGET.stat().st_size,"sha256":after}),flush=True)
        await call(c,"creative_write","creative.document.export",{"path":str(PNG),"format":"PNG"})
        if not PNG.is_file() or PNG.stat().st_size<2000 or PNG.read_bytes()[:8]!=b"\\x89PNG\\r\\n\\x1a\\n":
            raise RuntimeError("RED_PS_NATIVE_PNG_NOT_VERIFIED")
        print("RED_PS_FIRST_STROKE_NATIVE_ARTIFACTS=PASS "+json.dumps({
            "psd":str(TARGET),"psd_sha256":after,
            "png":str(PNG),"png_sha256":file_hash(PNG),
            "drawn":1,"target":len(STEPS),
            "visual_acceptance":"NOT_RUN_FURTHER_COMPONENTS_REQUIRED"}),flush=True)


if __name__=="__main__":
    asyncio.run(main())
