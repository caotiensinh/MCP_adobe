"""Recover the proven second red Illustrator vector without repeating its write.

The exact prior job created an Illustrator object but its automatic
z_telemetry timed out; this script only observes two real objects, then
saves the already-created second object to a unique native checkpoint.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from mcp import Client

from panda_red_poster_blueprint import STEPS
from panda_red_illustrator_one_native_shape_fast_snapshot import call, sha, snapshot, verify_idle, URL

FOLDER = Path(os.environ["USERPROFILE"]) / "Documents" / "MCPAdobe"
SOURCE = FOLDER / "MCP_KFP4_Red_AI_Fresh_38157335430.ai"
TARGET = FOLDER / "MCP_KFP4_Red_AI_Fresh_38157628243_5shapes.ai"
PNG = FOLDER / "MCP_KFP4_Red_AI_Fresh_38157628243_2_verified.png"
SOURCE_SHA = "25d46aaacc766759d11c920872d9ee1cc26861a145826143161698e97ca14b77"


async def main() -> None:
    if not SOURCE.is_file() or not TARGET.is_file():
        raise RuntimeError("RECT2_RECONCILE_NATIVE_NOT_FOUND_NO_WRITE")
    if sha(SOURCE) != SOURCE_SHA or sha(TARGET) != SOURCE_SHA:
        raise RuntimeError("RECT2_RECONCILE_PERSISTED_SOURCE_CHANGED_NO_WRITE")
    if PNG.exists():
        raise RuntimeError("RECT2_RECONCILE_PNG_ALREADY_EXISTS_NO_REPLAY")

    async with Client(URL) as client:
        await verify_idle(client)
        current = await snapshot(client)
        if current.get("hasDocument") is not True:
            raise RuntimeError("RECT2_RECONCILE_NO_ACTIVE_NATIVE_DOCUMENT")
        if current.get("name") not in (TARGET.name, TARGET.stem):
            raise RuntimeError("RECT2_RECONCILE_FOREIGN_DOCUMENT_NO_WRITE")
        items = current.get("items") or []
        names = {x.get("name") for x in items if isinstance(x, dict)}
        expected = {STEPS[0]["name"], STEPS[1]["name"]}
        if current.get("pageItemCount") != 2 or len(items) != 2 or names != expected:
            raise RuntimeError("RECT2_RECONCILE_UNVERIFIED_SHAPE_SET_NO_REPLAY " + str(names)[:250])
        for x in items:
            if x.get("name") == STEPS[1]["name"]:
                if abs(float(x.get("width", -1))-880)>3 or abs(float(x.get("height", -1))-700)>3:
                    raise RuntimeError("RECT2_RECONCILE_SECOND_SHAPE_GEOMETRY_INVALID")
        print("RECT2_RECONCILE_HOST_COUNT=PASS " + json.dumps({
            "count": len(items), "names": sorted(names),
            "current_saved_sha256": sha(TARGET)}, ensure_ascii=False), flush=True)

        # A successful prior host mutation is saved exactly once. No rectangle
        # create command is issued here, even if the GUI only shows one item.
        await call(client, "creative_write", "creative.document.save", {})
        after = sha(TARGET)
        if after == SOURCE_SHA:
            raise RuntimeError("RECT2_RECONCILE_SECOND_VECTOR_NOT_PERSISTED")
        check = await snapshot(client)
        if check.get("pageItemCount") != 2 or {x.get("name") for x in check.get("items") or []} != expected:
            raise RuntimeError("RECT2_RECONCILE_POSTSAVE_SCENEGRAPH_CHANGED")
        if sha(SOURCE) != SOURCE_SHA:
            raise RuntimeError("RECT2_RECONCILE_IMMUTABLE_SOURCE_MODIFIED")
        print("RECT2_RECONCILE_NATIVE_SAVED=PASS " + json.dumps({
            "objects": 2, "target": str(TARGET), "size": TARGET.stat().st_size,
            "sha256": after}, ensure_ascii=False), flush=True)
        await verify_idle(client)
        await call(client, "creative_write", "creative.document.export", {
            "output_path": str(PNG), "format": "png", "scale": 1, "overwrite": False})
        if not PNG.is_file() or PNG.stat().st_size < 1000 or PNG.read_bytes()[:8] != bytes((137,80,78,71,13,10,26,10)):
            raise RuntimeError("RECT2_RECONCILE_PNG_EXPORT_NOT_VERIFIED")
        print("RECT2_RECONCILE_REAL_NATIVE_EXPORT=PASS " + json.dumps({
            "png": str(PNG), "size": PNG.stat().st_size,
            "sha256": sha(PNG), "source_preserved": True}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
