"""Single-use native Adobe XD experimental Rectangle fill transaction.

An on-disk receipt is created BEFORE queueing. An ambiguous operation is never
replayed, even if the host response times out. The GUI Apply must be invoked
separately by the one-shot, host-attested Windows workflow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from collections.abc import Mapping

from mcp_adobe.xd_bridge import XdWebSocketBridgeClient
from mcp_adobe.xd_mode2_experimental import EXPERIMENTAL_BRIDGE_BUILD

DOC = "98d6635b-3767-4254-b200-ec8442b69ad2"
GUID = "9989e92f-7c9b-4721-9cdc-b5b5ea33cdf2"
NAME = "MODE2_DISPOSABLE_FILL_RECT_GUID_E2E"
BEFORE = "#445566"
AFTER = "#A1B2C3"
PANDA_HASH = "3A10E1510ABC41ECCD4485D6F852EA6CED7ACC2CF50109E7C1BD123353589ED1"
SAVED_HASH = "1E15162107A64E3D7D4CAF8C12B88FE24B64488DA9788854E6D300DDBAE88C2F"
EXPECTED_BOUNDS = {"left": 820, "top": 500, "right": 856, "bottom": 528}


def native_paths() -> tuple[Path, Path, Path, Path, Path]:
    root = Path(os.environ["USERPROFILE"]) / "Documents" / "MCPAdobe"
    disposable_dir = root / "mode2-disposable-native"
    return (
        root / "MCP_Mode1_Panda_XD_38136531800.xd",
        root / "mode2-isolated" / "Panda_Mode2_Editable_Experiment.xd",
        disposable_dir / "Mode2_Undo_E2E_38584984023.xd",
        disposable_dir / "mode2_fill_rect_guid_receipt.json",
        disposable_dir / "mode2_exact_guid_fill_mutation_receipt.json",
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def native_unchanged(paths: tuple[Path, Path, Path, Path, Path]) -> None:
    p1, p2, target, _, _ = paths
    if any(not p.is_file() or sha256(p) != PANDA_HASH for p in (p1, p2)):
        raise RuntimeError("MODE2_FILL_PROTECTED_PANDA_HASH_INVALID")
    if not target.is_file() or sha256(target) != SAVED_HASH:
        raise RuntimeError("MODE2_FILL_DISPOSABLE_SAVED_NATIVE_HASH_CHANGED")


def exact_rectangle(graph: Mapping) -> dict:
    if (not isinstance(graph, Mapping) or graph.get("complete") is not True or
        graph.get("document_id") != DOC or graph.get("node_count") != 34):
        raise RuntimeError("MODE2_FILL_SCENEGRAPH_NOT_VERIFIED_34")
    found = []
    total = [0]

    def visit(nodes: object, depth: int = 0) -> None:
        if not isinstance(nodes, list) or depth > 80:
            raise RuntimeError("MODE2_FILL_SCENEGRAPH_MALFORMED")
        for node in nodes:
            total[0] += 1
            if total[0] > 1000 or not isinstance(node, Mapping):
                raise RuntimeError("MODE2_FILL_SCENEGRAPH_UNSAFE")
            if node.get("id") == GUID or node.get("name") == NAME:
                found.append(node)
            visit(node.get("children", []), depth + 1)

    visit(graph.get("nodes"))
    if (total[0] != 34 or len(found) != 1 or
        found[0].get("id") != GUID or found[0].get("name") != NAME or
        found[0].get("type") != "Rectangle" or
        found[0].get("visible") is not True or
        found[0].get("locked") is not False):
        raise RuntimeError("MODE2_FILL_NOT_EXACT_DISPOSABLE_RECT")
    bounds = found[0].get("bounds")
    if (not isinstance(bounds, Mapping) or set(bounds) != set(EXPECTED_BOUNDS) or
        any(type(bounds[k]) not in (int, float) or abs(bounds[k] - v) > 0.1
            for k, v in EXPECTED_BOUNDS.items())):
        raise RuntimeError("MODE2_FILL_RECTANGLE_BOUNDS_CHANGED")
    return dict(bounds)


def inspect(bridge: XdWebSocketBridgeClient, expected_fill: str) -> dict:
    health = bridge.call_tool("xd.health", {})
    if (health.get("bridge_build") != EXPERIMENTAL_BRIDGE_BUILD or
        health.get("bridge") != "connected" or
        type(health.get("pending_count")) is not int or
        health["pending_count"] != 0):
        raise RuntimeError("MODE2_FILL_BRIDGE_NOT_CLEAN")
    bounds = exact_rectangle(bridge.call_tool("xd.scenegraph.snapshot", {}))
    selection = bridge.call_tool("xd.selection.get", {}).get("items", [])
    if (not isinstance(selection, list) or len(selection) != 1 or
        not isinstance(selection[0], Mapping) or selection[0].get("guid") != GUID):
        raise RuntimeError("MODE2_FILL_RECTANGLE_NOT_SELECTED_EXACTLY")
    native = bridge.call_tool("xd.mode2.node.fill.inspect", {
        "document_id": DOC, "node_id": GUID, "name": NAME, "bounds": bounds,
    })
    if (native.get("document_id") != DOC or native.get("node_id") != GUID or
        native.get("name") != NAME or native.get("bounds") != bounds or
        native.get("fill") != expected_fill or native.get("fill_type") != "Color" or
        native.get("selected_count") != 1 or native.get("pending_count") != 0):
        raise RuntimeError("MODE2_FILL_NATIVE_COLOR_MISMATCH")
    return bounds


def save_receipt(path: Path, record: dict, *, first: bool = False) -> None:
    data = json.dumps(record, indent=2, sort_keys=True)
    if first:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    else:
        temp = path.with_name(path.name + ".write-" + str(os.getpid()))
        if temp.exists():
            raise RuntimeError("MODE2_FILL_RECEIPT_TEMP_COLLISION")
        with temp.open("x", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-seconds", type=int, default=100)
    args = parser.parse_args()
    if not 30 <= args.wait_seconds <= 120:
        raise ValueError("MODE2_FILL_INVALID_TIMEOUT")
    paths = native_paths()
    native_unchanged(paths)
    creation = json.loads(paths[3].read_text(encoding="utf-8"))
    if (creation.get("state") != "applied" or creation.get("node_id") != GUID or
        creation.get("document_id") != DOC or creation.get("name") != NAME):
        raise RuntimeError("MODE2_FILL_CREATION_RECEIPT_UNVERIFIED")
    if paths[4].exists():
        raise RuntimeError("MODE2_FILL_RECEIPT_EXISTS_REFUSE_REPLAY")
    bridge = XdWebSocketBridgeClient(
        host="127.0.0.1", port=8766,
        startup_timeout_seconds=7, call_timeout_seconds=14,
    )
    try:
        bridge.start()
        deadline = time.monotonic() + args.wait_seconds
        while not bridge.connected and time.monotonic() < deadline:
            time.sleep(.25)
        if not bridge.connected or bridge.plugin_info.get("bridgeBuild") != EXPERIMENTAL_BRIDGE_BUILD:
            raise RuntimeError("MODE2_FILL_EXPERIMENTAL_UXP_NOT_CONNECTED")
        bounds = inspect(bridge, BEFORE)
        native_unchanged(paths)
        print("MODE2_EXACT_FILL_PREWRITE_READBACK=PASS", flush=True)
        record = {
            "state": "intent", "document_id": DOC, "node_id": GUID,
            "name": NAME, "bounds": bounds, "fill_before": BEFORE,
            "fill_requested": AFTER, "saved_native_sha256": SAVED_HASH,
            "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        }
        save_receipt(paths[4], record, first=True)
        queued = bridge.call_tool("xd.queue.mode2_fill", {
            "document_id": DOC, "node_id": GUID, "bounds": bounds,
            "fill": AFTER, "isolated_test_copy": True, "user_confirmed": True,
        })
        op_id = queued.get("operation_id")
        if (not isinstance(op_id, str) or not op_id or
            queued.get("status") != "queued" or
            queued.get("approval_required") is not True or
            queued.get("pending_count") != 1):
            raise RuntimeError("MODE2_FILL_QUEUE_RESULT_UNKNOWN_NO_REPLAY")
        record.update(state="queued", operation_id=op_id)
        save_receipt(paths[4], record)
        print("MODE2_FILL_QUEUE_READY_FOR_EXPLICIT_MENU=PASS", flush=True)
        last = {}
        while time.monotonic() < deadline:
            last = dict(bridge.call_tool("xd.queue.status", {"operation_id": op_id}))
            if last.get("status") == "applied":
                break
            if last.get("status") != "queued":
                raise RuntimeError("MODE2_FILL_APPLY_FAILED_OR_UNKNOWN_NO_REPLAY")
            time.sleep(.35)
        else:
            raise RuntimeError("MODE2_FILL_APPLY_TIMED_OUT_UNKNOWN_NO_REPLAY")
        if (last.get("method") != "xd.queue.mode2_fill"):
            raise RuntimeError("MODE2_FILL_APPLIED_WRONG_OPERATION")
        record["state"] = "apply_observed"
        save_receipt(paths[4], record)
        inspect(bridge, AFTER)
        native_unchanged(paths)
        record["state"] = "applied_verified"
        save_receipt(paths[4], record)
        print("MODE2_NATIVE_FILL_APPLIED_READBACK_A1B2C3=PASS", flush=True)
        print("MODE2_FILL_OPERATION_ID=" + op_id, flush=True)
        print("MODE2_PANDA_AND_DISPOSABLE_DISK_SHA_UNCHANGED=PASS", flush=True)
        return 0
    finally:
        bridge.close()


if __name__ == "__main__":
    raise SystemExit(main())
