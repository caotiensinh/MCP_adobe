"""Forensic, strictly read-only recovery of the one Illustrator red poster write.

DO NOT replay first shape. The preceding MCP upstream returned
execution=succeeded but its next document read timed out. The actual live
document must be inspected before any new mutation or restart.
"""
import asyncio, hashlib, json, os, time
from pathlib import Path
from mcp import Client

SOURCE_RUN="38146162392"
EXPECTED_DOC="MCP_KFP4_Red_AI_"+SOURCE_RUN+".ai"
EXPECTED_PART="001 Deep red poster background"
PATH=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"/EXPECTED_DOC
ROOT=Path("red_ai_reconcile")
ROOT.mkdir(parents=True,exist_ok=True)
RESULTS={"schema":"mcp-adobe-red-ai-reconcile/v1","original_run":SOURCE_RUN,
 "machine":os.getenv("COMPUTERNAME"),"original_document":EXPECTED_DOC,
 "write_policy":"READ_ONLY_STOP_IF_UNKNOWN","queries":[]}

async def query(c,cap,args,timeout=12):
    t=time.perf_counter()
    try:
        r=await asyncio.wait_for(c.call_tool("creative_read",{
          "application":"illustrator","capability":cap,"arguments":args}),timeout=timeout)
        payload=r.structured_content or {}
        result=payload.get("result") or {}
        record={"capability":cap,"ms":round((time.perf_counter()-t)*1000,2),
          "is_error":r.is_error,"ok":not r.is_error and payload.get("ok") is True,
          "result":result if cap=="creative.health" else str(result)[:6500],
          "error_content":[str(x)[:450] for x in r.content] if r.is_error else []}
    except Exception as exc:
        record={"capability":cap,"ms":round((time.perf_counter()-t)*1000,2),"ok":False,
         "error_type":type(exc).__name__,"error":str(exc)[:450]}
    RESULTS["queries"].append(record)
    print("RED_AI_FORENSIC_READ="+json.dumps(record,default=str)[:13000],flush=True)
    return record

async def main():
    if os.getenv("COMPUTERNAME")!="MRCAO":
        raise RuntimeError("RED_AI_FORENSIC_WRONG_MACHINE")
    if PATH.is_file():
        RESULTS["saved_file"]={"exists":True,"bytes":PATH.stat().st_size,
            "sha256":hashlib.sha256(PATH.read_bytes()).hexdigest()}
    else:RESULTS["saved_file"]={"exists":False}
    print("RED_AI_FORENSIC_PERSISTED="+json.dumps(RESULTS["saved_file"]),flush=True)
    try:
        async with Client("http://127.0.0.1:8787/mcp") as c:
            health=await query(c,"creative.health",{"probe":False,"timeout":5},timeout=16)
            if not health.get("ok"):
                RESULTS["stop"]="health_failure_no_host_mutation"
                return
            data=(health.get("result") or {}).get("connection",{}).get("data",{})
            panel=(data.get("layers") or {}).get("panel") or {}
            execution=data.get("execution") or {}
            doc=(data.get("layers") or {}).get("document") or {}
            RESULTS["host"]={"panel":panel,"execution":execution,
                  "document":doc,"blockedAt":data.get("blockedAt"),
                  "blocking":data.get("blocking")}
            if (panel.get("status")!="ok" or panel.get("busy") is not False
                or execution.get("activeJob") is not None or
                execution.get("unresolvedJobs") or execution.get("waiting")!=0):
                RESULTS["stop"]="host_not_idle_preserve_possible_applied_write"
                return
            info=await query(c,"creative.document.info",{},timeout=43)
            if not info.get("ok"):
                RESULTS["stop"]="document_readback_unknown_no_replay"
                return
            RESULT_TEXT=info.get("result","")
            if EXPECTED_PART in RESULT_TEXT and EXPECTED_DOC in RESULT_TEXT:
                RESULTS["status"]="existing_red_rectangle_found_read_only"
            else:
                RESULTS["status"]="document_received_manual_reconcile_required"
            # Additional metadata calls are deliberately skipped when the full
            # document result is questionable, to avoid filling CEP queue.
    finally:
        ROOT.joinpath("reconcile.json").write_text(json.dumps(RESULTS,indent=2,default=str),encoding="utf-8")
        print("RED_AI_FORENSIC_PERSISTED_REPORT="+json.dumps({"status":RESULTS.get("status"),
            "stop":RESULTS.get("stop"),"report":"red_ai_reconcile/reconcile.json"}),flush=True)

if __name__=="__main__":
    asyncio.run(main())
