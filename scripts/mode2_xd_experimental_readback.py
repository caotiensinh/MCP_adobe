"""Read-only Mode 2 XD sidecar attestation on isolated port 8766.

No Adobe file operations, GUI reloads, queued writes or Undo.
This tool fails closed unless the distinct experimental plugin is connected.
"""
from __future__ import annotations

import argparse
import json
import time
from math import isfinite
from collections.abc import Mapping
from typing import Any

from mcp_adobe.xd_bridge import XdWebSocketBridgeClient
from mcp_adobe.xd_mode2_experimental import (
    EXPERIMENTAL_BRIDGE_BUILD,
    ExperimentalXdMode2Adapter,
)

EXPECTED_DOC = "98d6635b-3767-4254-b200-ec8442b69ad2"


def find_selected_node(graph: Mapping[str, Any], selection: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve exactly one scenegraph node from a live single-item selection."""
    if graph.get("complete") is not True or not isinstance(graph.get("document_id"), str):
        raise ValueError("MODE2_SCENEGRAPH_UNVERIFIED")
    items = selection.get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], Mapping):
        raise ValueError("MODE2_EXPERIMENTAL_SELECTION_NOT_UNIQUE")
    guid = items[0].get("guid") or items[0].get("id")
    if not isinstance(guid, str) or not guid:
        raise ValueError("MODE2_SELECTION_GUID_MISSING")
    found = []
    count = 0

    def visit(nodes: Any, depth: int = 0) -> None:
        nonlocal count
        if not isinstance(nodes, list) or depth > 100:
            raise ValueError("MODE2_SCENEGRAPH_UNBOUNDED")
        for node in nodes:
            count += 1
            if count > 20000 or not isinstance(node, Mapping):
                raise ValueError("MODE2_SCENEGRAPH_UNBOUNDED")
            if node.get("id") == guid:
                found.append(node)
            visit(node.get("children", []), depth + 1)

    visit(graph.get("nodes", []))
    if len(found) != 1:
        raise ValueError("MODE2_SELECTED_NODE_NOT_UNIQUE_IN_GRAPH")
    node = found[0]
    rect = node.get("bounds")
    if node.get("visible") is not True or node.get("locked") is not False:
        raise ValueError("MODE2_SELECTED_NODE_UNSAFE")
    if not isinstance(rect, Mapping) or set(rect) != {"left", "top", "right", "bottom"}:
        raise ValueError("MODE2_SELECTED_NODE_BOUNDS_MISSING")
    if any(type(v) not in (int, float) or not isfinite(v) for v in rect.values()):
        raise ValueError("MODE2_SELECTED_NODE_NONFINITE")
    if rect["right"] <= rect["left"] or rect["bottom"] <= rect["top"]:
        raise ValueError("MODE2_SELECTED_NODE_ZERO_AREA")
    return {"document_id": graph["document_id"], "node_id": guid, "bounds": dict(rect)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-seconds", type=float, default=15)
    args = parser.parse_args()
    if not (0 < args.wait_seconds <= 45):
        raise ValueError("wait must be 0 to 45 seconds")
    bridge = XdWebSocketBridgeClient(
        host="127.0.0.1", port=8766,
        startup_timeout_seconds=5, call_timeout_seconds=12,
    )
    try:
        bridge.start()
        deadline = time.monotonic() + args.wait_seconds
        while not bridge.connected and time.monotonic() < deadline:
            time.sleep(.3)
        if not bridge.connected:
            print("MODE2_EXPERIMENTAL_BRIDGE=NOT_CONNECTED", flush=True)
            return 2
        build = bridge.plugin_info.get("bridgeBuild")
        if build != EXPERIMENTAL_BRIDGE_BUILD:
            raise RuntimeError("MODE2_WRONG_EXPERIMENTAL_PLUGIN_HELLO")
        adapter = ExperimentalXdMode2Adapter(bridge, writes_enabled=False)
        health = bridge.call_tool("xd.health", {})
        if (health.get("bridge") != "connected" or
                health.get("bridge_build") != EXPERIMENTAL_BRIDGE_BUILD or
                health.get("pending_count") != 0):
            raise RuntimeError("MODE2_EXPERIMENTAL_HEALTH_NOT_READY")
        graph = bridge.call_tool("xd.scenegraph.snapshot", {})
        selection = bridge.call_tool("xd.selection.get", {})
        if graph.get("document_id") != EXPECTED_DOC or graph.get("node_count") != 33:
            raise RuntimeError("MODE2_NOT_DISPOSABLE_BASELINE_GRAPH")
        frame = bridge.call_tool("xd.canvas.frame", {})
        if frame.get("document_id") != graph.get("document_id"):
            raise RuntimeError("MODE2_DISPOSABLE_FRAME_ID_MISMATCH")
        print("MODE2_EXPERIMENTAL_REAL_HOST="+json.dumps({
            "build": build, "document_id": graph["document_id"],
            "node_count": graph["node_count"], "pending_count": 0,
        }, sort_keys=True), flush=True)
        if len(selection.get("items", [])) == 1:
            target = find_selected_node(graph, selection)
            inspected = adapter.execute("xd.mode2.node.inspect", target)
            proof = inspected.get("result", {})
            if proof.get("node_id") != target["node_id"] or proof.get("bounds") != target["bounds"]:
                raise RuntimeError("MODE2_EXPERIMENTAL_INSPECT_NOT_EXACT")
            print("MODE2_EXPERIMENTAL_INSPECT_READONLY=PASS "+target["node_id"], flush=True)
        else:
            print("MODE2_EXPERIMENTAL_INSPECT=BLOCKED_SINGLE_SELECTION_REQUIRED", flush=True)
        print("MODE2_EXPERIMENTAL_BRIDGE_READONLY=PASS", flush=True)
        print("MODE2_NATIVE_MUTATION_ATTEMPTED=False", flush=True)
        return 0
    finally:
        bridge.close()


if __name__ == "__main__":
    raise SystemExit(main())
