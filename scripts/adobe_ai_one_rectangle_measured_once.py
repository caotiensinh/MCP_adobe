"""One Illustrator rectangle, real MCP, durable no-replay journal and native AI readback.

Run only from the matching single-app MRCAO Actions workflow.
Do not rerun if any checkpoint exists: an interrupted host request may have applied.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from mcp import Client

URL = "http://127.0.0.1:8787/mcp"
ROOT = Path(os.environ["USERPROFILE"]) / "Documents" / "MCPAdobe"
RUN_ID = os.environ["GITHUB_RUN_ID"]
NAME = "MCP_RectSpeed_AI_" + RUN_ID
RECT_NAME = "speed_test_rectangle_ai_01"
OUTPUT = ROOT / (NAME + ".ai")
JOURNAL = ROOT / (NAME + ".json")
ARTIFACT_ROOT = Path(os.environ["RUNNER_TEMP"]) / "single_rectangle_ai_artifact"
ARGUMENTS = {
    "name": RECT_NAME, "x": 100, "y": 100, "width": 200,
    "height": 120, "fill": {"r": 215, "g": 48, "b": 52},
}
times_ms: dict[str, float] = {}


def checkpoint(payload: dict[str, Any], phase: str, **fields: Any) -> None:
    payload["phase"] = phase
    payload.update(fields)
    payload["recorded_utc"] = datetime.now(timezone.utc).isoformat()
    tmp = JOURNAL.with_suffix(".journal.tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, JOURNAL)
    print("AI_RECT_CHECKPOINT=" + json.dumps({"phase": phase, "run": RUN_ID}), flush=True)


async def call(client: Client, kind: str, capability: str, args: Mapping[str, Any], *, stage: str) -> dict:
    t = time.perf_counter_ns()
    try:
        answer = await asyncio.wait_for(client.call_tool(kind, {
            "application": "illustrator", "capability": capability,
            "arguments": dict(args),
        }), timeout=35 if kind == "creative_write" else 18)
    finally:
        times_ms[stage] = round((time.perf_counter_ns() - t) / 1e6, 3)
    body = answer.structured_content
    if answer.is_error or not isinstance(body, Mapping) or body.get("ok") is not True:
        raise RuntimeError("AI_RECT_UNKNOWN_OR_ERROR_NO_REPLAY " + stage)
    print("AI_RECT_MCP_STEP=" + json.dumps({
        "stage": stage, "capability": capability, "elapsed_ms": times_ms[stage],
        "ok": True,
    }), flush=True)
    return dict(body.get("result") or {})


def health_data(res: Mapping[str, Any]) -> dict:
    data = (res.get("connection") or {}).get("data") or {}
    if not isinstance(data, Mapping):
        raise RuntimeError("AI_RECT_HEALTH_RESULT_INVALID")
    return dict(data)


def require_host_idle(res: Mapping[str, Any], *, allow_no_doc: bool = False) -> None:
    data = health_data(res)
    exe = data.get("execution") or {}
    panel = (data.get("layers") or {}).get("panel") or {}
    if exe.get("unresolvedJobs") or exe.get("activeJob") is not None or exe.get("waiting") not in (None, 0):
        raise RuntimeError("AI_RECT_HOST_FENCED_OR_BUSY")
    if panel.get("status") != "ok" or panel.get("busy") is not False or panel.get("activeRequestId") is not None:
        raise RuntimeError("AI_RECT_ILLUSTRATOR_PANEL_NOT_IDLE")
    if data.get("blocking") is not None:
        raise RuntimeError("AI_RECT_HOST_BLOCKING_FENCE")
    if allow_no_doc and (data.get("layers") or {}).get("document", {}).get("status") != "none_open":
        raise RuntimeError("AI_RECT_FOREIGN_OR_UNSAVED_DOCUMENT_PRESENT")


def inspect_document(res: Mapping[str, Any], expected_count: int) -> bool:
    data = res.get("data") or {}
    doc = data.get("document") or {}
    if not isinstance(doc, Mapping) or doc.get("name") not in (NAME, NAME + ".ai"):
        raise RuntimeError("AI_RECT_DOCUMENT_NAME_WRONG_NO_FURTHER_MUTATION")
    layers = data.get("layers") or []
    if not isinstance(layers, list) or not layers:
        raise RuntimeError("AI_RECT_DOCUMENT_LAYERS_UNKNOWN")
    count = sum(int(layer.get("itemCount", -1)) for layer in layers)
    if count != expected_count:
        raise RuntimeError("AI_RECT_ITEM_COUNT_MISMATCH " + str(count))
    return any(any(
        item.get("name") == RECT_NAME for item in layer.get("items", [])
        if isinstance(item, Mapping)
    ) for layer in layers)


async def main() -> None:
    if os.environ.get("COMPUTERNAME") != "MRCAO":
        raise RuntimeError("AI_RECT_UNAPPROVED_HOST")
    ROOT.mkdir(parents=True, exist_ok=True)
    if JOURNAL.exists() or OUTPUT.exists():
        raise RuntimeError("AI_RECT_PRIOR_CHECKPOINT_EXISTS_REFUSE_ANY_REPLAY")
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    state = {
        "schema": "mcp-adobe-single-rectangle-v1",
        "application": "illustrator", "run_id": RUN_ID, "document": NAME,
        "shape": ARGUMENTS, "native_path": str(OUTPUT),
        "rectangle_verified": False, "native_saved_verified": False,
    }
    async with Client(URL) as client:
        h = await call(client, "creative_read", "creative.health",
                       {"probe": False, "timeout": 5}, stage="health_before_ms")
        require_host_idle(h, allow_no_doc=True)
        probed = await call(client, "creative_read", "creative.health",
                            {"probe": True, "timeout": 12}, stage="trusted_probe_ms")
        require_host_idle(probed, allow_no_doc=True)
        if (health_data(probed).get("layers") or {}).get("illustrator", {}).get("status") != "ok":
            raise RuntimeError("AI_RECT_TRUSTED_ILLUSTRATOR_NOT_READY")
        checkpoint(state, "create_document_request_outcome_unknown")
        await call(client, "creative_write", "creative.document.create",
                   {"width": 640, "height": 400, "color_mode": "RGB", "name": NAME},
                   stage="create_document_ms")
        checkpoint(state, "document_create_ack")
        before = await call(client, "creative_read", "creative.document.info",
                            {}, stage="document_readback_before_ms")
        inspect_document(before, 0)
        checkpoint(state, "rectangle_request_outcome_unknown")
        creation = await call(client, "creative_write", "creative.shape.rectangle",
                              ARGUMENTS, stage="rectangle_command_ms")
        checkpoint(state, "rectangle_ack", rect_tool_ack=creation)
        after = await call(client, "creative_read", "creative.document.info",
                           {}, stage="rectangle_readback_ms")
        named = inspect_document(after, 1)
        if not named:
            raise RuntimeError("AI_RECT_ONE_ITEM_BUT_OBJECT_NAME_NOT_VERIFIED")
        state["rectangle_verified"] = True
        checkpoint(state, "rectangle_verified_pending_native_save")
        # Only test-owned file. Never overwrite a source user document.
        if OUTPUT.exists():
            raise RuntimeError("AI_RECT_OUTPUT_PATH_NOW_EXISTS_NO_SAVE")
        checkpoint(state, "save_request_outcome_unknown")
        await call(client, "creative_write", "creative.document.save",
                   {"path": str(OUTPUT)}, stage="native_save_ms")
        if not OUTPUT.is_file() or OUTPUT.stat().st_size < 1000:
            raise RuntimeError("AI_RECT_NATIVE_SAVE_ACK_WITHOUT_FILE")
        digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
        state["native_saved_verified"] = True
        state["native_sha256"] = digest
        state["native_size"] = OUTPUT.stat().st_size
        state["timings_ms"] = times_ms
        checkpoint(state, "complete_rectangle_and_native_verified")
        shutil.copy2(OUTPUT, ARTIFACT_ROOT / OUTPUT.name)
        print("AI_RECT_SINGLE_NATIVE_PASS=" + json.dumps({
            "sha256": digest, "bytes": state["native_size"],
            "rectangle_name": RECT_NAME, "timings_ms": times_ms,
        }), flush=True)
    shutil.copy2(JOURNAL, ARTIFACT_ROOT / JOURNAL.name)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        if JOURNAL.exists():
            ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
            shutil.copy2(JOURNAL, ARTIFACT_ROOT / JOURNAL.name)
