"""Resume red Photoshop poster from verified native stroke-1; persist strokes 2-3.

Source PSD is immutable. This script refuses unrelated documents and any
unknown or partial mutation, and never replays a non-idempotent write.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
import shutil
from pathlib import Path
from mcp import Client
from panda_red_poster_blueprint import STEPS, WIDTH, HEIGHT, validate

ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
SOURCE=ROOT/"MCP_KFP4_Red_PS_38146001775.psd"
SOURCE_SHA="4062233b7688583b1ed185c23fd38f22d0cb1e578f24e00de5fe95ce1ae41cdf"
RUN=os.environ["GITHUB_RUN_ID"]
TARGET=ROOT/f"MCP_KFP4_Red_PS_{RUN}_3shapes.psd"
PNG=ROOT/f"MCP_KFP4_Red_PS_{RUN}_3shapes.png"
URL="http://127.0.0.1:8787/mcp"

def sha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def rgb(value:str)->dict[str,int]:
    if len(value)!=7 or value[0]!="#": raise ValueError("invalid RGB")
    r,g,b=bytes.fromhex(value[1:])
    return {"red":r,"green":g,"blue":b}

async def call(c,tool,cap,args=None,authorized=False):
    p={"application":"photoshop","capability":cap,"arguments":args or {}}
    if authorized:
        if tool!="creative_authorized_write" or cap!="creative.style.fill":
            raise RuntimeError("PS_UNAUTHORIZED_CAPABILITY")
        p["allow_destructive"]=True
    if cap=="creative.document.save":p["allow_overwrite"]=True
    try:
        r=await asyncio.wait_for(c.call_tool(tool,p),timeout=30)
    except Exception as e:
        raise RuntimeError("PS_OPERATION_OUTCOME_UNKNOWN_NO_REPLAY "+cap) from e
    data=r.structured_content or {}
    if r.is_error or data.get("ok") is not True or data.get("outcome") in ("unknown","failed"):
        raise RuntimeError("PS_OPERATION_OUTCOME_UNKNOWN_NO_REPLAY "+cap+" "+str(r.content)[:200])
    print("RED_PS_3STEP_CALL="+json.dumps({"cap":cap,"outcome":data.get("outcome")}),flush=True)
    return data.get("result") or {}

async def state(c):return await call(c,"creative_read","creative.document.info")

async def layer_names(c):
    raw=await call(c,"creative_read","creative.layer.list")
    text=raw.get("text","")
    if not isinstance(text,str) or "{" not in text:
        raise RuntimeError("PS_LAYER_LIST_MALFORMED")
    obj=json.loads(text[text.index("{"):])
    return [p.get("name") for p in obj.get("layers",[])]

def inspect(doc,expected_name):
    if doc.get("hasDocument") is not True:raise RuntimeError("PS_MISSING_DOCUMENT")
    info=doc.get("document") or {}
    if int(info.get("width",-1))!=WIDTH or int(info.get("height",-1))!=HEIGHT:
        raise RuntimeError("PS_WRONG_CANVAS_SIZE")
    if expected_name and not str(info.get("name","")).startswith(expected_name):
        raise RuntimeError("PS_FOREIGN_ACTIVE_DOCUMENT")
    return info

async def main():
    validate()
    if len(STEPS)<3 or any(p["kind"]!="rectangle" for p in STEPS[:3]):
        raise RuntimeError("PS_BLUEPRINT_FIRST_3_NOT_RECTANGLES")
    if not SOURCE.is_file() or sha(SOURCE)!=SOURCE_SHA:
        raise RuntimeError("PS_SOURCE_SHA_CHANGED_NO_MUTATION")
    if TARGET.exists() or PNG.exists():
        raise RuntimeError("PS_STAGED_OUTPUT_ALREADY_EXISTS_NO_REPLAY")
    ROOT.mkdir(parents=True,exist_ok=True)
    async with Client(URL) as c:
        await call(c,"creative_read","creative.health")
        original=await state(c)
        if original.get("hasDocument"):
            # Photoshop 2023's get_state can say saved=False and retain the
            # transient title 'New Document' after save/export even when a
            # verified native PSD exists. Never silently equate that bit with
            # on-disk persistence OR discard the in-memory source.
            info=inspect(original,None)
            names_before=await layer_names(c)
            active=original.get("activeLayer") or {}
            b=active.get("bounds") or {}
            if (str(info.get("name","")) not in (SOURCE.name, SOURCE.stem, "New Document")
                or original.get("openDocumentCount")!=1
                or int(info.get("layerCount",-1))!=2
                or info.get("hasSelection") is not False
                or set(names_before)!={STEPS[0]["name"],"Background"}
                or len(names_before)!=2
                or active.get("name")!=STEPS[0]["name"]
                or any(abs(float(b.get(k,-9999))-v)>3 for k,v in (
                     ("left",0),("top",0),("right",WIDTH),("bottom",HEIGHT)))):
                raise RuntimeError("PS_FOREIGN_OR_UNVERIFIED_ACTIVE_DOCUMENT_NO_MUTATION")
            if not SOURCE.is_file() or sha(SOURCE)!=SOURCE_SHA:
                raise RuntimeError("PS_SOURCE_SHA_CHANGED_DURING_PREFLIGHT")
            print("RED_PS_UNSAVED_FLAG_DIAG="+json.dumps({
                "original_title":info.get("name"),"reported_saved":info.get("saved"),
                "source_sha256":SOURCE_SHA,"owner":active.get("name"),
                "policy":"open_verified_copy_only_without_closing_or_modifying_original"}),flush=True)
        shutil.copy2(SOURCE,TARGET)
        if sha(TARGET)!=SOURCE_SHA:
            raise RuntimeError("PS_STAGED_COPY_SHA_MISMATCH")
        await call(c,"creative_write","creative.document.open",{"path":str(TARGET)})
        current=await state(c)
        inspect(current,TARGET.stem)
        names=await layer_names(c)
        if names.count(STEPS[0]["name"])!=1 or any(s["name"] in names for s in STEPS[1:3]):
            raise RuntimeError("PS_SOURCE_LAYER_IDENTITY_MISMATCH_NO_WRITE")
        for ordinal,part in enumerate(STEPS[1:3],2):
            print("RED_PS_3STEP_BEGIN="+json.dumps({"ordinal":ordinal,"name":part["name"]}),flush=True)
            await call(c,"creative_write","creative.layer.create",{"name":part["name"]})
            doc=await state(c)
            if (doc.get("activeLayer") or {}).get("name")!=part["name"]:
                raise RuntimeError("PS_LAYER_CREATE_NOT_READBACK")
            x,y=part["x"],part["y"]
            await call(c,"creative_write","creative.selection.rectangle",{
                "left":x,"top":y,"right":x+part["width"],"bottom":y+part["height"]})
            doc=await state(c)
            if (doc.get("document") or {}).get("hasSelection") is not True:
                raise RuntimeError("PS_SELECTION_MISSING_BEFORE_FILL")
            await call(c,"creative_authorized_write","creative.style.fill",rgb(part["fill"]),authorized=True)
            doc=await state(c)
            active=doc.get("activeLayer") or {}
            bounds=active.get("bounds") or {}
            for key,want in (("left",x),("top",y),("right",x+part["width"]),("bottom",y+part["height"])):
                if abs(float(bounds.get(key,-99999))-want)>3:
                    raise RuntimeError("PS_PAINT_GEOMETRY_MISMATCH_NO_REPLAY "+str(bounds))
            await call(c,"creative_write","creative.selection.clear")
            names=await layer_names(c)
            expected={s["name"] for s in STEPS[:ordinal]}
            if not expected.issubset(names) or len([n for n in names if n in expected])!=ordinal:
                raise RuntimeError("PS_LAYER_READBACK_INCOMPLETE_NO_REPLAY")
            before=sha(TARGET)
            await call(c,"creative_write","creative.document.save",{"path":str(TARGET),"format":"PSD"})
            if sha(TARGET)==before:
                raise RuntimeError("PS_SAVE_HAS_NO_NEW_BYTES_NO_REPLAY")
            print("RED_PS_3STEP_PERSISTED="+json.dumps({"ordinal":ordinal,"name":part["name"],
                "sha256":sha(TARGET),"bytes":TARGET.stat().st_size}),flush=True)
        await call(c,"creative_write","creative.document.export",{"path":str(PNG),"format":"PNG"})
        if not PNG.is_file() or PNG.stat().st_size<1500 or PNG.read_bytes()[:8]!=bytes((137,80,78,71,13,10,26,10)):
            raise RuntimeError("PS_NATIVE_PNG_EXPORT_NOT_VERIFIED")
        if sha(SOURCE)!=SOURCE_SHA: raise RuntimeError("PS_SOURCE_CHANGED_DURING_RESUME")
        print("RED_PS_THREE_REAL_STROKES=PASS "+json.dumps({"count":3,"of":len(STEPS),
            "psd":str(TARGET),"sha256":sha(TARGET),"png":str(PNG),
            "png_sha256":sha(PNG),"original_unchanged":True}),flush=True)

if __name__=="__main__":
    asyncio.run(main())
