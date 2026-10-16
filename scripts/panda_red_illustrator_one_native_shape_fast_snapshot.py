"""One REAL Illustrator red-poster vector background on a fresh unique .ai document.

Every host request is checked before proceeding. Readback uses the proven
single-JSX fast_snapshot instead of the C014-prone nested get_document path.
On uncertain result STOP; never replay. Existing red Illustrator checkpoint
and Photoshop/XD files are not opened or written.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path

from mcp import Client
from panda_red_poster_blueprint import STEPS, WIDTH, HEIGHT, validate

HOME = Path(os.environ["USERPROFILE"]) / "Documents" / "MCPAdobe"
RUN_ID = os.environ["GITHUB_RUN_ID"]
NAME = f"MCP_KFP4_Red_AI_Fresh_{RUN_ID}"
NATIVE = HOME / (NAME + ".ai")
PNG = HOME / (NAME + ".png")
URL = "http://127.0.0.1:8787/mcp"
PRIOR = HOME / "MCP_KFP4_Red_AI_38146162392.ai"
PRIOR_SHA = "a44991466f8e3e17ebc92a03bd168b917efaca04001655cb8932091ace085091"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def call(client: Client, tool: str, capability: str, args=None, timeout=38):
    started = time.perf_counter()
    try:
        r = await asyncio.wait_for(client.call_tool(tool, {
            "application": "illustrator", "capability": capability,
            "arguments": args or {}}), timeout=timeout)
    except Exception as exc:
        raise RuntimeError("PAN_AI_NEW_SINGLE_RESULT_UNKNOWN_DO_NOT_REPEAT " + capability) from exc
    p = r.structured_content or {}
    result = p.get("result") or {}
    print("PAN_AI_NEW_STEP=" + json.dumps({
        "capability": capability,
        "elapsed_ms": round((time.perf_counter()-started)*1000, 2),
        "tool_error": r.is_error, "ok": p.get("ok"),
        "execution": result.get("execution") if isinstance(result, dict) else None,
        "job_id": result.get("jobId") if isinstance(result, dict) else None,
    }), flush=True)
    if r.is_error or p.get("ok") is not True or not isinstance(result, dict):
        raise RuntimeError("PAN_AI_NEW_UPSTREAM_UNKNOWN_DO_NOT_REPEAT " + capability + " " + str(r.content)[:250])
    if capability != "creative.health" and result.get("execution") != "succeeded":
        raise RuntimeError("PAN_AI_NEW_UPSTREAM_NOT_SUCCEEDED_DO_NOT_REPEAT " + capability)
    return result


async def verify_idle(client):
    h = await call(client, "creative_read", "creative.health", {"probe": False, "timeout": 5}, 18)
    d = ((h.get("connection") or {}).get("data") or {})
    e, panel = d.get("execution") or {}, (d.get("layers") or {}).get("panel") or {}
    state = {"unresolved": e.get("unresolvedJobs"), "active": e.get("activeJob"),
             "waiting": e.get("waiting"), "panel": panel.get("status"),
             "busy": panel.get("busy"), "heartbeat_stale": panel.get("heartbeatStale")}
    print("PAN_AI_NEW_IDLE="+json.dumps(state), flush=True)
    if (e.get("unresolvedJobs") != [] or e.get("activeJob") is not None or
        e.get("waiting") != 0 or panel.get("status") != "ok" or
        panel.get("busy") is not False or panel.get("heartbeatStale") is True):
        raise RuntimeError("PAN_AI_NEW_HOST_NOT_IDLE_DO_NOT_WRITE")


async def snapshot(client):
    result = await call(client, "creative_read", "creative.document.fast_snapshot", {}, 33)
    data = result.get("data") or {}
    if not isinstance(data, dict) or not isinstance(data.get("hasDocument"), bool):
        raise RuntimeError("PAN_AI_NEW_SNAPSHOT_MISSING_NATIVE_DOCUMENT_ACK")
    print("PAN_AI_NEW_SNAPSHOT="+json.dumps({
        "hasDocument": data.get("hasDocument"), "name": data.get("name"),
        "width": data.get("width"), "height": data.get("height"),
        "count": data.get("pageItemCount"), "items": data.get("items", [])[:2],
    }, default=str)[:1500], flush=True)
    return data


async def main():
    validate()
    HOME.mkdir(parents=True, exist_ok=True)
    if not PRIOR.is_file() or sha(PRIOR) != PRIOR_SHA:
        raise RuntimeError("PAN_AI_NEW_PRIOR_NATIVE_CHANGED_NO_WRITES")
    if NATIVE.exists() or PNG.exists():
        raise RuntimeError("PAN_AI_NEW_TARGET_ALREADY_EXISTS_DO_NOT_REPLAY")
    async with Client(URL) as client:
        await verify_idle(client)
        blank = await snapshot(client)
        if blank["hasDocument"]:
            raise RuntimeError("PAN_AI_NEW_FOREIGN_ACTIVE_DOCUMENT_NO_WRITES")
        step = STEPS[0]
        if step["kind"] != "rectangle" or step["width"] != WIDTH or step["height"] != HEIGHT:
            raise RuntimeError("PAN_AI_NEW_BACKGROUND_BLUEPRINT_CHANGED")
        await call(client, "creative_write", "creative.document.create",
                   {"name": NAME, "width": WIDTH, "height": HEIGHT, "color_mode": "RGB"})
        created = await snapshot(client)
        if (created.get("hasDocument") is not True or
            abs(float(created.get("width", -1)) - WIDTH) > 1 or
            abs(float(created.get("height", -1)) - HEIGHT) > 1 or
            created.get("pageItemCount") != 0):
            raise RuntimeError("PAN_AI_NEW_ARTBOARD_NOT_VERIFIED_DO_NOT_RECREATE")
        await call(client, "creative_write", "creative.document.save", {"file_path": str(NATIVE)})
        if not NATIVE.is_file() or NATIVE.stat().st_size <= 1000:
            raise RuntimeError("PAN_AI_NEW_BLANK_AI_NOT_SAVED_NO_REPLAY")
        before = sha(NATIVE)
        await verify_idle(client)
        await call(client, "creative_write", "creative.shape.rectangle", {
            "name": step["name"], "x": 0, "y": 0,
            "width": WIDTH, "height": HEIGHT,
            "fill": {"r": 188, "g": 0, "b": 0}})
        painted = await snapshot(client)
        items = painted.get("items") or []
        if (painted.get("pageItemCount") != 1 or len(items) != 1 or
            items[0].get("name") != step["name"] or
            abs(float(items[0].get("width", -1)) - WIDTH) > 2 or
            abs(float(items[0].get("height", -1)) - HEIGHT) > 2):
            raise RuntimeError("PAN_AI_NEW_BACKGROUND_VECTOR_NOT_VERIFIED_DO_NOT_REPLAY " + str(items)[:350])
        await call(client, "creative_write", "creative.document.save")
        if sha(NATIVE) == before:
            raise RuntimeError("PAN_AI_NEW_AI_SAVE_DID_NOT_PERSIST_VECTOR")
        await verify_idle(client)
        await call(client, "creative_write", "creative.document.export", {
            "output_path": str(PNG), "format": "png", "scale": 1, "overwrite": False})
        if (not PNG.is_file() or PNG.stat().st_size < 1000 or
            PNG.read_bytes()[:8] != bytes((137, 80, 78, 71, 13, 10, 26, 10))):
            raise RuntimeError("PAN_AI_NEW_ACTUAL_NATIVE_EXPORT_NOT_VERIFIED")
        if sha(PRIOR) != PRIOR_SHA:
            raise RuntimeError("PAN_AI_NEW_PRIOR_NATIVE_WAS_MODIFIED")
        print("PAN_AI_NEW_FRESH_NATIVE_FIRST_SHAPE=PASS " + json.dumps({
            "component_count": 1, "target": len(STEPS), "native_ai": str(NATIVE),
            "ai_sha256": sha(NATIVE), "ai_size": NATIVE.stat().st_size,
            "native_png": str(PNG), "png_sha256": sha(PNG),
            "old_ai_preserved": True}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
