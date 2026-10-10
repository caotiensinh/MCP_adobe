"""Read-only live Adobe desktop readiness report through current MCP gateway."""
from __future__ import annotations
import asyncio
import json
from mcp import Client

APPS = ("photoshop", "illustrator", "xd")

async def main():
    async with Client("http://127.0.0.1:8787/mcp") as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        if "creative_read" not in tools:
            raise RuntimeError("creative_read not present")
        results = {}
        for app in APPS:
            try:
                r = await asyncio.wait_for(client.call_tool("creative_read", {
                    "application": app, "capability": "creative.health", "arguments": {}
                }), timeout=20)
                # Report only status; do not expose Photoshop documents or sensitive responses.
                results[app] = "MCP_ERROR" if r.is_error else "MCP_READ_RETURNED"
            except Exception as e:
                results[app] = "CALL_FAILED:" + type(e).__name__
        print("ADOBE_DIRECT_READINESS=" + json.dumps(results, sort_keys=True), flush=True)
        if not all(x == "MCP_READ_RETURNED" for x in results.values()):
            raise SystemExit("ADOBE_DIRECT_ACCEPTANCE=BLOCKED")
        print("ADOBE_DIRECT_ACCEPTANCE=HEALTH_READS_PASS; desktop GUI interaction not proven")


if __name__ == "__main__":
    asyncio.run(main())
