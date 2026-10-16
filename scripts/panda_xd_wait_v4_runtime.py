"""Wait for the actual Adobe XD UXP bridge build v4 after a single GUI reload."""
import asyncio,time,json
from mcp import Client
async def main():
    expiry=time.monotonic()+65
    last=None
    while time.monotonic()<expiry:
        try:
            async with Client("http://127.0.0.1:8787/mcp") as c:
                r=await c.call_tool("creative_read",{
                    "application":"xd","capability":"creative.health","arguments":{}})
                data=(r.structured_content or {}).get("result") or {}
                last={"status":data.get("bridge"),"build":data.get("bridge_build"),
                      "pending":data.get("pending_count"),"error":r.is_error}
                if data.get("bridge")=="connected" and data.get("bridge_build")=="xd-ellipse-radius-geometry-v4" and data.get("pending_count")==0:
                    x=await c.call_tool("creative_discover",{})
                    arr=(x.structured_content or {}).get("applications") or []
                    xd=next((v for v in arr if v.get("application")=="xd"),{})
                    if "xd.queue.ellipse_geometry_repair" not in (xd.get("native_capabilities") or []):
                        raise RuntimeError("XD_RADIUS_V4_GATEWAY_ADAPTER_NOT_INSTALLED")
                    print("XD_ELLIPSE_V4_RUNTIME=PASS "+json.dumps(last),flush=True)
                    return
        except Exception as e:
            last={"exception":type(e).__name__,"message":str(e)[:250]}
        await asyncio.sleep(2.0)
    raise RuntimeError("XD_ELLIPSE_V4_RUNTIME_NOT_OBSERVED_NO_REPEAT_RELOAD "+json.dumps(last))
asyncio.run(main())
