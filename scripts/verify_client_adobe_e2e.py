"""Verify a fresh, real Photoshop MCP state after an external AI client run.

Exit nonzero unless the live Photoshop document contains a unique marker written
by the client. This intentionally cannot pass from a CLI response or fake log.
"""
from __future__ import annotations
import argparse
import asyncio
import json
from collections.abc import Mapping
from mcp import Client


def extract_payload(result):
    if result.is_error:
        raise RuntimeError(f"MCP tool error: {result.content}")
    data = result.structured_content
    if not isinstance(data, Mapping) or not data.get("ok"):
        raise RuntimeError(f"MCP returned no successful structured response: {data!r}")
    return data


async def verify(url: str, marker: str) -> None:
    async with Client(url) as client:
        listed = {tool.name for tool in (await client.list_tools()).tools}
        required = {"creative_discover", "creative_read", "creative_write",
                    "creative_live_build", "creative_authorized_write"}
        if not required.issubset(listed):
            raise RuntimeError(f"Missing gateway tools: {sorted(required - listed)}")
        health = extract_payload(await client.call_tool("creative_read", {
            "application": "photoshop", "capability": "creative.health", "arguments": {}
        }))
        if not health.get("result"):
            raise RuntimeError("Live Photoshop health had no upstream result")
        layer_data = extract_payload(await client.call_tool("creative_read", {
            "application": "photoshop", "capability": "creative.layer.list", "arguments": {}
        }))
        result = layer_data.get("result", {})
        raw = result.get("text", "") if isinstance(result, Mapping) else ""
        if marker not in raw:
            raise RuntimeError(f"CLIENT_TO_ADOBE_E2E=FAIL marker {marker!r} absent from live Photoshop read-back")
        context = extract_payload(await client.call_tool("creative_read", {
            "application": "photoshop", "capability": "creative.context.get", "arguments": {}
        }))
        if not context.get("result"):
            raise RuntimeError("No Photoshop context from real upstream")
        print(json.dumps({"status": "PASS", "marker": marker,
                          "photoshop_health": "connected", "live_readback": True,
                          "tool_count": len(listed)}, ensure_ascii=False), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8787/mcp")
    parser.add_argument("--marker", required=True)
    args = parser.parse_args()
    if len(args.marker) < 14 or not args.marker.startswith("MCP-E2E-"):
        parser.error("marker must be a unique MCP-E2E-* test identifier")
    asyncio.run(verify(args.url, args.marker))


if __name__ == "__main__":
    main()
