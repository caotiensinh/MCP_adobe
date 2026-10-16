"""Capture a real Photoshop preview through the EXISTING read-only MCP capability.

Do not invent Illustrator/XD screenshot support: they currently lack read-only
raster preview in their adapters. The output is an untrusted UNBOUND image until
the operator pairs it with a same-document verified metadata snapshot.
"""
from __future__ import annotations
import argparse
import asyncio
import base64
import binascii
from pathlib import Path
from mcp import Client

PNG_MAGIC = bytes.fromhex("89504e470d0a1a0a")
JPEG_MAGIC = bytes.fromhex("ffd8ff")
MAX_IMAGE = 32 * 1024 * 1024


def decode_preview(result) -> tuple[bytes, str]:
    if result.is_error:
        raise ValueError("Adobe preview tool failed")
    for block in result.content or []:
        if getattr(block, "type", "") != "image":
            continue
        mime = getattr(block, "mimeType", "")
        if mime not in {"image/png", "image/jpeg"}:
            continue
        try:
            binary = base64.b64decode(block.data, validate=True)
        except (binascii.Error, TypeError):
            raise ValueError("Corrupt MCP preview image data") from None
        if not binary or len(binary) > MAX_IMAGE:
            raise ValueError("Preview exceeds safe size")
        if mime == "image/png" and binary.startswith(PNG_MAGIC):
            return binary, ".png"
        if mime == "image/jpeg" and binary.startswith(JPEG_MAGIC):
            return binary, ".jpg"
        raise ValueError("Preview mime and signature disagree")
    raise ValueError("No MCP image block returned; no trustworthy canvas preview")


async def capture(url: str, application: str) -> tuple[bytes, str]:
    if application != "photoshop":
        raise ValueError(f"{application} has no verified read-only raster preview capability yet")
    async with Client(url) as client:
        response = await client.call_tool("creative_read", {
            "application": application,
            "capability": "creative.document.preview",
            "arguments": {},
        })
        return decode_preview(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application", choices=["photoshop", "illustrator", "xd"], required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8787/mcp")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    image, ext = asyncio.run(capture(args.url, args.application))
    target = Path(args.output)
    if target.suffix.lower() != ext:
        parser.error(f"output extension must match preview type ({ext})")
    target.write_bytes(image)
    print(f"PREVIEW_CAPTURE=PASS application={args.application} bytes={len(image)} source=live-MCP-image-block")
    print("PREVIEW_FRAME_BINDING=UNVERIFIED; do NOT enable automated region edits")


if __name__ == "__main__":
    main()
