"""Improve red poster typography on a new immutable copy of the 60-layer PSD.

Each existing native Type layer is selected by exact unique name, scaled,
positioned using observed live bounds, saved, and read back. No raster imports,
no layer recreation, and no replay of ambiguous Photoshop MCP mutations.
"""
from __future__ import annotations
import asyncio, json, os, shutil
from pathlib import Path
from mcp import Client
from panda_red_poster_blueprint import STEPS, WIDTH, HEIGHT, validate
from panda_red_photoshop_resume_3shapes import call, sha, state, layer_names, inspect

ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
SOURCE=ROOT/"MCP_KFP4_Red_PS_38151318908_60shapes.psd"
SOURCE_SHA="8b5c0c0702ee7e2953f479563550956dee66838d7dd554bacc141db51f715337"
RUN=os.environ["GITHUB_RUN_ID"]
TARGET=ROOT/f"MCP_KFP4_Red_PS_{RUN}_polished.psd"
PNG=ROOT/f"MCP_KFP4_Red_PS_{RUN}_polished.png"
URL="http://127.0.0.1:8787/mcp"
# Target top-left coordinate in the real poster artboard, not a point-text baseline.
MOVES=(
    (57,135,150,765),
    (58,165,56,866),
    (59,130,360,1030),
)

def valid_bounds(d):
    out={}
    for key in ("left","top","right","bottom"):
        try:out[key]=float(d[key])
        except (KeyError,TypeError,ValueError) as exc:
            raise RuntimeError("RED_PS_TITLE_MISSING_BOUNDS") from exc
    if out["right"]<=out["left"] or out["bottom"]<=out["top"]:
        raise RuntimeError("RED_PS_TITLE_DEGENERATE_BOUNDS")
    return out

async def move_text(c,ordinal,scale,desired_left,desired_top):
    part=STEPS[ordinal-1]
    label=part["name"]
    await call(c,"creative_write","creative.layer.select",{"name":label})
    before=await state(c)
    layer=before.get("activeLayer") or {}
    old=valid_bounds(layer.get("bounds") or {})
    if layer.get("name")!=label or "TEXT" not in str(layer.get("kind","")).upper():
        raise RuntimeError("RED_PS_TITLE_SELECTED_WRONG_LAYER_STOP")
    await call(c,"creative_write","creative.object.scale",{"scalePercent":scale,"centerAnchor":True})
    scaled=await state(c)
    item=scaled.get("activeLayer") or {}
    big=valid_bounds(item.get("bounds") or {})
    if item.get("name")!=label or "TEXT" not in str(item.get("kind","")).upper():
        raise RuntimeError("RED_PS_TITLE_SCALE_CHANGED_LAYER")
    if big["right"]-big["left"] < (scale/100-0.15)*(old["right"]-old["left"]):
        raise RuntimeError("RED_PS_TITLE_SCALE_INSUFFICIENT_STOP")
    dx=round(desired_left-big["left"],2)
    dy=round(desired_top-big["top"],2)
    if abs(dx)>600 or abs(dy)>600:
        raise RuntimeError("RED_PS_TITLE_UNSAFE_TRANSLATION_NO_WRITE")
    await call(c,"creative_write","creative.object.move",{"deltaX":dx,"deltaY":dy})
    moved=await state(c)
    final=moved.get("activeLayer") or {}
    bounds=valid_bounds(final.get("bounds") or {})
    if final.get("name")!=label or "TEXT" not in str(final.get("kind","")).upper():
        raise RuntimeError("RED_PS_TITLE_MOVE_CHANGED_LAYER")
    if abs(bounds["left"]-desired_left)>3 or abs(bounds["top"]-desired_top)>3:
        raise RuntimeError("RED_PS_TITLE_ACTUAL_POSITION_WRONG_NO_REPLAY "+str(bounds))
    if bounds["right"]>WIDTH+2 or bounds["bottom"]>HEIGHT+3:
        raise RuntimeError("RED_PS_TITLE_OUT_OF_ARTBOARD_NO_REPLAY "+str(bounds))
    names=await layer_names(c)
    expected={step["name"] for step in STEPS}
    if len(names)!=61 or set(names)!=expected|{"Background"}:
        raise RuntimeError("RED_PS_TITLE_LAYER_IDENTITY_NOT_PRESERVED")
    previous=sha(TARGET)
    await call(c,"creative_write","creative.document.save",{"path":str(TARGET),"format":"PSD"})
    newsha=sha(TARGET)
    if previous==newsha:
        raise RuntimeError("RED_PS_TITLE_SAVE_UNVERIFIED")
    print("RED_PS_TITLE_REPOSITIONED=PASS "+json.dumps({"ordinal":ordinal,"name":label,
        "old":old,"scaled":big,"new":bounds,"scale_percent":scale,"sha256":newsha}),flush=True)

async def main():
    validate()
    if sha(SOURCE)!=SOURCE_SHA or not SOURCE.is_file():
        raise RuntimeError("RED_PS_TITLE_IMMUTABLE_60_SOURCE_MISMATCH")
    if TARGET.exists() or PNG.exists():
        raise RuntimeError("RED_PS_TITLE_OUTPUT_EXISTS_NO_REPLAY")
    async with Client(URL) as c:
        await call(c,"creative_read","creative.health")
        current=await state(c)
        if current.get("hasDocument"):
            info=inspect(current,None)
            if info.get("name") not in (SOURCE.name,SOURCE.stem):
                raise RuntimeError("RED_PS_TITLE_FOREIGN_ACTIVE_DOCUMENT")
            names=await layer_names(c)
            if set(names)!={s["name"] for s in STEPS}|{"Background"} or len(names)!=61:
                raise RuntimeError("RED_PS_TITLE_FOREIGN_SOURCE_LAYERS")
        shutil.copy2(SOURCE,TARGET)
        if sha(TARGET)!=SOURCE_SHA:
            raise RuntimeError("RED_PS_TITLE_STAGED_COPY_SHA_BAD")
        await call(c,"creative_write","creative.document.open",{"path":str(TARGET)})
        staged=await state(c)
        inspect(staged,TARGET.stem)
        names=await layer_names(c)
        if len(names)!=61 or set(names)!={s["name"] for s in STEPS}|{"Background"}:
            raise RuntimeError("RED_PS_TITLE_STAGED_LAYER_SET_WRONG")
        for ordinal,scale,x,y in MOVES:
            await move_text(c,ordinal,scale,x,y)
        await call(c,"creative_write","creative.document.export",{"path":str(PNG),"format":"PNG"})
        if (not PNG.is_file() or PNG.stat().st_size<2000 or
            PNG.read_bytes()[:8]!=bytes((137,80,78,71,13,10,26,10))):
            raise RuntimeError("RED_PS_TITLE_EXPORT_INVALID")
        if sha(SOURCE)!=SOURCE_SHA:
            raise RuntimeError("RED_PS_TITLE_ORIGINAL_CHANGED")
        print("RED_PS_POLISHED_NATIVE=PASS "+json.dumps({
          "psd":str(TARGET),"psd_sha256":sha(TARGET),
          "png":str(PNG),"png_sha256":sha(PNG),"editable_native_type_layers":3,
          "drawn_components":60,"source_unchanged":True}),flush=True)

if __name__=="__main__":
    asyncio.run(main())
