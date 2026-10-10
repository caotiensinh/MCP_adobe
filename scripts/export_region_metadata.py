"""Read-only Adobe document/object snapshot for canvas annotation UI.

No MCP transport, auth, or write path is changed. Fails closed when the
upstream does not expose reliable dimensions, identity, or layer bounds.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mcp import Client


def unwrap(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return unwrap(json.loads(value))
        except json.JSONDecodeError:
            return value
    if isinstance(value, Mapping):
        for key in ("result", "structuredContent", "data"):
            if key in value and isinstance(value[key], (Mapping, list, str)):
                nested = unwrap(value[key])
                if isinstance(nested, Mapping) and any(
                    k in nested for k in ("document", "hasDocument", "layers", "width", "activeLayer")
                ):
                    return nested
        if "text" in value:
            nested = unwrap(value["text"])
            if isinstance(nested, (Mapping, list)):
                return nested
        return value
    if isinstance(value, list):
        if len(value) == 1:
            return unwrap(value[0])
        return [unwrap(item) for item in value]
    return value


def normalize_snapshot(state: Mapping[str, Any], layers_payload: Any, application: str = "photoshop") -> dict[str, Any]:
    if application not in {"photoshop", "illustrator", "xd"}:
        raise ValueError("Unsupported Adobe application")
    state = unwrap(state)
    layers_payload = unwrap(layers_payload)
    if not isinstance(state, Mapping) or state.get("hasDocument") is False:
        raise ValueError("No active Photoshop document")
    doc = state.get("document", state)
    if not isinstance(doc, Mapping):
        raise ValueError("Photoshop document metadata unavailable")
    width = doc.get("width", state.get("width"))
    height = doc.get("height", state.get("height"))
    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)) or width <= 0 or height <= 0:
        raise ValueError("Real document dimensions unavailable")
    identity = doc.get("id") or doc.get("documentId") or state.get("documentId")
    if identity is None:
        raise ValueError("Document ID unavailable: refuse stale-targeting risk")
    if application == "xd" and isinstance(layers_payload, Mapping) and layers_payload.get("complete") is True:
        from mcp_adobe.xd_scenegraph_targeting import normalize_xd_scenegraph
        return normalize_xd_scenegraph(doc, layers_payload)
    raw_layers = (layers_payload.get("layers", layers_payload.get("items")) if isinstance(layers_payload, Mapping) else layers_payload)
    if application == "xd" and isinstance(layers_payload, Mapping) and not isinstance(raw_layers, list):
        selected = layers_payload.get("selection", layers_payload.get("selectedItems"))
        if isinstance(selected, list):
            raw_layers = selected
        elif isinstance(selected, Mapping):
            raw_layers = [selected]
        elif "bounds" in layers_payload:
            raw_layers = [layers_payload]
    if not isinstance(raw_layers, list):
        raise ValueError("Layer list not available")
    layers = []
    for item in raw_layers:
        if not isinstance(item, Mapping):
            continue
        bounds = item.get("bounds")
        if not isinstance(bounds, Mapping) or not all(k in bounds for k in ("left", "top", "right", "bottom")):
            continue
        if item.get("id") is None:
            continue
        layers.append({
            "id": item["id"], "name": str(item.get("name", "")),
            "bounds": {k: float(bounds[k]) for k in ("left", "top", "right", "bottom")},
            "visible": item.get("visible", True), "locked": item.get("locked", False),
            "background": item.get("background", False),
        })
    if not layers:
        raise ValueError("No layers with stable IDs and bounds; manual metadata required")
    return {"application": application, "document_identity": str(identity),
            "width": float(width), "height": float(height), "layers": layers}


def normalize_xd_canvas_snapshot(scenegraph: Any, frame: Any) -> dict[str, Any]:
    from mcp_adobe.xd_scenegraph_targeting import normalize_xd_scenegraph
    scenegraph, frame = unwrap(scenegraph), unwrap(frame)
    if not isinstance(scenegraph, Mapping) or not isinstance(frame, Mapping):
        raise ValueError("XD scenegraph or canvas frame missing")
    if str(frame.get("document_id")) != str(scenegraph.get("document_id")):
        raise ValueError("XD scenegraph/frame document mismatch")
    width, height = frame.get("width"), frame.get("height")
    left, top = frame.get("left"), frame.get("top")
    if not all(isinstance(v, (int, float)) for v in (width, height, left, top)):
        raise ValueError("XD canvas frame coordinates unavailable")
    result = normalize_xd_scenegraph(
        {"id": frame["document_id"], "width": width, "height": height}, scenegraph
    )
    for layer in result["layers"]:
        bounds = layer["bounds"]
        bounds["left"] -= left
        bounds["right"] -= left
        bounds["top"] -= top
        bounds["bottom"] -= top
    result["coordinate_frame"] = {"left": left, "top": top, "space": "artboard_union"}
    return result


def payload(result: Any) -> Any:
    if result.is_error:
        kinds = [type(block).__name__ for block in (result.content or [])]
        # Surface only a bounded upstream error hint; never print full payloads or secrets.
        import re
        hints = []
        for block in result.content or []:
            message = getattr(block, "text", "")
            if isinstance(message, str):
                message = re.sub(r"(?i)(token|password|secret|authorization|api[_-]?key)\s*[:=]\s*[^\s,}]+", r"\1=[REDACTED]", message)
                message = re.sub(r"https?://\S+", "[URL_REDACTED]", message)
                hints.append(message[:350].replace("\n", " "))
        raise RuntimeError(f"Adobe MCP read rejected; content_block_types={kinds}; hints={hints[:2]}")
    value = result.structured_content
    if value is None:
        value = [{"text": block.text} for block in result.content if hasattr(block, "text")]
    if isinstance(value, Mapping) and value.get("ok") is False:
        raise RuntimeError("Adobe bridge reported a failed read")
    return unwrap(value)


async def capture(url: str, application: str = "photoshop") -> dict[str, Any]:
    if application not in {"photoshop", "illustrator", "xd"}:
        raise ValueError("Unsupported Adobe application")
    async with Client(url) as client:
        listed = {t.name for t in (await client.list_tools()).tools}
        if "creative_read" not in listed:
            raise RuntimeError("MCP creative_read unavailable")
        async def read(capability: str) -> Any:
            result = await client.call_tool("creative_read", {
                "application": application, "capability": capability, "arguments": {},
            })
            try:
                return payload(result)
            except RuntimeError as exc:
                raise RuntimeError(f"{application} capability={capability} failed: {exc}") from None
        health = await read("creative.health")
        print(f"REGION_METADATA_HEALTH=PASS application={application}", flush=True)
        state = await read("creative.context.get")
        layers = await read("creative.scenegraph.list" if application == "xd" else "creative.layer.list")
        if application == "xd":
            frame = await read("creative.canvas.frame")
            return normalize_xd_canvas_snapshot(layers, frame)
        return normalize_snapshot(state, layers, application=application)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8787/mcp")
    parser.add_argument("--application", choices=("photoshop", "illustrator", "xd"), default="photoshop")
    parser.add_argument("--output", default="adobe_region_metadata.json")
    args = parser.parse_args()
    result = asyncio.run(capture(args.url, args.application))
    out = Path(args.output)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"REGION_METADATA=PASS layers={len(result['layers'])} path={out}")


if __name__ == "__main__":
    main()
