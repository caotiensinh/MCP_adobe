"""Resume VERIFIED red Photoshop 3-part PSD; append two independent filled paths.

No image import, no bulk native script, no silent replay of an ambiguous write.
The source is immutable. Two Bézier contours are individually submitted,
read back, and saved to a unique work PSD before Adobe PNG export.
"""
from __future__ import annotations
import asyncio
import json
import os
import shutil
from pathlib import Path
from mcp import Client
from panda_red_poster_blueprint import STEPS,WIDTH,HEIGHT,validate
from panda_red_photoshop_resume_3shapes import call,sha,state,layer_names,inspect
from panda_red_photoshop_vector_fill import compile_path_fill

ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
SOURCE=ROOT/"MCP_KFP4_Red_PS_38147544140_3shapes.psd"
SOURCE_SHA="9396e3f3a0f3cabbc1bc279524fafa8b3e6ee08f192ccc56a34cc53fc5ac618e"
RUN=os.environ["GITHUB_RUN_ID"]
TARGET=ROOT/f"MCP_KFP4_Red_PS_{RUN}_5shapes.psd"
PNG=ROOT/f"MCP_KFP4_Red_PS_{RUN}_5shapes.png"
URL="http://127.0.0.1:8787/mcp"

async def native_polygon(c,source,expected_bounds):
    # Native-script permission is explicit for exactly one named, prechecked
    # vector shape. The capability is higher risk than a regular MCP write.
    params={"application":"photoshop","capability":"photoshop.execute_script",
        "arguments":{"code":source,"timeout_ms":25000},"allow_native_script":True}
    try:
        result=await asyncio.wait_for(c.call_tool("creative_authorized_write",params),timeout=33)
    except Exception as exc:
        raise RuntimeError("RED_PS_VECTOR_OUTCOME_UNKNOWN_NO_REPLAY") from exc
    data=result.structured_content or {}
    if result.is_error or data.get("ok") is not True or data.get("outcome") in ("unknown","failed"):
        raise RuntimeError("RED_PS_VECTOR_EXECUTION_UNVERIFIED_NO_REPLAY "+str(result.content)[:330])
    print("RED_PS_NATIVE_SINGLE_COMPONENT_ACK="+json.dumps({
        "outcome":data.get("outcome"),
        "result_excerpt":str(data.get("result"))[:200],"expected_bounds":expected_bounds}),flush=True)

async def main():
    validate()
    if any(part["kind"]!="path" for part in STEPS[3:5]):
        raise RuntimeError("RED_PS_BLUEPRINT_VECTOR_STEPS_CHANGED")
    if not SOURCE.is_file() or sha(SOURCE)!=SOURCE_SHA:
        raise RuntimeError("RED_PS_3SHAPES_SOURCE_SHA_MISMATCH_NO_WRITE")
    if TARGET.exists() or PNG.exists():
        raise RuntimeError("RED_PS_5SHAPES_OUTPUT_ALREADY_EXISTS_NO_REPLAY")
    ROOT.mkdir(parents=True,exist_ok=True)
    async with Client(URL) as c:
        await call(c,"creative_read","creative.health")
        current=await state(c)
        if current.get("hasDocument"):
            d=inspect(current,None)
            if d.get("name") not in (SOURCE.name,SOURCE.stem):
                raise RuntimeError("RED_PS_FOREIGN_ACTIVE_DOCUMENT_REFUSE_GUI_MUTATION")
            existing=await layer_names(c)
            expected={p["name"] for p in STEPS[:3]}|{"Background"}
            if set(existing)!=expected or len(existing)!=4:
                raise RuntimeError("RED_PS_3SHAPES_ACTIVE_LAYER_SET_UNEXPECTED")
        shutil.copy2(SOURCE,TARGET)
        if sha(TARGET)!=SOURCE_SHA:
            raise RuntimeError("RED_PS_5SHAPES_CHECKPOINT_COPY_SHA_BAD")
        await call(c,"creative_write","creative.document.open",{"path":str(TARGET)})
        document=await state(c)
        inspect(document,TARGET.stem)
        existing=await layer_names(c)
        if set(existing)!={p["name"] for p in STEPS[:3]}|{"Background"} or len(existing)!=4:
            raise RuntimeError("RED_PS_5SHAPES_STAGED_SOURCE_LAYER_MISMATCH")
        for ordinal,part in enumerate(STEPS[3:5],4):
            source,bounds=compile_path_fill(part,expected_doc=TARGET.name)
            print("RED_PS_5STEP_BEGIN="+json.dumps({"ordinal":ordinal,"name":part["name"],
                "vertices_script_bytes":len(source),"target_bounds":bounds}),flush=True)
            await call(c,"creative_write","creative.layer.create",{"name":part["name"]})
            current=await state(c)
            if (current.get("activeLayer") or {}).get("name")!=part["name"]:
                raise RuntimeError("RED_PS_5STEP_ACTIVE_LAYER_NOT_VERIFIED")
            await native_polygon(c,source,bounds)
            current=await state(c)
            actual=(current.get("activeLayer") or {}).get("bounds") or {}
            for key,want in bounds.items():
                if abs(float(actual.get(key,-99999))-want)>3.5:
                    raise RuntimeError("RED_PS_NATIVE_VECTOR_PIXEL_BOUNDS_MISMATCH_NO_REPLAY "+str(actual))
            if (current.get("document") or {}).get("hasSelection") is not False:
                raise RuntimeError("RED_PS_PATH_SELECTION_NOT_RELEASED")
            existing=await layer_names(c)
            expected={p["name"] for p in STEPS[:ordinal]}
            if len([name for name in existing if name in expected])!=ordinal or not expected.issubset(existing):
                raise RuntimeError("RED_PS_NATIVE_PATH_LAYER_READBACK_INCOMPLETE_NO_REPLAY")
            before=sha(TARGET)
            await call(c,"creative_write","creative.document.save",{"path":str(TARGET),"format":"PSD"})
            after=sha(TARGET)
            if after==before:
                raise RuntimeError("RED_PS_NATIVE_PATH_NOT_PERSISTED_NO_REPLAY")
            print("RED_PS_VECTOR_PART_PERSISTED="+json.dumps({
                "ordinal":ordinal,"name":part["name"],"bounds":actual,"bytes":TARGET.stat().st_size,
                "sha256":after}),flush=True)
        await call(c,"creative_write","creative.document.export",{"path":str(PNG),"format":"PNG"})
        if not PNG.exists() or PNG.stat().st_size<1500 or PNG.read_bytes()[:8]!=bytes((137,80,78,71,13,10,26,10)):
            raise RuntimeError("RED_PS_5SHAPES_NATIVE_EXPORT_MISSING")
        if sha(SOURCE)!=SOURCE_SHA:
            raise RuntimeError("RED_PS_3SHAPES_SOURCE_MODIFIED_DURING_RESUME")
        print("RED_PS_FIVE_REAL_STROKES=PASS "+json.dumps({
            "completed":5,"total":len(STEPS),"psd":str(TARGET),"psd_sha256":sha(TARGET),
            "png":str(PNG),"png_sha256":sha(PNG),"original_unchanged":True}),flush=True)

if __name__=="__main__":
    asyncio.run(main())
