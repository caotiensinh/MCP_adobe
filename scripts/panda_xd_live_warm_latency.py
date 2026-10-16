"""Measure *successful* warm XD MPC health and scenegraph reads, never writes.

Use existing Gateway and UXP session; no process restarts or plugin installs.
A failed tool response counts as failure, never a fast successful sample.
"""
import asyncio
import json
import os
import statistics
import time
from pathlib import Path
from mcp import Client

URL="http://127.0.0.1:8787/mcp"
SAMPLES=30
values={}
events=[]
def observe(name,t0,valid,error=""):
    duration=round((time.perf_counter()-t0)*1000,3)
    events.append({"phase":name,"latency_ms":duration,"success":valid,"error":error[:200]})
    values.setdefault(name,[]).append(duration if valid else None)
    print("XD_MCP_SPEED_SAMPLE="+json.dumps(events[-1]),flush=True)
def percentile(numbers,p):
    nums=sorted(x for x in numbers if x is not None)
    if not nums:return None
    k=(len(nums)-1)*p
    a=int(k); b=min(len(nums)-1,a+1)
    return round(nums[a]+(nums[b]-nums[a])*(k-a),3)
def summarize():
    return {k:{"total":len(v),"success":sum(x is not None for x in v),
      "p50_ms":percentile(v,.5),"p95_ms":percentile(v,.95),
      "p99_ms":percentile(v,.99)} for k,v in values.items()}

async def call(client,cap):
    t=time.perf_counter()
    try:
        out=await asyncio.wait_for(client.call_tool("creative_read",{
          "application":"xd","capability":cap,"arguments":{}}),timeout=6)
        if out.is_error or not isinstance(out.structured_content,dict) or out.structured_content.get("ok") is not True:
            raise RuntimeError("MCP error "+str(out.content)[:170])
        result=out.structured_content.get("result")
        if not isinstance(result,dict):raise RuntimeError("missing XD result")
        if cap=="creative.health":
            if result.get("bridge")!="connected" or result.get("pending_count")!=0:
                raise RuntimeError("XD bridge not connected/idle")
        elif cap=="creative.scenegraph.list":
            if not result.get("complete") or result.get("document_id")!= "98d6635b-3767-4254-b200-ec8442b69ad2":
                raise RuntimeError("scenegraph document/complete mismatch")
            artboards=result.get("nodes") or []
            if len(artboards)!=1 or len(artboards[0].get("children") or [])!=32:
                raise RuntimeError("XD 32-node saved scene not found")
        observe("warm_"+("health" if cap=="creative.health" else "readback"),t,True)
        return result
    except Exception as exc:
        observe("warm_"+("health" if cap=="creative.health" else "readback"),t,False,type(exc).__name__+":"+str(exc))
        raise

async def main():
    result={"version":"xd-live-warm-speed/v1","machine":os.environ.get("COMPUTERNAME"),
      "github_run_id":os.environ.get("GITHUB_RUN_ID"),
      "session_contract":"read-only, persistent Gateway, no Adobe restart"}
    async with Client(URL) as c:
        for phase,cap in (("warm_health","creative.health"),("warm_readback","creative.scenegraph.list")):
            for _ in range(SAMPLES):
                await call(c,cap)
        for _ in range(10):
            t=time.perf_counter()
            try:
                async with Client(URL) as cold:
                    await call(cold,"creative.health")
                observe("new_client_session",t,True)
            except Exception as exc:
                observe("new_client_session",t,False,type(exc).__name__+":"+str(exc))
    result["statistics"]=summarize()
    result["events"]=events
    Path("xd_warm_latency.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("XD_MCP_SPEED_SUMMARY="+json.dumps(result["statistics"]),flush=True)
    for phase in ("warm_health","warm_readback","new_client_session"):
        obj=result["statistics"][phase]
        if obj["success"]!=obj["total"] or obj["p95_ms"] is None or obj["p95_ms"]>1000:
            raise RuntimeError("XD_WARM_SPEED_SLO_FAIL "+phase)
    print("XD_MCP_WARM_HEALTH_READBACK_SLO=PASS; shape-write-latency-NOT-MEASURED",flush=True)
asyncio.run(main())
