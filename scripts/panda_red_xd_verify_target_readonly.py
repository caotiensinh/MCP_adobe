"""Inspect live red XD draft; never send creative_write or GUI input.

Usage (MRCAO Session 1, with gateway running):
  uv run python scripts/panda_red_xd_verify_target_readonly.py --discover
  uv run python scripts/panda_red_xd_verify_target_readonly.py --expected-document-id <live-pinned-uuid>

Discovery reports evidence but NEVER sets write_ready. A later invocation with
explicit pinned UUID, matching scenegraph + native SHA + empty 880x700 artboard
is required before the first queue operation. Do not replay unknown work.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from mcp import Client
from mcp_adobe.xd_red_poster_guard import (
    OLD_DOCUMENT_ID,
    XdRedGuardError,
    validate_live_target,
    verify_native_files,
)

MCP_URL = "http://127.0.0.1:8787/mcp"
CAPABILITIES = ("creative.health", "creative.document.info", "creative.scenegraph.list")


def _context() -> Path:
    if os.getenv("COMPUTERNAME") != "MRCAO":
        raise XdRedGuardError("XD_RED_NOT_APPROVED_MRCAO_HOST")
    return Path(os.environ["USERPROFILE"]) / "Documents" / "MCPAdobe"


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
    tmp.replace(path)


async def _read(client: Client, cap: str) -> tuple[Mapping[str, Any], float]:
    start = time.perf_counter()
    result = await asyncio.wait_for(client.call_tool("creative_read", {
        "application": "xd", "capability": cap, "arguments": {},
    }), timeout=12)
    latency_ms = round((time.perf_counter() - start) * 1000, 3)
    response = result.structured_content
    if (result.is_error or not isinstance(response, Mapping)
            or response.get("ok") is not True or not isinstance(response.get("result"), Mapping)):
        raise XdRedGuardError("XD_RED_LIVE_READ_NOT_VERIFIED: " + cap)
    return response["result"], latency_ms


async def inspect(*, expected_document_id: str | None, report: Path) -> None:
    proof: dict[str, Any] = {
        "application": "xd",
        "mode": "bind" if expected_document_id else "discovery",
        "read_only": True,
        "new_native_writes": 0,
        "bridge_gui_actions": 0,
        "ready_for_first_write": False,
        "github_run_id": os.getenv("GITHUB_RUN_ID"),
        "stages": [],
    }
    try:
        proof["native_before"] = verify_native_files(_context())
        observations: dict[str, Mapping[str, Any]] = {}
        async with asyncio.timeout(46):
            async with Client(MCP_URL) as client:
                for capability in CAPABILITIES:
                    result, latency = await _read(client, capability)
                    observations[capability] = result
                    proof["stages"].append({
                        "capability": capability, "latency_ms": latency, "verified_read": True,
                    })
        document = observations["creative.document.info"]
        scene = observations["creative.scenegraph.list"]
        health = observations["creative.health"]
        root_node = document.get("insertionParent")
        native_root_guid = root_node.get("guid") if isinstance(root_node, Mapping) else None
        proof["observed_document_id"] = document.get("id") or document.get("document_id") or native_root_guid
        proof["scene_document_id"] = scene.get("document_id")
        proof["scene_complete"] = scene.get("complete") is True
        proof["artboard_count"] = len(scene.get("nodes") or [])
        proof["pending_count"] = health.get("pending_count")
        proof["bridge"] = health.get("bridge")
        proof["native_after"] = verify_native_files(_context())
        if proof["native_before"] != proof["native_after"]:
            raise XdRedGuardError("XD_RED_NATIVE_CHANGED_DURING_PREFLIGHT")
        if not expected_document_id:
            if proof["observed_document_id"] == OLD_DOCUMENT_ID:
                raise XdRedGuardError("XD_RED_OLD_DOCUMENT_STILL_BOUND")
            if not proof["observed_document_id"] or proof["scene_document_id"] != proof["observed_document_id"]:
                raise XdRedGuardError("XD_RED_DISCOVERY_IDENTITIES_MISMATCH")
            # Positive discovery is not permission to write: UUID must be
            # pinned, reviewed and confirmed in a separate invocation.
            proof["outcome"] = "DISCOVERED_NOT_AUTHORIZED_FOR_WRITE"
            print("XD_RED_DISCOVERY_UUID=" + str(proof["observed_document_id"]), flush=True)
        else:
            proof["binding"] = validate_live_target(
                health, document, scene, expected_document_id=expected_document_id)
            proof["ready_for_first_write"] = True
            proof["outcome"] = "READ_ONLY_PREFLIGHT_PASS"
            print("XD_RED_FIRST_WRITE_TARGET_GATE=PASS", flush=True)
    except Exception as exc:
        proof["outcome"] = "BLOCKED"
        proof["reason"] = type(exc).__name__ + ": " + str(exc)[:380]
        raise
    finally:
        _write_report(report, proof)
        print("XD_RED_PREFLIGHT_EVIDENCE=" + str(report), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--discover", action="store_true")
    group.add_argument("--expected-document-id")
    parser.add_argument("--report", type=Path, default=Path(os.environ.get("RUNNER_TEMP", ".")) / "xd_red_poster_preflight.json")
    args = parser.parse_args()
    if args.expected_document_id == OLD_DOCUMENT_ID:
        parser.error("refusing to bind known old 32-object document")
    asyncio.run(inspect(expected_document_id=args.expected_document_id, report=args.report))


if __name__ == "__main__":
    main()
