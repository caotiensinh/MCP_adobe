"""Native Photoshop Panda poster checkpoint engine: one verified component at a time.

Guarantees: exact SHA of immutable input, unique output, one Adobe operation per
shape part, no automatic replay on timeout, one layer per component, readback
after each mutation and native save after each component.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
from pathlib import Path

from mcp import Client
if __package__:
    from .panda_red_poster_blueprint import STEPS, WIDTH, HEIGHT, validate
    from .panda_red_photoshop_resume_3shapes import call, sha, state, layer_names, inspect, rgb
    from .panda_red_photoshop_vector_fill import compile_path_fill
    from .panda_red_photoshop_resume_5shapes import native_polygon
else:
    from panda_red_poster_blueprint import STEPS, WIDTH, HEIGHT, validate
    from panda_red_photoshop_resume_3shapes import call, sha, state, layer_names, inspect, rgb
    from panda_red_photoshop_vector_fill import compile_path_fill
    from panda_red_photoshop_resume_5shapes import native_polygon

ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
SOURCE_NAME=os.environ["RED_PS_SOURCE_NAME"]
SOURCE_SHA=os.environ["RED_PS_SOURCE_SHA"].lower()
END=int(os.environ["RED_PS_END"])
START=int(os.environ["RED_PS_START"])
SOURCE=ROOT/SOURCE_NAME
RUN=os.environ["GITHUB_RUN_ID"]
TARGET=ROOT/f"MCP_KFP4_Red_PS_{RUN}_{END}shapes.psd"
PNG=ROOT/f"MCP_KFP4_Red_PS_{RUN}_{END}shapes.png"
URL="http://127.0.0.1:8787/mcp"

def preflight() -> None:
    validate()
    if not (2 <= START <= END <= len(STEPS)) or END-START+1>20:
        raise RuntimeError("RED_PS_RANGE_OUTSIDE_SAFE_20_COMPONENT_BATCH")
    if not SOURCE_NAME.startswith("MCP_KFP4_Red_PS_") or not SOURCE_NAME.endswith(".psd"):
        raise RuntimeError("RED_PS_BAD_SOURCE_IDENTITY")
    if len(SOURCE_SHA)!=64 or any(c not in "0123456789abcdef" for c in SOURCE_SHA):
        raise RuntimeError("RED_PS_BAD_EXPECTED_CHECKSUM")
    if SOURCE.is_file() is False or sha(SOURCE)!=SOURCE_SHA:
        raise RuntimeError("RED_PS_IMMUTABLE_INPUT_SHA_MISMATCH")
    if TARGET.exists() or PNG.exists():
        raise RuntimeError("RED_PS_RANGE_OUTPUT_ALREADY_EXISTS_NO_REPLAY")
    if START!=len({x["name"] for x in STEPS[:START-1]})+1:
        raise RuntimeError("RED_PS_INVALID_COMPONENT_IDENTITIES")

async def paint(c,part,ordinal):
    if part["kind"]=="text":
        return await paint_text(c,part,ordinal)
    await call(c,"creative_write","creative.layer.create",{"name":part["name"]})
    before=await state(c)
    if (before.get("activeLayer") or {}).get("name")!=part["name"]:
        raise RuntimeError("RED_PS_RANGE_NEW_LAYER_NOT_ACTIVE_NO_REPLAY")
    if part["kind"]=="path":
        source,bounds=compile_path_fill(part,expected_doc=TARGET.name)
        await native_polygon(c,source,bounds)
    elif part["kind"] in ("ellipse","rectangle"):
        x,y=float(part["x"]),float(part["y"])
        bounds={"left":x,"top":y,"right":x+part["width"],"bottom":y+part["height"]}
        await call(c,"creative_write","creative.selection."+part["kind"],bounds)
        selected=await state(c)
        if (selected.get("document") or {}).get("hasSelection") is not True:
            raise RuntimeError("RED_PS_RANGE_SELECTION_UNVERIFIED_NO_FILL")
        await call(c,"creative_authorized_write","creative.style.fill",rgb(part["fill"]),authorized=True)
        await call(c,"creative_write","creative.selection.clear")
    else:
        raise RuntimeError("RED_PS_RANGE_UNSUPPORTED_COMPONENT_KIND_NO_WRITE")
    after=await state(c)
    actual=(after.get("activeLayer") or {}).get("bounds") or {}
    if (after.get("activeLayer") or {}).get("name")!=part["name"]:
        raise RuntimeError("RED_PS_RANGE_ACTIVE_LAYER_CHANGED")
    for key,want in bounds.items():
        if abs(float(actual.get(key,-99999))-want)>4:
            raise RuntimeError("RED_PS_RANGE_PIXEL_BOUNDS_MISMATCH_NO_REPLAY "+str(actual))
    if (after.get("document") or {}).get("hasSelection") is not False:
        raise RuntimeError("RED_PS_RANGE_SELECTION_STILL_ACTIVE")
    names=await layer_names(c)
    expected={s["name"] for s in STEPS[:ordinal]}
    if not expected.issubset(names) or len([x for x in names if x in expected])!=ordinal:
        raise RuntimeError("RED_PS_RANGE_MISSING_OR_DUPLICATE_LAYER_AFTER_WRITE")
    previous=sha(TARGET)
    await call(c,"creative_write","creative.document.save",{"path":str(TARGET),"format":"PSD"})
    updated=sha(TARGET)
    if previous==updated:
        raise RuntimeError("RED_PS_RANGE_PSD_NOT_PERSISTED")
    print("RED_PS_COMPONENT_PERSISTED="+json.dumps({
        "ordinal":ordinal,"name":part["name"],"kind":part["kind"],
        "bounds":actual,"source_sha256":previous,"sha256":updated,
        "bytes":TARGET.stat().st_size},ensure_ascii=False),flush=True)

async def paint_text(c,part,ordinal):
    # Photoshop creates an editable native Type layer itself.
    params={"text":str(part["text"]),"x":float(part["x"]),"y":float(part["y"]),
            "fontSize":float(part["fontSize"]),**rgb(part["fill"])}
    await call(c,"creative_write","creative.text.create",params)
    initial=await state(c)
    active=initial.get("activeLayer") or {}
    if "TEXT" not in str(active.get("kind","")).upper():
        raise RuntimeError("RED_PS_RANGE_TEXT_LAYER_KIND_UNVERIFIED_NO_REPLAY")
    await call(c,"creative_write","creative.layer.rename",{"name":part["name"]})
    after=await state(c)
    layer=after.get("activeLayer") or {}
    bounds=layer.get("bounds") or {}
    if layer.get("name")!=part["name"]:
        raise RuntimeError("RED_PS_RANGE_TEXT_NAME_NOT_VERIFIED")
    # Point text uses a baseline anchor; check actual visible glyph bounds.
    if (float(bounds.get("right",-999))-float(bounds.get("left",0))<=0 or
        float(bounds.get("bottom",-999))-float(bounds.get("top",0))<=0):
        raise RuntimeError("RED_PS_RANGE_TEXT_GLYPH_BOUNDS_DEGENERATE")
    names=await layer_names(c)
    expected={s["name"] for s in STEPS[:ordinal]}
    if not expected.issubset(names) or len([n for n in names if n in expected])!=ordinal:
        raise RuntimeError("RED_PS_RANGE_TEXT_LAYER_READBACK_INCOMPLETE")
    before=sha(TARGET)
    await call(c,"creative_write","creative.document.save",{"path":str(TARGET),"format":"PSD"})
    after_sha=sha(TARGET)
    if after_sha==before:
        raise RuntimeError("RED_PS_RANGE_TEXT_PSD_NOT_PERSISTED")
    print("RED_PS_COMPONENT_PERSISTED="+json.dumps({
        "ordinal":ordinal,"name":part["name"],"kind":"text",
        "bounds":bounds,"source_sha256":before,"sha256":after_sha,
        "bytes":TARGET.stat().st_size},ensure_ascii=False),flush=True)

async def main() -> None:
    preflight()
    ROOT.mkdir(parents=True,exist_ok=True)
    async with Client(URL) as c:
        await call(c,"creative_read","creative.health")
        original=await state(c)
        if original.get("hasDocument"):
            original_document=inspect(original,None)
            if original_document.get("name") not in (SOURCE.name,SOURCE.stem):
                raise RuntimeError("RED_PS_RANGE_FOREIGN_ACTIVE_DOCUMENT_NO_MUTATION")
            existing=await layer_names(c)
            expected={s["name"] for s in STEPS[:START-1]}|{"Background"}
            if set(existing)!=expected or len(existing)!=START:
                raise RuntimeError("RED_PS_RANGE_SOURCE_ACTIVE_SCENE_UNEXPECTED")
        shutil.copy2(SOURCE,TARGET)
        if sha(TARGET)!=SOURCE_SHA:
            raise RuntimeError("RED_PS_RANGE_STAGE_SHA_BAD")
        await call(c,"creative_write","creative.document.open",{"path":str(TARGET)})
        active=await state(c)
        inspect(active,TARGET.stem)
        names=await layer_names(c)
        expected={s["name"] for s in STEPS[:START-1]}|{"Background"}
        if set(names)!=expected or len(names)!=START:
            raise RuntimeError("RED_PS_RANGE_STAGED_SCENE_NOT_VERIFIED")
        for ordinal in range(START,END+1):
            part=STEPS[ordinal-1]
            print("RED_PS_RANGE_COMPONENT_START="+json.dumps({
                "ordinal":ordinal,"name":part["name"],"kind":part["kind"]}),flush=True)
            await paint(c,part,ordinal)
        await call(c,"creative_write","creative.document.export",{"path":str(PNG),"format":"PNG"})
        if not PNG.is_file() or PNG.stat().st_size<1500 or PNG.read_bytes()[:8]!=bytes((137,80,78,71,13,10,26,10)):
            raise RuntimeError("RED_PS_RANGE_NATIVE_PNG_NOT_VERIFIED")
        if sha(SOURCE)!=SOURCE_SHA:
            raise RuntimeError("RED_PS_RANGE_INPUT_MUTATED")
        print("RED_PS_RANGE_NATIVE=PASS "+json.dumps({
          "from":START,"through":END,"completed":END,"planned":len(STEPS),
          "psd":str(TARGET),"psd_sha256":sha(TARGET),"png":str(PNG),"png_sha256":sha(PNG),
          "native_source_immutable":True,"visual_similarity":"UNVERIFIED"}),flush=True)

if __name__=="__main__":
    asyncio.run(main())
