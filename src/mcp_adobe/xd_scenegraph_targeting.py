"""Normalize Adobe XD read-only scenegraph snapshots for region selection.

No bridge/network side effects. Requires stable document identity and node IDs.
The bridge must explicitly supply a scenegraph snapshot; selection-only data is
not silently presented as all-canvas hit testing.
"""
from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any


def _rect(raw: Any) -> dict[str, float]:
    if not isinstance(raw, Mapping):
        raise ValueError("node bounds unavailable")
    bounds = {k: float(raw[k]) for k in ("left", "top", "right", "bottom")}
    if not all(isfinite(v) for v in bounds.values()):
        raise ValueError("nonfinite node bounds")
    if bounds["right"] <= bounds["left"] or bounds["bottom"] <= bounds["top"]:
        raise ValueError("nonpositive node bounds")
    return bounds


def flatten_scenegraph(snapshot: Mapping[str, Any], *, max_nodes: int = 20000) -> list[dict[str, Any]]:
    """Depth-first walk; fail closed for duplicate IDs or malformed structure.

    Input schema:
      {"complete":true, "nodes":[{"id":"...", "bounds":{...}, "children":[...]}]}
    Children must have GLOBAL document-coordinate bounds, not parent-relative
    bounds; coordinates are never inferred from artboard screenshot geometry.
    """
    if snapshot.get("complete") is not True:
        raise ValueError("incomplete XD scenegraph; region targeting prohibited")
    roots = snapshot.get("nodes")
    if not isinstance(roots, list):
        raise ValueError("XD scenegraph must contain nodes array")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    stack = list(reversed(roots))
    while stack:
        node = stack.pop()
        if len(result) >= max_nodes:
            raise ValueError("XD scenegraph exceeds safety node limit")
        if not isinstance(node, Mapping) or node.get("id") is None:
            raise ValueError("XD node missing stable ID")
        node_id = str(node["id"])
        if node_id in seen:
            raise ValueError("duplicate XD node ID")
        seen.add(node_id)
        children = node.get("children", [])
        if not isinstance(children, list):
            raise ValueError("XD node children malformed")
        stack.extend(reversed(children))
        if node.get("visible") is False or node.get("locked") is True:
            continue
        try:
            bounds = _rect(node.get("bounds"))
        except (TypeError, KeyError, ValueError):
            if children:
                continue  # Containers can have child bounds but no own bounds.
            raise
        result.append({
            "id": node_id, "name": str(node.get("name", "")),
            "bounds": bounds, "visible": True, "locked": False,
            "background": bool(node.get("background", False)),
            "node_type": str(node.get("type", "")),
        })
    return result


def normalize_xd_scenegraph(
    document: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> dict[str, Any]:
    doc_id = document.get("id")
    width, height = document.get("width"), document.get("height")
    if doc_id is None or not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
        raise ValueError("XD document identity or dimensions unavailable")
    if not all(isfinite(float(v)) and float(v) > 0 for v in (width, height)):
        raise ValueError("invalid XD document dimensions")
    if str(snapshot.get("document_id")) != str(doc_id):
        raise ValueError("XD scenegraph document mismatch")
    layers = flatten_scenegraph(snapshot)
    if not layers:
        raise ValueError("no targetable XD nodes")
    return {"application": "xd", "document_identity": str(doc_id),
            "width": float(width), "height": float(height), "layers": layers}
