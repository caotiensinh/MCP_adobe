"""Read-only live Adobe desktop connection diagnostics; never configures MCP."""
import asyncio
import json
import os
from mcp import Client

APPS=("photoshop","illustrator","xd")

async def main():
    async with Client(os.getenv("MCP_ADOBE_URL","http://127.0.0.1:8787/mcp")) as client:
        tools={t.name for t in (await client.list_tools()).tools}
        if "creative_read" not in tools:
            print("MCP_GATEWAY=FAIL missing creative_read")
            return
        print("MCP_GATEWAY=PASS creative_read advertised",flush=True)
        for app in APPS:
            try:
                result=await asyncio.wait_for(client.call_tool("creative_read",{
                    "application":app,"capability":"creative.health","arguments":{}
                }),timeout=15)
                # A successful MCP response is not automatically a connected desktop.
                raw=result.structured_content
                if raw is None:
                    raw=[getattr(block,"text","") for block in result.content or []]
                if result.is_error or (isinstance(raw,dict) and raw.get("ok") is False):
                    status="FAIL"
                else:
                    status="UNVERIFIED"  # exact Adobe app readiness needs live payload inspection
                print(f"ADOBE_{app.upper()}_HEALTH={status} response_type={type(raw).__name__}",flush=True)
            except Exception as exc:
                print(f"ADOBE_{app.upper()}_HEALTH=FAIL reason={type(exc).__name__}",flush=True)

asyncio.run(main())
