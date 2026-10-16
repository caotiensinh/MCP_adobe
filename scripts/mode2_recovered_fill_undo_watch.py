"""One verified XD experimental WebSocket session for new Fill->Undo E2E.

The earlier applied Fill belonged to a terminated XD process; it is not retried.
This is a distinct, one-shot recovery transaction on the verified SAVED 34-node
copy. Native GUI menu commands are issued only by the outer self-hosted job,
never from a nested Python subprocess.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from mcp_adobe.xd_bridge import XdWebSocketBridgeClient
from mcp_adobe.xd_mode2_experimental import EXPERIMENTAL_BRIDGE_BUILD
from mode2_live_disposable_fill_once import (
    DOC, GUID, NAME, BEFORE, AFTER, SAVED_HASH,
    native_paths, native_unchanged, exact_rectangle, inspect, save_receipt,
)

RECEIPT_NAME = "mode2_recovered_fill_undo_session_receipt.json"


def check_old_transaction(paths: tuple[Path, ...]) -> None:
    old = json.loads(paths[4].read_text(encoding="utf-8"))
    if (old.get("state") != "applied_verified" or
        old.get("operation_id") != "xd-1792161320011-1" or
        old.get("document_id") != DOC or old.get("node_id") != GUID or
        old.get("fill_before") != BEFORE or old.get("fill_requested") != AFTER):
        raise RuntimeError("MODE2_RECOVERY_PRIOR_SESSION_UNVERIFIED")
    folder = paths[4].parent
    if (not (folder / "Mode2_AfterFill_GUI_Recovery_Once.marker").is_file() or
        not (folder / "Mode2_Recovery_Reselect_Guid_Color_Once.marker").is_file() or
        (folder / "Mode2_GUID_Fill_Undo_Once.marker").exists() or
        (folder / "mode2_exact_guid_fill_undo_receipt.json").exists()):
        raise RuntimeError("MODE2_RECOVERY_PREVIOUS_SESSION_FENCE_NOT_EXACT")


def one_session(timeout_seconds: int) -> None:
    paths = native_paths()
    native_unchanged(paths)
    check_old_transaction(paths)
    folder = paths[4].parent
    receipt = folder / RECEIPT_NAME
    if receipt.exists():
        raise RuntimeError("MODE2_RECOVERY_NEW_TRANSACTION_ALREADY_ATTEMPTED")
    bridge = XdWebSocketBridgeClient(
        host="127.0.0.1", port=8766,
        startup_timeout_seconds=7, call_timeout_seconds=14,
    )
    try:
        bridge.start()
        deadline = time.monotonic() + timeout_seconds
        while not bridge.connected and time.monotonic() < deadline:
            time.sleep(0.25)
        if not bridge.connected or bridge.plugin_info.get("bridgeBuild") != EXPERIMENTAL_BRIDGE_BUILD:
            raise RuntimeError("MODE2_RECOVERY_EXPERIMENTAL_UXP_NOT_CONNECTED")
        bounds = inspect(bridge, BEFORE)
        if bounds != exact_rectangle(bridge.call_tool("xd.scenegraph.snapshot", {})):
            raise RuntimeError("MODE2_RECOVERY_TARGET_BOUNDS_MISMATCH")
        native_unchanged(paths)
        record = {
            "state": "intent", "document_id": DOC, "node_id": GUID,
            "name": NAME, "bounds": bounds, "before_fill": BEFORE,
            "after_fill": AFTER, "saved_native_sha256": SAVED_HASH,
            "prior_transaction_id": "xd-1792161320011-1",
            "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        }
        save_receipt(receipt, record, first=True)
        queued = bridge.call_tool("xd.queue.mode2_fill", {
            "document_id": DOC, "node_id": GUID, "bounds": bounds,
            "fill": AFTER, "isolated_test_copy": True, "user_confirmed": True,
        })
        op = queued.get("operation_id")
        if (queued.get("status") != "queued" or
            queued.get("approval_required") is not True or
            queued.get("pending_count") != 1 or
            not isinstance(op, str) or
            op == record["prior_transaction_id"]):
            raise RuntimeError("MODE2_RECOVERY_QUEUE_AMBIGUOUS_NO_REPLAY")
        record.update(state="queued", operation_id=op)
        save_receipt(receipt, record)
        print("MODE2_RECOVERY_NEW_FILL_OPERATION=" + op, flush=True)
        print("MODE2_RECOVERY_FILL_QUEUE_READY=PASS", flush=True)
        while time.monotonic() < deadline:
            status = bridge.call_tool("xd.queue.status", {"operation_id": op})
            if status.get("status") == "applied":
                if status.get("method") != "xd.queue.mode2_fill":
                    raise RuntimeError("MODE2_RECOVERY_WRONG_OPERATION_APPLIED")
                break
            if status.get("status") != "queued":
                raise RuntimeError("MODE2_RECOVERY_APPLY_FAILED_OR_UNKNOWN_NO_REPLAY")
            time.sleep(.3)
        else:
            raise RuntimeError("MODE2_RECOVERY_APPLY_TIMEOUT_UNKNOWN_NO_REPLAY")
        inspect(bridge, AFTER)
        native_unchanged(paths)
        record["state"] = "applied_verified"
        save_receipt(receipt, record)
        print("MODE2_RECOVERY_FILL_APPLIED_A1B2C3=PASS", flush=True)
        while time.monotonic() < deadline:
            try:
                inspect(bridge, BEFORE)
                break
            except RuntimeError as exc:
                if "MODE2_FILL_NATIVE_COLOR_MISMATCH" not in str(exc):
                    raise
            time.sleep(.4)
        else:
            raise RuntimeError("MODE2_RECOVERY_UNDO_NOT_OBSERVED_OUTCOME_UNKNOWN")
        if bridge.call_tool("xd.health", {}).get("pending_count") != 0:
            raise RuntimeError("MODE2_RECOVERY_UNDO_LEFT_PENDING_QUEUE")
        native_unchanged(paths)
        record["state"] = "undone_verified"
        save_receipt(receipt, record)
        print("MODE2_RECOVERY_REAL_XD_UNDO_TO_445566=PASS", flush=True)
        print("MODE2_RECOVERY_GUID_NODE_COUNT_BOUNDS_PRESERVED=PASS", flush=True)
        print("MODE2_RECOVERY_PROTECTED_AND_DISPOSABLE_HASHES_PRESERVED=PASS", flush=True)
    finally:
        bridge.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-seconds", type=int, default=160)
    args = parser.parse_args()
    if not 60 <= args.wait_seconds <= 240:
        raise ValueError("MODE2_RECOVERY_INVALID_TIMEOUT")
    one_session(args.wait_seconds)
