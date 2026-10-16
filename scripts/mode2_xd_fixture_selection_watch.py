"""Bounded real Adobe XD 8766 readback after explicit GUI fixture-selection command.

This listener never queues writes, invokes Reload, or modifies the XD document.
"""
from __future__ import annotations
import argparse
import json
import time
from mcp_adobe.xd_bridge import XdWebSocketBridgeClient
from mcp_adobe.xd_mode2_experimental import (
    EXPERIMENTAL_BRIDGE_BUILD, ExperimentalXdMode2Adapter
)

DOC = "98d6635b-3767-4254-b200-ec8442b69ad2"
GUID = "130fdb64-c691-4374-ab46-66fd3f9e077c"
EXPECTED = {"left": 484, "top": 166, "right": 584, "bottom": 280}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-seconds", type=int, default=65)
    args = parser.parse_args()
    if args.wait_seconds < 10 or args.wait_seconds > 90:
        raise ValueError("Invalid bounded selection watch duration")
    bridge = XdWebSocketBridgeClient(
        host="127.0.0.1", port=8766, startup_timeout_seconds=7,
        call_timeout_seconds=12,
    )
    try:
        bridge.start()
        deadline = time.monotonic() + args.wait_seconds
        while not bridge.connected and time.monotonic() < deadline:
            time.sleep(.3)
        if not bridge.connected:
            raise RuntimeError("MODE2_EXP_PLUGIN_NOT_CONNECTED")
        if bridge.plugin_info.get("bridgeBuild") != EXPERIMENTAL_BRIDGE_BUILD:
            raise RuntimeError("MODE2_WRONG_EXPERIMENTAL_BUILD")
        print("MODE2_FIXTURE_LIVE_UXP_BUILD=PASS", flush=True)
        health = bridge.call_tool("xd.health", {})
        graph = bridge.call_tool("xd.scenegraph.snapshot", {})
        if (health.get("pending_count") != 0 or
            health.get("bridge_build") != EXPERIMENTAL_BRIDGE_BUILD or
            graph.get("complete") is not True or
            graph.get("document_id") != DOC or
            graph.get("node_count") != 33):
            raise RuntimeError("MODE2_FIXTURE_PRESELECT_GRAPH_NOT_BASELINE")
        print("MODE2_FIXTURE_PRESELECT_GRAPH=PASS", flush=True)
        while time.monotonic() < deadline:
            s = bridge.call_tool("xd.selection.get", {})
            items = s.get("items", [])
            if len(items) == 1:
                item = items[0]
                if (item.get("guid") != GUID or
                    item.get("name") != "11 XD Panda Right Ear"):
                    raise RuntimeError("MODE2_SELECTED_WRONG_NODE_NO_MUTATION")
                print("MODE2_FIXTURE_SELECTION_GUID="+str(item["guid"]), flush=True)
                break
            if len(items) > 1:
                raise RuntimeError("MODE2_SELECTION_NOT_UNIQUE")
            time.sleep(.5)
        else:
            raise RuntimeError("MODE2_SELECTION_WAS_NOT_OBSERVED")
        target = {"document_id": DOC, "node_id": GUID, "bounds": EXPECTED}
        adapter = ExperimentalXdMode2Adapter(bridge, writes_enabled=False)
        result = adapter.execute("xd.mode2.node.inspect", target)
        proof = result["result"]
        if proof.get("node_id") != GUID or proof.get("bounds") != EXPECTED:
            raise RuntimeError("MODE2_FIXTURE_NATIVE_INSPECT_MISMATCH")
        after = bridge.call_tool("xd.scenegraph.snapshot", {})
        endhealth = bridge.call_tool("xd.health", {})
        if (after.get("document_id") != DOC or
            after.get("node_count") != 33 or
            endhealth.get("pending_count") != 0):
            raise RuntimeError("MODE2_SELECTION_CHANGED_NATIVE_SCENE")
        print("MODE2_FIXTURE_SELECTED_AND_INSPECTED=PASS", flush=True)
        print("MODE2_FIXTURE_NO_WRITE_QUEUE=PASS", flush=True)
        return 0
    finally:
        bridge.close()


if __name__ == "__main__":
    raise SystemExit(main())
