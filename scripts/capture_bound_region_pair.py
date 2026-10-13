"""Fail-closed paired preview/metadata snapshot using existing read-only MCP.

Double-read consistency is evidence of stability, NOT proof of an atomic Adobe
revision. Never mark the preview as trusted for automatic targeted writes.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import os
import struct
from pathlib import Path
from mcp import Client
from scripts.capture_region_preview import decode_preview
from scripts.export_region_metadata import normalize_snapshot, payload


def preview_dimensions(binary: bytes, extension: str) -> tuple[int, int]:
    """Parse PNG/JPEG dimensions without trusting file names or third-party libs."""
    if extension == ".png":
        if len(binary) < 24 or not binary.startswith(bytes.fromhex("89504e470d0a1a0a")) or binary[12:16] != b"IHDR":
            raise ValueError("Invalid PNG preview header")
        width, height = struct.unpack(">II", binary[16:24])
    elif extension == ".jpg":
        if not binary.startswith(bytes.fromhex("ffd8ff")):
            raise ValueError("Invalid JPEG preview header")
        pos = 2
        width = height = 0
        while pos + 4 <= len(binary):
            if binary[pos] != 0xFF:
                raise ValueError("Invalid JPEG preview marker")
            while pos < len(binary) and binary[pos] == 0xFF:
                pos += 1
            if pos >= len(binary):
                break
            marker = binary[pos]
            pos += 1
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            if pos + 2 > len(binary):
                break
            length = int.from_bytes(binary[pos:pos + 2], "big")
            if length < 2 or pos + length > len(binary):
                break
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if length < 7:
                    break
                height = int.from_bytes(binary[pos + 3:pos + 5], "big")
                width = int.from_bytes(binary[pos + 5:pos + 7], "big")
                break
            pos += length
    else:
        raise ValueError("Unsupported preview image type")
    if not (0 < width <= 32768 and 0 < height <= 32768):
        raise ValueError("Invalid preview dimensions")
    return width, height


def assert_preview_frame(binary: bytes, extension: str, metadata: dict) -> tuple[int, int]:
    width, height = preview_dimensions(binary, extension)
    expected_width, expected_height = float(metadata["width"]), float(metadata["height"])
    if abs(width / height - expected_width / expected_height) > 0.002:
        raise ValueError("Preview aspect ratio differs from live Adobe document")
    return width, height


def stable_fingerprint(metadata: dict) -> str:
    fields = {key: metadata[key] for key in ("application", "document_identity", "width", "height", "layers")}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def compare_snapshots(before: dict, after: dict) -> str:
    if stable_fingerprint(before) != stable_fingerprint(after):
        raise ValueError("Document/layer snapshot changed during preview; reject stale pair")
    return stable_fingerprint(before)


async def pair_photoshop(url: str) -> tuple[bytes, str, dict]:
    async with Client(url) as client:
        async def read(capability: str):
            return await client.call_tool("creative_read", {
                "application": "photoshop", "capability": capability, "arguments": {},
            })
        async def metadata():
            state = payload(await read("creative.context.get"))
            layers = payload(await read("creative.layer.list"))
            return normalize_snapshot(state, layers, "photoshop")
        before = await metadata()
        binary, extension = decode_preview(await read("creative.document.preview"))
        after = await metadata()
        fingerprint = compare_snapshots(before, after)
        image_width, image_height = assert_preview_frame(binary, extension, after)
        metadata_result = dict(after)
        metadata_result["preview_binding"] = {
            "status": "stable_double_read_unverified_revision",
            "metadata_sha256": fingerprint,
            "image_width": image_width,
            "image_height": image_height,
            "preview_sha256": hashlib.sha256(binary).hexdigest(),
            "preview_frame_verified": False,
            "atomic_revision_verified": False,
            "requires_live_document_identity_check": True,
        }
        return binary, extension, metadata_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8787/mcp")
    parser.add_argument("--output-prefix", required=True)
    args = parser.parse_args()
    binary, ext, meta = asyncio.run(pair_photoshop(args.url))
    base = Path(args.output_prefix)
    image = base.with_suffix(ext)
    metadata = base.with_suffix(".json")
    if image.exists() or metadata.exists():
        parser.error("Refusing to overwrite existing pair")
    # Two output paths are not an atomic transaction: stage both and roll back
    # any published member if the second publication fails.
    image_tmp = image.with_name(image.name + ".partial")
    metadata_tmp = metadata.with_name(metadata.name + ".partial")
    if image_tmp.exists() or metadata_tmp.exists():
        parser.error("Refusing to overwrite pre-existing partial capture")
    published = []
    try:
        with image_tmp.open("xb") as out:
            out.write(binary)
        with metadata_tmp.open("x", encoding="utf-8") as out:
            json.dump(meta, out, indent=2, ensure_ascii=False)
        os.replace(image_tmp, image)
        published.append(image)
        os.replace(metadata_tmp, metadata)
        published.append(metadata)
    except BaseException:
        for target in published:
            target.unlink(missing_ok=True)
        raise
    finally:
        image_tmp.unlink(missing_ok=True)
        metadata_tmp.unlink(missing_ok=True)
    print("PREVIEW_PAIR=STABLE_DOUBLE_READ; ATOMIC_REVISION=UNVERIFIED")
    print(f"PREVIEW_IMAGE={image} PREVIEW_METADATA={metadata}")


if __name__ == "__main__":
    main()
