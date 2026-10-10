"""Fail-closed paired preview/metadata snapshot using existing read-only MCP.

Double-read consistency is evidence of stability, NOT proof of an atomic Adobe
revision. Never mark the preview as trusted for automatic targeted writes.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from mcp import Client
from scripts.capture_region_preview import decode_preview
from scripts.export_region_metadata import normalize_snapshot, payload


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
        metadata_result = dict(after)
        metadata_result["preview_binding"] = {
            "status": "stable_double_read_unverified_revision",
            "metadata_sha256": fingerprint,
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
    image.write_bytes(binary)
    metadata.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print("PREVIEW_PAIR=STABLE_DOUBLE_READ; ATOMIC_REVISION=UNVERIFIED")
    print(f"PREVIEW_IMAGE={image} PREVIEW_METADATA={metadata}")


if __name__ == "__main__":
    main()
