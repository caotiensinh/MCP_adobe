"""Pure geometric targeting for a user-drawn canvas annotation.

This module does not connect to or change the MCP transport. The caller must
obtain trustworthy document dimensions and layer bounds from the Adobe bridge.
Coordinates are DOCUMENT pixels, not screenshot or desktop pixels.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    def __post_init__(self) -> None:
        if not all(isfinite(v) for v in (self.left, self.top, self.right, self.bottom)):
            raise ValueError("rectangle coordinates must be finite")
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("rectangle must have positive size")

    @property
    def area(self) -> float:
        return (self.right - self.left) * (self.bottom - self.top)

    def overlap(self, other: "Rect") -> float:
        width = max(0.0, min(self.right, other.right) - max(self.left, other.left))
        height = max(0.0, min(self.bottom, other.bottom) - max(self.top, other.top))
        return width * height


def document_rect_from_viewport(
    *,
    stroke: Mapping[str, float],
    viewport: Mapping[str, float],
    document: Mapping[str, float],
) -> Rect:
    """Map a drag in viewport CSS px into unrotated document px.

    viewport: left/top of DOCUMENT ORIGIN on preview, scale = CSS pixels per
    document pixel.  This deliberately rejects rotation/skew instead of
    silently targeting the wrong Adobe object.
    """
    scale = float(viewport["scale"])
    if not isfinite(scale) or scale <= 0:
        raise ValueError("invalid viewport scale")
    if float(viewport.get("rotation", 0)) != 0:
        raise ValueError("rotated viewport unsupported; refresh preview")
    width, height = float(document["width"]), float(document["height"])
    if not all(isfinite(v) and v > 0 for v in (width, height)):
        raise ValueError("invalid document dimensions")
    xs = [(float(stroke[k]) - float(viewport["left"])) / scale for k in ("left", "right")]
    ys = [(float(stroke[k]) - float(viewport["top"])) / scale for k in ("top", "bottom")]
    if not all(isfinite(v) for v in xs + ys):
        raise ValueError("invalid stroke")
    l, r = sorted(xs)
    t, b = sorted(ys)
    if l < 0 or t < 0 or r > width or b > height:
        raise ValueError("selection outside document; refresh preview")
    return Rect(l, t, r, b)


def candidates_in_region(
    region: Rect,
    layers: Sequence[Mapping[str, Any]],
    *,
    min_overlap: float = 0.1,
) -> list[dict[str, Any]]:
    """Read-only candidates ranked by region coverage, never silently edit.

    Locked/hidden/background layers are rejected; ambiguous matches are
    retained for a user/agent disambiguation step.
    """
    if not 0 < min_overlap <= 1:
        raise ValueError("min_overlap must be between 0 and 1")
    result = []
    for layer in layers:
        if layer.get("visible") is False or layer.get("locked") is True or layer.get("background") is True:
            continue
        try:
            bounds = layer["bounds"]
            rect = Rect(*(float(bounds[k]) for k in ("left", "top", "right", "bottom")))
        except (KeyError, ValueError, TypeError):
            continue
        coverage = rect.overlap(region) / region.area
        if coverage >= min_overlap:
            result.append({
                "layer_id": layer.get("id"),
                "layer_name": str(layer.get("name", "")),
                "region_coverage": round(coverage, 4),
                "layer_bounds": dict(bounds),
            })
    result.sort(key=lambda x: (-x["region_coverage"], str(x["layer_id"])))
    return result


def resolve_annotation(
    *,
    stroke: Mapping[str, float],
    viewport: Mapping[str, float],
    document: Mapping[str, float],
    layers: Sequence[Mapping[str, Any]],
    document_identity: str,
    expected_document_identity: str,
) -> dict[str, Any]:
    """Return targets for review; NEVER issue a mutation based on coordinates alone."""
    if not document_identity or document_identity != expected_document_identity:
        raise ValueError("document changed since annotation; refresh")
    region = document_rect_from_viewport(stroke=stroke, viewport=viewport, document=document)
    found = candidates_in_region(region, layers)
    return {
        "status": "single_candidate" if len(found) == 1 else "ambiguous" if found else "no_candidate",
        "document_identity": document_identity,
        "region": vars(region),
        "candidates": found,
        "requires_confirmation": len(found) != 1,
    }
