"""Read-only Adobe XD color attestation for the saved 34-node disposable Rectangle.

No selection staging, no edits, no file I/O, no queue clearing. Requires exact
live document/selection identity; deliberately fails closed on any ambiguity.
"""
from __future__ import annotations

import argparse
import time
from collections.abc import Mapping

from mcp_adobe.xd_bridge import XdWebSocketBridgeClient
from mcp_adobe.xd_mode2_experimental import EXPERIMENTAL_BRIDGE_BUILD

DOC = "98d6635b-3767-4254-b200-ec8442b69ad2"
GUID = "9989e92f-7c9b-4721-9cdc-b5b5ea33cdf2"
NAME = "MODE2_DISPOSABLE_FILL_RECT_GUID_E2E"
INITIAL = "#445566"


def one_exact_rect(graph: Mapping) -> Mapping:
    if (
        graph.get("complete") is not True
        or graph.get("document_id") != DOC
        or graph.get("node_count") != 34
        or not isinstance(graph.get("nodes"), list)
    ):
        raise RuntimeError("MODE2_FILL_READ_SCENEGRAPH_NOT_34_NODE_COPY")
    found = []

    def walk(nodes, depth=0):
        if depth > 80 or not isinstance(nodes, list):
            raise RuntimeError("MODE2_FILL_READ_UNSAFE_SCENEGRAPH")
        for node in nodes:
            if not isinstance(node, Mapping):
                raise RuntimeError("MODE2_FILL_READ_MALFORMED_NODE")
            if node.get("id") == GUID or node.get("name") == NAME:
                found.append(node)
            walk(node.get("children", []), depth + 1)

    walk(graph["nodes"])
    if len(found) != 1:
        raise RuntimeError("MODE2_FILL_READ_MISSING_OR_AMBIGUOUS_GUID")
    node = found[0]
    if (
        node.get("id") != GUID
        or node.get("name") != NAME
        or node.get("type") != "Rectangle"
        or node.get("visible") is not True
        or node.get("locked") is not False
    ):
        raise RuntimeError("MODE2_FILL_READ_WRONG_OR_UNEDITABLE_NODE")
    b = node.get("bounds")
    if (
        not isinstance(b, dict)
        or set(b) != {"left", "top", "right", "bottom"}
        or any(type(v) not in (int, float) for v in b.values())
        or abs(b["left"] - 820) > 2
        or abs(b["top"] - 500) > 2
        or abs(b["right"] - 856) > 2
        or abs(b["bottom"] - 528) > 2
    ):
        raise RuntimeError("MODE2_FILL_READ_RECTANGLE_BOUNDS_INVALID")
    return node


def verify_live_color(bridge: XdWebSocketBridgeClient) -> None:
    health = bridge.call_tool("xd.health", {})
    if (
        health.get("bridge") != "connected"
        or health.get("bridge_build") != EXPERIMENTAL_BRIDGE_BUILD
        or type(health.get("pending_count")) is not int
        or health["pending_count"] != 0
    ):
        raise RuntimeError("MODE2_FILL_READ_WRONG_BRIDGE_OR_PENDING_QUEUE")
    graph = bridge.call_tool("xd.scenegraph.snapshot", {})
    node = one_exact_rect(graph)
    selected = bridge.call_tool("xd.selection.get", {}).get("items", [])
    if not isinstance(selected, list) or len(selected) != 1 or selected[0].get("guid") != GUID:
        raise RuntimeError("MODE2_FILL_READ_EXACT_GUID_NOT_SELECTED_NO_MUTATION")
    bounds = node["bounds"]
    args = {"document_id": DOC, "node_id": GUID, "name": NAME, "bounds": bounds}
    proof = bridge.call_tool("xd.mode2.node.fill.inspect", args)
    if (
        proof.get("document_id") != DOC
        or proof.get("node_id") != GUID
        or proof.get("name") != NAME
        or proof.get("bounds") != bounds
        or proof.get("fill_type") != "Color"
        or proof.get("fill") != INITIAL
        or proof.get("selected_count") != 1
        or proof.get("pending_count") != 0
    ):
        raise RuntimeError("MODE2_FILL_READ_REAL_COLOR_NOT_ATTESTED")
    after = bridge.call_tool("xd.health", {})
    if after.get("pending_count") != 0:
        raise RuntimeError("MODE2_FILL_READ_QUEUE_CHANGED")
    print("MODE2_REAL_XD_RECT_GUID=" + GUID, flush=True)
    print("MODE2_REAL_XD_RECT_COLOR=" + proof["fill"], flush=True)
    print("MODE2_REAL_XD_FILL_INITIAL_READBACK=PASS", flush=True)
    print("MODE2_MUTATION_ATTEMPTED=False", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait-seconds", type=int, default=65)
    args = ap.parse_args()
    if not (10 <= args.wait_seconds <= 90):
        raise ValueError("bad timeout")
    bridge = XdWebSocketBridgeClient(
        host="127.0.0.1", port=8766,
        startup_timeout_seconds=7, call_timeout_seconds=12
    )
    try:
        bridge.start()
        deadline = time.monotonic() + args.wait_seconds
        while not bridge.connected and time.monotonic() < deadline:
            time.sleep(0.3)
        if not bridge.connected:
            raise RuntimeError("MODE2_EXPERIMENTAL_UXP_NOT_CONNECTED")
        if bridge.plugin_info.get("bridgeBuild") != EXPERIMENTAL_BRIDGE_BUILD:
            raise RuntimeError("MODE2_FILL_READ_WRONG_UXP_BUILD")
        verify_live_color(bridge)
        return 0
    finally:
        bridge.close()


if __name__ == "__main__":
    raise SystemExit(main())
