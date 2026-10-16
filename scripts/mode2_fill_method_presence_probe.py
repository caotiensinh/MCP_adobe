"""Prove actual live experimental UXP exposes the Fill inspector after a cold start.

Calls an intentionally invalid read-only request and expects the new inspector's
distinct fail-closed error. No Adobe selection, mutation or file writes.
"""
from __future__ import annotations
import argparse
import time
from mcp_adobe.xd_bridge import XdWebSocketBridgeClient
from mcp_adobe.xd_mode2_experimental import EXPERIMENTAL_BRIDGE_BUILD

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--wait-seconds",type=int,default=70)
    options=parser.parse_args()
    if not 10 <= options.wait_seconds <= 90:
        raise ValueError("invalid wait")
    bridge=XdWebSocketBridgeClient(host="127.0.0.1",port=8766,
                                   startup_timeout_seconds=7,call_timeout_seconds=12)
    try:
        bridge.start()
        deadline=time.monotonic()+options.wait_seconds
        while not bridge.connected and time.monotonic()<deadline:
            time.sleep(0.3)
        if not bridge.connected:raise RuntimeError("MODE2_UXP_NOT_CONNECTED")
        if bridge.plugin_info.get("bridgeBuild")!=EXPERIMENTAL_BRIDGE_BUILD:
            raise RuntimeError("MODE2_WRONG_PLUGIN_BUILD")
        h=bridge.call_tool("xd.health",{})
        g=bridge.call_tool("xd.scenegraph.snapshot",{})
        if (h.get("bridge_build")!=EXPERIMENTAL_BRIDGE_BUILD or
            h.get("pending_count")!=0 or g.get("node_count")!=34 or
            g.get("document_id")!="98d6635b-3767-4254-b200-ec8442b69ad2"):
            raise RuntimeError("MODE2_UXP_WRONG_HOST_OR_GRAPH")
        try:
            bridge.call_tool("xd.mode2.node.fill.inspect",{})
        except RuntimeError as exc:
            if "MODE2_FILL_READ_TARGET_NOT_EXACT" not in str(exc):
                raise RuntimeError("MODE2_UXP_INSPECTOR_STILL_NOT_LOADED") from exc
            print("MODE2_LIVE_FILL_INSPECTOR_METHOD_PRESENT=PASS",flush=True)
            print("MODE2_LIVE_SCENEGRAPH_34_AND_ZERO_PENDING=PASS",flush=True)
            print("MODE2_MUTATION_ATTEMPTED=False",flush=True)
            return 0
        raise RuntimeError("MODE2_INVALID_INSPECT_REQUEST_NOT_REJECTED")
    finally:
        bridge.close()

if __name__=="__main__":
    raise SystemExit(main())
