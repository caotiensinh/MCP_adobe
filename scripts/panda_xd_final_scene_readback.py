"""Read-only audit of 32 live XD nodes against persisted per-write receipts."""
import asyncio,json,hashlib,os
from pathlib import Path
from mcp import Client
from panda_xd_mode1_e2e import STEPS,node_map
ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
ID="38136531800"
CHECKPOINT=ROOT/f"MCP_Mode1_Panda_XD_{ID}.json"
NATIVE=ROOT/f"MCP_Mode1_Panda_XD_{ID}.xd"
PNG=ROOT/f"MCP_Mode1_Panda_XD_{ID}.png"
async def read(c,cap):
    r=await c.call_tool("creative_read",{"application":"xd","capability":cap,"arguments":{}})
    p=r.structured_content
    if r.is_error or not isinstance(p,dict) or p.get("ok") is not True:
        raise RuntimeError("XD_FINAL_LIVE_READ_FAILED "+cap)
    return p.get("result") or {}
async def main():
    if not CHECKPOINT.is_file() or not NATIVE.is_file() or not PNG.is_file():
        raise RuntimeError("XD_FINAL_REQUIRED_EVIDENCE_MISSING")
    data=json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    proven=data.get("proven") or []
    if len(proven)!=32 or data.get("pending") is not None:
        raise RuntimeError("XD_FINAL_CHECKPOINT_NOT_ALL_32")
    if [item["name"] for item in proven]!=[shape[0] for shape in STEPS]:
        raise RuntimeError("XD_FINAL_SHAPE_ORDER_CHANGED")
    if not all(item["status"]=="applied" for item in proven):
        raise RuntimeError("XD_FINAL_NON_APPLIED_RECEIPT")
    if len({item["guid"] for item in proven})!=32:
        raise RuntimeError("XD_FINAL_DUPLICATE_GUID")
    async with Client("http://127.0.0.1:8787/mcp") as c:
        health=await read(c,"creative.health")
        if health.get("bridge")!="connected" or health.get("pending_count")!=0:
            raise RuntimeError("XD_FINAL_BRIDGE_NOT_IDLE")
        graph=await read(c,"creative.scenegraph.list")
        if graph.get("complete") is not True or graph.get("document_id")!=data["document_id"]:
            raise RuntimeError("XD_FINAL_DOCUMENT_ID_MISMATCH")
        observed=node_map(graph)
        expected={p["name"]:p["guid"] for p in proven}
        if observed!=expected:
            raise RuntimeError("XD_FINAL_32_LIVE_NODES_MISMATCH")
    raw=PNG.read_bytes()
    if raw[:8]!=b"\x89PNG\r\n\x1a\n" or len(raw)<1000:
        raise RuntimeError("XD_FINAL_PNG_NOT_VALID")
    print("XD_E2E_FINAL_READBACK=PASS "+json.dumps({
      "applied":len(proven),"live_nodes":len(observed),
      "document":data["document_id"],
      "original_bytes":NATIVE.stat().st_size,
      "original_sha256":hashlib.sha256(NATIVE.read_bytes()).hexdigest(),
      "png_bytes":len(raw),"png_sha256":hashlib.sha256(raw).hexdigest(),
      "checkpoint_sha256":hashlib.sha256(CHECKPOINT.read_bytes()).hexdigest()
    }),flush=True)
asyncio.run(main())
