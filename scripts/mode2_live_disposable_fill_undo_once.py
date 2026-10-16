"""Verify applied native XD color, invoke one exact native Undo, verify restored.

The rollback is a single intentional XD Edit > Undo command. Persistent
receipts and a separate GUI marker forbid blind retries after unknown results.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from collections.abc import Mapping

from mcp_adobe.xd_bridge import XdWebSocketBridgeClient
from mcp_adobe.xd_mode2_experimental import EXPERIMENTAL_BRIDGE_BUILD
from mode2_live_disposable_fill_once import (
    DOC, GUID, NAME, BEFORE, AFTER,
    native_paths, native_unchanged, exact_rectangle, inspect, save_receipt,
)


def exact_color(bridge: XdWebSocketBridgeClient) -> str:
    h = bridge.call_tool("xd.health", {})
    if h.get("bridge_build") != EXPERIMENTAL_BRIDGE_BUILD or h.get("pending_count") != 0:
        raise RuntimeError("MODE2_UNDO_EXPERIMENTAL_HEALTH_NOT_CLEAN")
    bounds = exact_rectangle(bridge.call_tool("xd.scenegraph.snapshot", {}))
    selected = bridge.call_tool("xd.selection.get", {}).get("items", [])
    if (not isinstance(selected, list) or len(selected) != 1 or
        not isinstance(selected[0], Mapping) or selected[0].get("guid") != GUID):
        raise RuntimeError("MODE2_UNDO_SELECTION_CHANGED")
    color = bridge.call_tool("xd.mode2.node.fill.inspect", {
        "document_id": DOC, "node_id": GUID, "name": NAME, "bounds": bounds,
    })
    if (color.get("node_id") != GUID or color.get("document_id") != DOC or
        color.get("bounds") != bounds or color.get("selected_count") != 1 or
        color.get("pending_count") != 0 or color.get("fill_type") != "Color" or
        not isinstance(color.get("fill"), str)):
        raise RuntimeError("MODE2_UNDO_NATIVE_COLOR_READ_UNVERIFIED")
    return color["fill"]


def ui(action: str) -> None:
    helper = Path(__file__).with_name("mode2_live_fill_undo_ui.ps1")
    subprocess.run([
        "powershell", "-NoProfile", "-NonInteractive",
        "-ExecutionPolicy", "Bypass", "-File", str(helper),
        "-Action", action,
    ], check=True, timeout=35)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-seconds", type=int, default=85)
    options = parser.parse_args()
    if not 30 <= options.wait_seconds <= 110:
        raise ValueError("MODE2_UNDO_TIMEOUT_NOT_VALID")
    paths = native_paths()
    native_unchanged(paths)
    record = json.loads(paths[4].read_text(encoding="utf-8"))
    if (record.get("state") != "applied_verified" or
        record.get("document_id") != DOC or
        record.get("node_id") != GUID or
        record.get("name") != NAME or
        record.get("fill_before") != BEFORE or
        record.get("fill_requested") != AFTER or
        not isinstance(record.get("operation_id"), str) or
        not record["operation_id"]):
        raise RuntimeError("MODE2_UNDO_EXACT_APPLIED_FILL_RECEIPT_MISSING")
    undo_path = paths[4].with_name("mode2_exact_guid_fill_undo_receipt.json")
    undo_marker = paths[4].with_name("Mode2_GUID_Fill_Undo_Once.marker")
    if undo_path.exists() or undo_marker.exists():
        raise RuntimeError("MODE2_UNDO_ALREADY_ATTEMPTED_NO_REPLAY")
    bridge = XdWebSocketBridgeClient(
        host="127.0.0.1", port=8766,
        startup_timeout_seconds=7, call_timeout_seconds=12,
    )
    try:
        bridge.start()
        if bridge.connected:
            raise RuntimeError("MODE2_UNDO_UNOWNED_EXISTING_BRIDGE_SESSION")
        ui("Connect")
        deadline = time.monotonic() + options.wait_seconds
        while not bridge.connected and time.monotonic() < deadline:
            time.sleep(.3)
        if not bridge.connected or bridge.plugin_info.get("bridgeBuild") != EXPERIMENTAL_BRIDGE_BUILD:
            raise RuntimeError("MODE2_UNDO_EXPERIMENTAL_BRIDGE_NOT_CONNECTED")
        if exact_color(bridge) != AFTER:
            raise RuntimeError("MODE2_UNDO_PRECONDITION_NOT_APPLIED_COLOR")
        applied = bridge.call_tool("xd.queue.status", {"operation_id": record["operation_id"]})
        if (applied.get("status") != "applied" or
            applied.get("method") != "xd.queue.mode2_fill"):
            raise RuntimeError("MODE2_UNDO_ORIGINAL_OPERATION_STATUS_UNVERIFIED")
        inspect(bridge, AFTER)
        native_unchanged(paths)
        print("MODE2_NATIVE_UNDO_PRECHECK_A1B2C3=PASS", flush=True)
        undo_record = {
            "state": "intent", "operation_id": record["operation_id"],
            "document_id": DOC, "node_id": GUID, "fill_before_undo": AFTER,
            "fill_expected_after_undo": BEFORE,
            "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        }
        save_receipt(undo_path, undo_record, first=True)
        ui("Undo")
        print("MODE2_NATIVE_UNDO_INVOKED_ONE_SHOT=PASS", flush=True)
        while time.monotonic() < deadline:
            actual = exact_color(bridge)
            if actual == BEFORE:
                break
            if actual != AFTER:
                raise RuntimeError("MODE2_UNDO_RESULT_UNEXPECTED_FILL_COLOR")
            time.sleep(.4)
        else:
            raise RuntimeError("MODE2_UNDO_COLOR_NOT_RESTORED_OUTCOME_UNKNOWN")
        inspect(bridge, BEFORE)
        native_unchanged(paths)
        undo_record["state"] = "undone_verified"
        save_receipt(undo_path, undo_record)
        print("MODE2_REAL_XD_FILL_UNDO_BACK_TO_445566=PASS", flush=True)
        print("MODE2_REAL_XD_FILL_UNDO_SAME_GUID_34_NODES=PASS", flush=True)
        print("MODE2_NATIVE_PROTECTED_PANDA_AND_DISPOSABLE_SHA_UNCHANGED=PASS", flush=True)
        return 0
    finally:
        bridge.close()


if __name__ == "__main__":
    raise SystemExit(main())
