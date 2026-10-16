"""Checkpointed live Illustrator house completion; never replays uncertain host writes.

Target: the existing Two_Story_Red_Tile_House.ai on MRCAO, at 14 objects.
Appends 15 named vector shapes (two trees, flower borders, downstairs windows
and the entrance), checks every mutation through a fresh MCP document readback,
and saves each successful checkpoint. Does not create or close documents.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import time
from pathlib import Path

from mcp import Client

DOCUMENT_NAME = "Two_Story_Red_Tile_House.ai"
ROOT = Path(os.environ["USERPROFILE"]) / "Documents" / "MCPAdobe"
TARGET = ROOT / DOCUMENT_NAME
GATEWAY = "http://127.0.0.1:8787/mcp"


def rectangle(name, x, y, width, height, rgb):
    return name, "creative.shape.rectangle", {
        "name": name, "x": x, "y": y, "width": width, "height": height,
        "fill": {"r": rgb[0], "g": rgb[1], "b": rgb[2]},
    }


def polygon(name, points, rgb):
    return name, "creative.path.create", {
        "name": name, "points": points, "closed": True,
        "fill": {"r": rgb[0], "g": rgb[1], "b": rgb[2]},
    }


STEPS = [
    rectangle("15 Left Garden Tree Trunk", 79, 414, 20, 132, (113, 76, 45)),
    polygon("16 Left Garden Tree Crown", [
        [35, 367], [49, 334], [75, 313], [104, 316], [132, 340],
        [146, 378], [131, 412], [103, 430], [70, 428], [44, 409],
    ], (64, 140, 62)),
    rectangle("17 Right Garden Tree Trunk", 813, 403, 17, 43, (115, 76, 44)),
    polygon("18 Right Garden Tree Crown", [
        [762, 370], [780, 333], [809, 309], [840, 308], [867, 336],
        [884, 375], [864, 408], [826, 422], [785, 414],
    ], (59, 137, 62)),
    rectangle("19 Left Garden Hedge", 20, 568, 126, 29, (52, 121, 53)),
    rectangle("20 Right Garden Hedge", 755, 568, 124, 29, (50, 119, 53)),
    rectangle("21 Left Flower Bed", 53, 582, 69, 10, (238, 90, 132)),
    rectangle("22 Right Flower Bed", 786, 583, 72, 9, (245, 192, 65)),
    rectangle("23 Downstairs Left Window Frame", 229, 473, 123, 97, (83, 59, 48)),
    rectangle("24 Downstairs Left Window Glass", 236, 480, 108, 82, (128, 204, 227)),
    rectangle("25 Downstairs Right Window Frame", 545, 473, 123, 97, (83, 59, 48)),
    rectangle("26 Downstairs Right Window Glass", 552, 480, 108, 82, (128, 204, 227)),
    rectangle("27 Main Entrance Frame", 416, 467, 93, 152, (81, 58, 46)),
    rectangle("28 Brown Main Entrance Door", 424, 475, 77, 144, (140, 91, 59)),
    rectangle("29 Brass Door Handle", 480, 545, 8, 8, (236, 201, 92)),
]


def check_result(response, capability):
    payload = response.structured_content
    if response.is_error or not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RuntimeError(f"UNVERIFIED_MCP_RESPONSE_{capability}: stop; do not replay")
    if (payload.get("result") or {}).get("execution") in ("unknown", "failed"):
        raise RuntimeError(f"UNKNOWN_HOST_OUTCOME_{capability}: stop; do not replay")
    return payload


async def call(client, tool, capability, arguments):
    response = await client.call_tool(tool, {
        "application": "illustrator",
        "capability": capability,
        "arguments": arguments,
    })
    return check_result(response, capability)


async def assert_idle(client):
    p = await call(client, "creative_read", "creative.health", {"probe": False, "timeout": 5})
    state = p["result"]["connection"]["data"]
    execution = state.get("execution") or {}
    panel = (state.get("layers") or {}).get("panel") or {}
    if (execution.get("unresolvedJobs")
        or execution.get("activeJob") is not None
        or execution.get("waiting") != 0
        or state.get("blocking")
        or panel.get("status") != "ok"
        or panel.get("busy") is not False
        or panel.get("activeRequestId") is not None
        or panel.get("heartbeatStale") is True):
        raise RuntimeError("ILLUSTRATOR_NOT_IDLE_NO_MUTATION")
    return state


async def inventory(client):
    p = await call(client, "creative_read", "creative.document.info", {})
    result = p.get("result") or {}
    if result.get("execution") != "succeeded":
        raise RuntimeError("DOCUMENT_READBACK_UNVERIFIED")
    data = result.get("data") or {}
    doc = data.get("document") or {}
    layers = data.get("layers") or []
    count = sum(int(layer.get("itemCount", 0)) for layer in layers)
    listed = [item.get("name") for layer in layers for item in (layer.get("items") or [])]
    return doc, count, listed


async def save_checkpoint(client, index, count):
    p = await call(client, "creative_write", "creative.document.save", {})
    if (p.get("result") or {}).get("execution") != "succeeded":
        raise RuntimeError("ILLUSTRATOR_SAVE_UNVERIFIED_DO_NOT_REPLAY")
    if not TARGET.is_file() or TARGET.stat().st_size < 1024:
        raise RuntimeError("SAVED_AI_FILE_MISSING")
    print("LANDSCAPE_SAVED=" + json.dumps({
        "shape": index, "total": count, "bytes": TARGET.stat().st_size,
        "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest(),
    }), flush=True)


async def main():
    if not TARGET.is_file() or TARGET.stat().st_size < 1024:
        raise RuntimeError("EXISTING_HOUSE_FILE_NOT_PRESENT")

    async with Client(GATEWAY) as client:
        await assert_idle(client)
        doc, count, visible = await inventory(client)
        print("LANDSCAPE_PREFLIGHT=" + json.dumps({
            "name": doc.get("name"), "width": doc.get("width"),
            "height": doc.get("height"), "count": count,
            "savedFlag": doc.get("saved"), "visible": visible,
        }), flush=True)
        if doc.get("name") != DOCUMENT_NAME or doc.get("width") != 900 or doc.get("height") != 650:
            raise RuntimeError("DIFFERENT_DOCUMENT_NO_MUTATION")

        # Resume only from independently named checkpoints, never from a guess.
        if not 14 <= count <= 29:
            raise RuntimeError("UNEXPECTED_SHAPE_COUNT_NO_MUTATION")
        if count == 14:
            previous_name = "14 Garden Front Walkway"
        else:
            previous_name = STEPS[count - 15][0]
        if previous_name not in visible:
            raise RuntimeError("PREVIOUS_CHECKPOINT_NAME_NOT_VERIFIED_NO_MUTATION")
        if count == 29:
            print("LANDSCAPE_29_OBJECTS=PASS_ALREADYGALLERY", flush=True)
        else:
            backup = ROOT / ("Two_Story_Red_Tile_House_pre_completion_"
                             + time.strftime("%Y%m%d_%H%M%S") + ".ai")
            shutil.copy2(TARGET, backup)
            if hashlib.sha256(backup.read_bytes()).digest() != hashlib.sha256(TARGET.read_bytes()).digest():
                raise RuntimeError("BACKUP_INTEGRITY_FAILED")
            print("LANDSCAPE_BACKUP=PASS bytes=" + str(backup.stat().st_size), flush=True)

        for step_number in range(max(0, count - 14), len(STEPS)):
            name, capability, args = STEPS[step_number]
            await assert_idle(client)
            print("LANDSCAPE_STROKE_BEGIN=" + json.dumps({
                "next": count + 1, "name": name, "capability": capability,
            }), flush=True)
            p = await call(client, "creative_write", capability, args)
            if (p.get("result") or {}).get("execution") != "succeeded":
                raise RuntimeError("STROKE_EXECUTION_NOT_VERIFIED_NO_REPLAY")
            doc, new_count, visible = await inventory(client)
            print("LANDSCAPE_STROKE_READBACK=" + json.dumps({
                "name": name, "count": new_count, "nameFound": name in visible,
            }), flush=True)
            if doc.get("name") != DOCUMENT_NAME or new_count != count + 1 or name not in visible:
                raise RuntimeError("STROKE_READBACK_MISMATCH_NO_REPLAY")
            count = new_count
            await assert_idle(client)
            await save_checkpoint(client, name, count)
            await asyncio.sleep(0.6)

        if count != 29:
            raise RuntimeError("LANDSCAPE_COMPLETION_MISSING")
        print("LANDSCAPE_29_OBJECTS=PASS", flush=True)
        await assert_idle(client)
        out = ROOT / ("Two_Story_Red_Tile_House_garden_29_"
                      + time.strftime("%Y%m%d_%H%M%S") + ".png")
        r = await call(client, "creative_write", "creative.document.export", {
            "output_path": str(out), "format": "png", "scale": 1, "overwrite": False,
        })
        if (r.get("result") or {}).get("execution") != "succeeded":
            raise RuntimeError("LANDSCAPE_EXPORT_UNVERIFIED")
        if not out.is_file() or out.stat().st_size < 1000:
            raise RuntimeError("LANDSCAPE_EXPORTED_PNG_MISSING")
        shutil.copyfile(out, Path.cwd() / "house_landscape_29_actual.png")
        print("LANDSCAPE_29_REAL_PNG=PASS " + json.dumps({
            "bytes": out.stat().st_size,
            "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        }), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
