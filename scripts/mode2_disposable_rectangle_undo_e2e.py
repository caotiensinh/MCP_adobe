"""One-shot real Adobe XD disposable-only transaction. Never replay an ambiguous write."""
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from mcp import Client
from export_region_metadata import payload, unwrap

ROOT = Path(os.environ["USERPROFILE"]) / "Documents" / "MCPAdobe"
ORIGINAL = ROOT / "MCP_Mode1_Panda_XD_38136531800.xd"
PANDA = ROOT / "mode2-isolated" / "Panda_Mode2_Editable_Experiment.xd"
TEST = ROOT / "mode2-disposable-native" / "Mode2_Undo_E2E_38584984023.xd"
SHA = "3a10e1510abc41eccd4485d6f852ea6ced7acc2cf50109e7c1bd123353589ed1"
NAME = "MODE2_DISPOSABLE_UNDO_RECT_ONE_SHOT"

def protect():
    for p in (ORIGINAL, PANDA):
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != SHA:
            raise RuntimeError("MODE2_PROTECTED_NATIVE_CHANGED")
def target_nodes(obj):
    result = []
    def walk(nodes):
        for n in nodes:
            if n.get("name") == NAME:
                result.append(n)
            walk(n.get("children", []))
    walk(obj.get("nodes", []))
    return result

async def main():
    protect()
    if not TEST.is_file() or hashlib.sha256(TEST.read_bytes()).hexdigest() != SHA:
        raise RuntimeError("MODE2_TEST_BASELINE_CHANGED")
    receipt_path = TEST.with_suffix(".mode2-receipt.json")
    if receipt_path.exists():
        raise RuntimeError("MODE2_RECEIPT_EXISTS_NO_REPLAY")
    async with Client("http://127.0.0.1:8787/mcp") as c:
        async def call(tool, capability, arguments=None):
            r = await asyncio.wait_for(c.call_tool(tool, {
                "application": "xd", "capability": capability, "arguments": arguments or {}
            }), timeout=15)
            o = payload(r)
            if not isinstance(o, dict) or o.get("ok") is False:
                raise RuntimeError("MODE2_MCP_RESPONSE_UNKNOWN_" + capability)
            if isinstance(o.get("result"), dict):
                o = o["result"]
            o = unwrap(o)
            if not isinstance(o, dict):
                raise RuntimeError("MODE2_MCP_RESULT_NOT_OBJECT_" + capability)
            return o
        g = await call("creative_read", "creative.scenegraph.list")
        h = await call("creative_read", "creative.health")
        sel = await call("creative_read", "creative.selection.get")
        if g.get("complete") is not True or g.get("node_count") != 33 or target_nodes(g):
            raise RuntimeError("MODE2_PREWRITE_SCENE_UNEXPECTED")
        if h.get("bridge") != "connected" or h.get("pending_count") != 0:
            raise RuntimeError("MODE2_EXISTING_PENDING_QUEUE")
        if len(sel.get("items", [])) != 1:
            raise RuntimeError("MODE2_SELECTION_CHANGED")
        print("MODE2_PREWRITE_SAFE=PASS " + str(g.get("document_id")), flush=True)
        op = await call("creative_write", "creative.shape.rectangle", {
            "name": NAME, "x": 700, "y": 420, "width": 34,
            "height": 26, "fill": "#4F7CFF"
        })
        op_id = op.get("operation_id")
        if op.get("status") != "queued" or op.get("pending_count") != 1 or not op_id:
            raise RuntimeError("MODE2_QUEUE_RESULT_UNKNOWN_STOP")
        receipt_path.write_text(json.dumps({
            "operation_id": op_id, "state": "queued", "document_id": g["document_id"],
            "target_name": NAME,
        }, indent=2), encoding="utf-8")
        print("MODE2_RECT_QUEUED_ONCE=" + str(op_id), flush=True)
        # Only the existing proven XD real UXP menu helper is allowed to apply.
        import subprocess
        helper = Path(__file__).with_name("mode2_disposable_apply_once.ps1")
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(helper)], check=True, timeout=20)
        for _ in range(16):
            status = await call("creative_read", "xd.queue.status", {"operation_id": op_id})
            if status.get("status") != "queued":
                break
            await asyncio.sleep(0.4)
        if status.get("status") != "applied":
            raise RuntimeError("MODE2_APPLY_UNCERTAIN_NO_REPLAY")
        after = await call("creative_read", "creative.scenegraph.list")
        if after.get("document_id") != g.get("document_id") or len(target_nodes(after)) != 1:
            raise RuntimeError("MODE2_AFTER_APPLY_NOT_UNIQUE")
        if after.get("node_count") != g.get("node_count") + 1:
            raise RuntimeError("MODE2_NODE_COUNT_NOT_PLUS_ONE")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["state"] = "applied"
        receipt["guid"] = target_nodes(after)[0].get("id")
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print("MODE2_RECT_APPLIED_READBACK=PASS " + str(receipt["guid"]), flush=True)
        # Undo via native XD foreground menu in an independent PowerShell step.
        # This Python phase deliberately terminates here, leaving exact receipt.
        protect()

asyncio.run(main())
