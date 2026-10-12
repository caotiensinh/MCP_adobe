"""One-shot live 880x700 red XD background via MCP + independently verified UXP Apply.

Phases are separate GitHub steps: queue -> before_apply -> after_apply.
Unknown outcomes are permanently fenced in the durable local checkpoint.
Never re-queues an operation if its checkpoint already exists.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from mcp import Client
from mcp_adobe.xd_red_poster_guard import (
    NEW_ARTBOARD_ID,
    NEW_DOCUMENT_ID,
    XdRedGuardError,
    validate_live_target,
    verify_native_files,
)

URL = "http://127.0.0.1:8787/mcp"
NAME = "01 XD KFP4 Red Background"
COLOR = "#B51F1C"
SHAPE = {"name": NAME, "x": 0, "y": 0, "width": 880, "height": 700, "fill": COLOR}
ROOT = Path(os.environ["USERPROFILE"]) / "Documents" / "MCPAdobe"
CHECKPOINT = ROOT / "MCP_KFP4_Red_XD_38205166138_first_bg.json"


def save(data: dict) -> None:
    data["checkpoint_updated_utc"] = datetime.now(timezone.utc).isoformat()
    tmp = CHECKPOINT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(tmp, CHECKPOINT)
    print("XD_RED_BG_CHECKPOINT=" + json.dumps({
        "phase": data["phase"], "operation_id": data.get("operation_id"),
        "checkpoint": str(CHECKPOINT)
    }), flush=True)


def read_checkpoint() -> dict:
    if not CHECKPOINT.is_file():
        raise RuntimeError("XD_RED_BG_CHECKPOINT_MISSING_STOP_NO_REPLAY")
    value = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    if value.get("document_id") != NEW_DOCUMENT_ID or value.get("artboard_id") != NEW_ARTBOARD_ID or value.get("name") != NAME:
        raise RuntimeError("XD_RED_BG_WRONG_CHECKPOINT_REFUSE")
    return value


async def call(client: Client, kind: str, capability: str, arguments: dict | None = None) -> dict:
    output = await asyncio.wait_for(client.call_tool(kind, {
        "application": "xd", "capability": capability, "arguments": arguments or {}
    }), timeout=11)
    result = output.structured_content
    if output.is_error or not isinstance(result, Mapping) or result.get("ok") is not True:
        raise RuntimeError("XD_RED_BG_TOOL_UNKNOWN_STOP_NO_REPLAY " + kind + " " + capability)
    data = result.get("result")
    if not isinstance(data, Mapping):
        raise RuntimeError("XD_RED_BG_TOOL_RESULT_MISSING " + capability)
    return dict(data)


async def sample(client: Client) -> tuple[dict, dict, dict]:
    health = await call(client, "creative_read", "creative.health")
    document = await call(client, "creative_read", "creative.document.info")
    scene = await call(client, "creative_read", "creative.scenegraph.list")
    return health, document, scene


def check_native() -> None:
    verify_native_files(ROOT)


async def queue() -> None:
    if CHECKPOINT.exists():
        raise RuntimeError("XD_RED_BG_CHECKPOINT_ALREADY_EXISTS_NO_DUPLICATE_QUEUE")
    check_native()
    async with Client(URL) as client:
        health, document, scene = await sample(client)
        proof = validate_live_target(health, document, scene, expected_document_id=NEW_DOCUMENT_ID)
        if proof["artboard_id"] != NEW_ARTBOARD_ID:
            raise XdRedGuardError("XD_RED_BG_NATIVE_ARTBOARD_MISMATCH")
        # The UXP rectangle_create implementation calls
        # selection.insertionParent.addChild(node). RootNode is NOT the
        # artboard and could create an unsaved/off-artboard object.
        insertion = document.get("insertionParent")
        if (not isinstance(insertion, Mapping)
            or insertion.get("type") != "Artboard"
            or insertion.get("guid") != NEW_ARTBOARD_ID):
            raise XdRedGuardError("XD_RED_BG_INSERTION_PARENT_NOT_TARGET_ARTBOARD_NO_WRITE")
        # Durable write-ahead fence before sending the only creative_write.
        record = {
            "schema": "red-xd-first-bg/v1",
            "phase": "prepared_write_outcome_unknown_until_receipt",
            "document_id": NEW_DOCUMENT_ID,
            "artboard_id": NEW_ARTBOARD_ID,
            "name": NAME,
            "color": COLOR,
            "args": SHAPE,
            "queued_by_github_run": os.environ.get("GITHUB_RUN_ID", ""),
            "operation_id": None,
            "native_checkpoint": verify_native_files(ROOT),
        }
        save(record)
        print("XD_RED_BG_FIRST_WRITE_REQUEST=ONCE", flush=True)
        # Timeout after request delivery is UNKNOWN: no retry or queue clear.
        reply = await call(client, "creative_write", "creative.shape.rectangle", SHAPE)
        operation_id = reply.get("operation_id")
        if reply.get("status") != "queued" or reply.get("pending_count") != 1 or not isinstance(operation_id, str) or not operation_id:
            raise RuntimeError("XD_RED_BG_QUEUE_ACK_NOT_EXACT_UNKNOWN_NO_REPLAY")
        record["phase"] = "queued"
        record["operation_id"] = operation_id
        save(record)
        receipt = await call(client, "creative_read", "xd.queue.status", {"operation_id": operation_id})
        health_now = await call(client, "creative_read", "creative.health")
        if receipt.get("status") != "queued" or health_now.get("pending_count") != 1:
            raise RuntimeError("XD_RED_BG_ACK_AND_QUEUE_DISAGREE_NO_APPLY")
        print("XD_RED_BG_QUEUED_RECEIPT=PASS " + operation_id, flush=True)
    check_native()


async def before_apply() -> None:
    state = read_checkpoint()
    if state.get("phase") != "queued" or not isinstance(state.get("operation_id"), str):
        raise RuntimeError("XD_RED_BG_NOT_EXACTLY_QUEUED_REFUSE_APPLY")
    check_native()
    async with Client(URL) as client:
        h, d, g = await sample(client)
        if h.get("bridge") != "connected" or h.get("pending_count") != 1:
            raise RuntimeError("XD_RED_BG_QUEUE_NOT_EXACT_ONE")
        if g.get("complete") is not True or g.get("document_id") != NEW_DOCUMENT_ID:
            raise RuntimeError("XD_RED_BG_DOCUMENT_SWITCHED")
        nodes = g.get("nodes")
        if not isinstance(nodes, list) or len(nodes) != 1 or nodes[0].get("id") != NEW_ARTBOARD_ID or nodes[0].get("children") != []:
            raise RuntimeError("XD_RED_BG_HOST_SCENE_NOT_PRISTINE")
        receipt = await call(client, "creative_read", "xd.queue.status", {"operation_id": state["operation_id"]})
        if receipt.get("status") != "queued":
            raise RuntimeError("XD_RED_BG_RECEIPT_NO_LONGER_QUEUED")
        root = d.get("insertionParent")
        if not isinstance(root, Mapping) or root.get("guid") != NEW_DOCUMENT_ID:
            raise RuntimeError("XD_RED_BG_WRONG_INSERTION_PARENT")
        print("XD_RED_BG_SAFE_FOR_ONE_GUI_APPLY=PASS " + state["operation_id"], flush=True)


async def after_apply() -> None:
    state = read_checkpoint()
    if state.get("phase") != "queued":
        raise RuntimeError("XD_RED_BG_CHECKPOINT_NOT_QUEUED_POST_APPLY")
    check_native()
    op = state["operation_id"]
    async with Client(URL) as client:
        receipt = await call(client, "creative_read", "xd.queue.status", {"operation_id": op})
        health, doc, scene = await sample(client)
        outcome = receipt.get("status")
        print("XD_RED_BG_POST_APPLY_RECEIPT=" + json.dumps({
            "operation_id": op, "status": outcome,
            "pending_count": health.get("pending_count"),
            "document_id": scene.get("document_id")
        }), flush=True)
        if outcome != "applied" or health.get("pending_count") != 0 or scene.get("complete") is not True or scene.get("document_id") != NEW_DOCUMENT_ID:
            raise RuntimeError("XD_RED_BG_APPLY_NOT_VERIFIED_UNKNOWN_NO_REPLAY")
        roots = scene.get("nodes")
        if not isinstance(roots, list) or len(roots) != 1 or roots[0].get("id") != NEW_ARTBOARD_ID:
            raise RuntimeError("XD_RED_BG_ARTBOARD_CHANGED_AFTER_APPLY")
        children = roots[0].get("children")
        if not isinstance(children, list) or len(children) != 1:
            raise RuntimeError("XD_RED_BG_EXPECT_ONE_CHILD_AFTER_APPLY")
        node = children[0]
        if node.get("type") != "Rectangle" or node.get("name") != NAME or not isinstance(node.get("id"), str):
            raise RuntimeError("XD_RED_BG_WRONG_OBJECT_CREATED")
        bounds = node.get("bounds")
        if not isinstance(bounds, Mapping) or any(abs(float(bounds[k]) - expected) > 1
                  for k, expected in (("left", 0), ("top", 0), ("right", 880), ("bottom", 700))):
            raise RuntimeError("XD_RED_BG_WRONG_BOUNDS_CREATED")
        guid = node["id"]
        applied = receipt.get("result") or {}
        if isinstance(applied, Mapping) and applied.get("guid") and applied["guid"] != guid:
            raise RuntimeError("XD_RED_BG_OPERATION_GUID_MISMATCH")
        if doc.get("insertionParent", {}).get("guid") != NEW_DOCUMENT_ID:
            raise RuntimeError("XD_RED_BG_INSERTION_PARENT_CHANGED")
        state["phase"] = "applied_not_yet_native_saved"
        state["shape_guid"] = guid
        state["live_bounds"] = dict(bounds)
        save(state)
        print("XD_RED_BG_REAL_RECTANGLE_APPLIED=PASS " + json.dumps({
            "guid": guid, "name": NAME, "fill_requested": COLOR, "bounds": bounds,
            "document_id": NEW_DOCUMENT_ID, "operation_id": op
        }), flush=True)
    check_native()


def main() -> None:
    if os.environ.get("COMPUTERNAME") != "MRCAO":
        raise RuntimeError("XD_RED_BG_NOT_MRCAO")
    phase = sys.argv[1]
    if phase not in {"queue", "before_apply", "after_apply"}:
        raise RuntimeError("XD_RED_BG_BAD_PHASE")
    asyncio.run({"queue": queue, "before_apply": before_apply, "after_apply": after_apply}[phase]())


if __name__ == "__main__":
    main()
