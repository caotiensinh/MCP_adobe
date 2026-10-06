from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path

from mcp import Client, StdioServerParameters


OUT_DIR = Path(os.environ.get("RUNNER_TEMP", ".")) / "mcp-adobe-photoshop-live-inspect"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _text_blocks(result) -> list[str]:
    texts: list[str] = []
    for item in getattr(result, "content", ()) or ():
        if getattr(item, "type", None) == "text":
            text = getattr(item, "text", None)
            if text:
                texts.append(str(text))
    return texts


def _image_blocks(result):
    for item in getattr(result, "content", ()) or ():
        if getattr(item, "type", None) == "image":
            yield item


async def main() -> None:
    params = StdioServerParameters(
        command="npx",
        args=["-y", "@alisaitteke/photoshop-mcp@1.7.32"],
        env={
            **os.environ,
            "LOG_LEVEL": "0",
            "PSMCP_FEEDBACK": "0",
            "PSMCP_UPDATE_CHECK": "0",
        },
    )

    async with Client(params) as client:
        listed = await client.list_tools()
        names = {tool.name for tool in listed.tools}
        for required in ("photoshop_ping", "photoshop_get_state", "photoshop_get_preview"):
            if required not in names:
                raise RuntimeError(f"required Photoshop MCP tool missing: {required}")

        ping = await client.call_tool("photoshop_ping", {})
        print("PHOTOSHOP_PING=" + " | ".join(_text_blocks(ping)))

        state = await client.call_tool("photoshop_get_state", {})
        state_text = "\n".join(_text_blocks(state))
        print("PHOTOSHOP_STATE=" + state_text.replace("\n", " "))
        (OUT_DIR / "photoshop-live-state.txt").write_text(state_text, encoding="utf-8")

        preview = await client.call_tool(
            "photoshop_get_preview",
            {"max_dimension_px": 1024, "quality": 10},
        )
        preview_text = "\n".join(_text_blocks(preview))
        (OUT_DIR / "photoshop-live-preview-metadata.txt").write_text(preview_text, encoding="utf-8")
        print("PHOTOSHOP_PREVIEW_METADATA=" + preview_text.replace("\n", " "))

        images = list(_image_blocks(preview))
        if not images:
            raise RuntimeError("photoshop_get_preview returned no MCP image content block")

        item = images[0]
        data = getattr(item, "data", None)
        if not data:
            raise RuntimeError("Photoshop MCP preview image block had no data")
        mime = getattr(item, "mime_type", None) or getattr(item, "mimeType", None) or "image/jpeg"
        suffix = ".png" if "png" in str(mime).lower() else ".jpg"
        out = OUT_DIR / f"photoshop-live-preview{suffix}"
        out.write_bytes(base64.b64decode(data))
        print(f"PHOTOSHOP_LIVE_PREVIEW=PASS path={out} bytes={out.stat().st_size} mime={mime}")


if __name__ == "__main__":
    asyncio.run(main())
