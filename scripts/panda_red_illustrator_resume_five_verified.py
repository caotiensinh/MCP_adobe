"""Resume one real editable Illustrator red poster .ai checkpoint from 1 to 5 shapes.

No original overwrite, one MCP mutation + readback + save per component,
no replay of unknown results, fast native Illustrator JSX scenegraph snapshot.
"""
from __future__ import annotations
import asyncio, json, os, shutil, math
from pathlib import Path
from mcp import Client
from panda_red_poster_blueprint import STEPS, WIDTH, HEIGHT, validate
from panda_red_vector_adapter import translate
from panda_red_illustrator_one_native_shape_fast_snapshot import call, verify_idle, snapshot, sha, URL

HOME=Path(os.environ["USERPROFILE"]) / "Documents" / "MCPAdobe"
SOURCE=HOME / "MCP_KFP4_Red_AI_Fresh_38157335430.ai"
SOURCE_SHA="25d46aaacc766759d11c920872d9ee1cc26861a145826143161698e97ca14b77"
RUN=os.environ["GITHUB_RUN_ID"]
TARGET=HOME / f"MCP_KFP4_Red_AI_Fresh_{RUN}_5shapes.ai"
PNG=HOME / f"MCP_KFP4_Red_AI_Fresh_{RUN}_5shapes.png"


def assert_items(data, count: int):
    if data.get("hasDocument") is not True or data.get("pageItemCount") != count:
        raise RuntimeError("PAN_AI_FIVE_WRONG_OBJECT_COUNT_NO_REPLAY")
    items=data.get("items") or []
    if len(items) != count:
        raise RuntimeError("PAN_AI_FIVE_TRUNCATED_SCENEGRAPH_NO_REPLAY")
    names=[obj.get("name") for obj in items]
    expected=[part["name"] for part in STEPS[:count]]
    if len(set(names))!=count or set(names)!=set(expected):
        raise RuntimeError("PAN_AI_FIVE_COMPONENT_NAMES_DO_NOT_MATCH "+str(names)[:300])
    for item in items:
        for key in ("width","height"):
            v=float(item.get(key,-1))
            if not math.isfinite(v) or v<=0:
                raise RuntimeError("PAN_AI_FIVE_DEGENERATE_NATIVE_GEOMETRY "+str(item)[:180])


async def main():
    validate()
    if not SOURCE.is_file() or sha(SOURCE)!=SOURCE_SHA:
        raise RuntimeError("PAN_AI_FIVE_SOURCE_SHA_MISMATCH_NO_WRITE")
    if TARGET.exists() or PNG.exists():
        raise RuntimeError("PAN_AI_FIVE_TARGET_ALREADY_EXISTS_NO_REPLAY")
    HOME.mkdir(parents=True,exist_ok=True)
    async with Client(URL) as c:
        await verify_idle(c)
        current=await snapshot(c)
        if current.get("hasDocument") is True and current.get("name") not in (SOURCE.name,SOURCE.stem):
            raise RuntimeError("PAN_AI_FIVE_FOREIGN_ACTIVE_DOCUMENT_REFUSE_WRITE")
        shutil.copy2(SOURCE,TARGET)
        if sha(TARGET)!=SOURCE_SHA:
            raise RuntimeError("PAN_AI_FIVE_STAGE_COPY_SHA_MISMATCH")
        await call(c,"creative_write","creative.document.open",{"file_path":str(TARGET)})
        opened=await snapshot(c)
        if opened.get("name") not in (TARGET.name,TARGET.stem) or int(opened.get("width",-1))!=WIDTH or int(opened.get("height",-1))!=HEIGHT:
            raise RuntimeError("PAN_AI_FIVE_OPENED_WRONG_DOCUMENT_NO_REPLAY")
        assert_items(opened,1)
        for ordinal in range(2,6):
            component=STEPS[ordinal-1]
            capability,params=translate("illustrator",component)
            print("PAN_AI_FIVE_COMPONENT_START="+json.dumps({
                "ordinal":ordinal,"name":component["name"],"capability":capability}),flush=True)
            await verify_idle(c)
            await call(c,"creative_write",capability,params)
            scene=await snapshot(c)
            assert_items(scene,ordinal)
            previous_sha=sha(TARGET)
            await call(c,"creative_write","creative.document.save",{})
            after_sha=sha(TARGET)
            if after_sha==previous_sha:
                raise RuntimeError("PAN_AI_FIVE_NATIVE_NOT_PERSISTED_NO_REPLAY")
            print("PAN_AI_FIVE_COMPONENT_SAVED=PASS "+json.dumps({
                "ordinal":ordinal,"name":component["name"],
                "page_items":scene["pageItemCount"],"sha256":after_sha,
                "file_bytes":TARGET.stat().st_size}),flush=True)
        await verify_idle(c)
        await call(c,"creative_write","creative.document.export",{
            "output_path":str(PNG),"format":"png","scale":1,"overwrite":False})
        if not PNG.is_file() or PNG.stat().st_size<1500 or PNG.read_bytes()[:8]!=bytes((137,80,78,71,13,10,26,10)):
            raise RuntimeError("PAN_AI_FIVE_NATIVE_PNG_NOT_EXPORTED")
        if sha(SOURCE)!=SOURCE_SHA:
            raise RuntimeError("PAN_AI_FIVE_IMMUTABLE_SOURCE_CHANGED")
        print("PAN_AI_FIVE_REAL_VECTOR_SHAPES=PASS "+json.dumps({
            "verified_components":5,"planned":len(STEPS),
            "native_ai":str(TARGET),"ai_sha256":sha(TARGET),
            "png":str(PNG),"png_sha256":sha(PNG),
            "source_sha_unchanged":True,"poster_quality":"PARTIAL"}),flush=True)

if __name__=="__main__":
    asyncio.run(main())
