"""Live opt-in warm read-only benchmark through AdobeFastSession on MRCAO.

Uses the existing Adobe process, does not launch, edit, or save.
Readiness claims are derived from the actual host responses, not a caller flag.
"""
import asyncio
import json
import os
import statistics
import sys
import time
import traceback
from pathlib import Path
from mcp import Client
from mcp_adobe.fast_session import AdobeFastSession
from mcp_adobe.fast_path_v2 import Identity

def percentile(a,q):
    s=sorted(a)
    if not s: return None
    k=(len(s)-1)*q
    j=int(k)
    return round(s[j]+(s[min(j+1,len(s)-1)]-s[j])*(k-j),3)

async def benchmark(app):
    if app!="xd": raise RuntimeError("only XD host scenegraph can certify warm read-only state")
    if os.getenv("COMPUTERNAME")!="MRCAO" or os.getenv("ADOBE_SESSION")!="1":
        raise RuntimeError("MRCAO session 1 required")
    pid=int(os.environ["ADOBE_APP_PID"])
    if pid<=0: raise RuntimeError("invalid Adobe PID")
    rows=[]
    async with AdobeFastSession(app,enabled=True,client_factory=Client) as session:
        # Initial read must use normal transport: fast-path readiness cannot self-certify.
        first=await session.client.call_tool("creative_read",{
            "application":app,"capability":"creative.health",
            "arguments":{"probe":False,"timeout":5} if app=="illustrator" else {}})
        body=first.structured_content
        if first.is_error or not isinstance(body,dict) or body.get("ok") is not True:
            diagnostic={"is_error":bool(first.is_error),
                "structured_type":type(body).__name__,
                "structured_keys":sorted(str(k) for k in body.keys())[:20] if isinstance(body,dict) else [],
                "ok":body.get("ok") if isinstance(body,dict) else None,
                "error_code":str(body.get("error_code") or body.get("code") or "")[:100] if isinstance(body,dict) else "",
                "result_type":type(body.get("result")).__name__ if isinstance(body,dict) else "",
                "content_types":[type(x).__name__ for x in (first.content or [])][:5],
                "error_text":[str(getattr(x,"text",""))[:700] for x in (first.content or [])[:2]]}
            print("XD_INITIAL_HEALTH_DIAGNOSTIC="+json.dumps(diagnostic),flush=True)
            raise RuntimeError("initial health read failed: "+json.dumps(diagnostic))
        health=body.get("result") or {}
        if app=="illustrator":
            data=((health.get("connection") or {}).get("data") or {})
            layer=(data.get("layers") or {})
            exe=data.get("execution") or {}
            verified=(layer.get("panel") or {}).get("status")=="ok" and (layer.get("panel") or {}).get("busy") is False
            clean=not exe.get("unresolvedJobs") and exe.get("activeJob") is None and data.get("blocking") is None
            generation=str(pid)
            doc_generation="probe_false_unknown"
            capabilities=["creative.health"]
        elif app=="xd":
            verified=health.get("bridge")=="connected"
            clean=health.get("pending_count")==0
            sg=await session.client.call_tool("creative_read",{"application":app,"capability":"creative.scenegraph.list","arguments":{}})
            sgbody=sg.structured_content
            if sg.is_error or not isinstance(sgbody,dict) or sgbody.get("ok") is not True:
                raise RuntimeError("XD scenegraph not verified")
            snapshot=sgbody.get("result") or {}
            verified=verified and snapshot.get("complete") is True and bool(snapshot.get("document_id"))
            generation=str(pid)
            doc_generation=str(snapshot.get("document_id") or "")
            capabilities=["creative.health","creative.scenegraph.list"]
        else:
            # No Photoshop host-readback schema is certified here.
            raise RuntimeError("Photoshop fast path requires explicit trusted host verifier")
        if not verified or not clean: raise RuntimeError("host readiness or queue not verified")
        session.trusted_observe(Identity(app,pid,generation,doc_generation),
            host_readback_verified=True,no_unresolved_jobs=True)
        for capability in capabilities:
            for i in range(12):
                start=time.perf_counter()
                answer=await session.read(capability,{"probe":False,"timeout":5} if app=="illustrator" else {})
                elapsed=(time.perf_counter()-start)*1000
                if not isinstance(answer,dict): raise RuntimeError("invalid readback")
                if capability=="creative.health":
                    if answer.get("bridge")!="connected" or answer.get("pending_count")!=0:
                        session.coordinator.invalidate("bridge_disconnect")
                        raise RuntimeError("XD health changed during benchmark")
                if capability=="creative.scenegraph.list":
                    if answer.get("complete") is not True or answer.get("document_id")!=doc_generation:
                        session.coordinator.invalidate("document_changed")
                        raise RuntimeError("XD document generation changed during benchmark")
                rows.append({"capability":capability,"n":i+1,"ms":round(elapsed,3)})
        stats={cap:{"samples":len(v),"p50_ms":percentile(v,.5),"p95_ms":percentile(v,.95)}
               for cap in capabilities for v in [[r["ms"] for r in rows if r["capability"]==cap]]}
        return {"schema":"adobe-fast-session-live-readonly/v1","application":app,"pid":pid,
            "run_id":os.getenv("GITHUB_RUN_ID"),"statistics":stats,"rows":rows,
            "writes":0,"native_save":False,"full_e2e":False,"passed":True}

def main():
    if len(sys.argv)!=2: raise SystemExit("usage: fast_session_live_probe.py xd")
    output=Path(os.environ["ADOBE_FAST_REPORT"])
    try:
        record=asyncio.run(benchmark(sys.argv[1]))
    except Exception as exc:
        def flatten(error, depth=0):
            record={"type":type(error).__name__,"message":str(error)[:500],"depth":depth}
            children=getattr(error,"exceptions",())
            if children and depth<5:
                record["causes"]=[flatten(child,depth+1) for child in children[:8]]
            return record
        details=flatten(exc)
        print("ADOBE_FAST_EXCEPTION_TREE="+json.dumps(details),flush=True)
        traceback.print_exception(exc)
        record={"passed":False,"error":str(exc)[:250],"exception_tree":details,"application":sys.argv[1]}
    output.parent.mkdir(parents=True,exist_ok=True)
    temp=output.with_suffix(".tmp")
    temp.write_text(json.dumps(record,indent=2),encoding="utf-8")
    os.replace(temp,output)
    print("ADOBE_FAST_LIVE="+json.dumps({k:v for k,v in record.items() if k!="rows"}),flush=True)
    if not record["passed"]: raise SystemExit(2)

if __name__=="__main__": main()
