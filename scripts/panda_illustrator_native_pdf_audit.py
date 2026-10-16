"""Read-only Illustrator native PDF-compatible geometry comparison.

Never opens Illustrator, sends any host command, or modifies native files.
A SHA change alone is persistence evidence, NOT proof of two vector objects.
Reports stronger geometry evidence only if both native files expose comparable
PDF drawing operators. Inapplicable PDF parsing is explicitly UNVERIFIED.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

BASELINE_SHA = "25d46aaacc766759d11c920872d9ee1cc26861a145826143161698e97ca14b77"
TARGET_SHA = "ec6d2239b3547845c16c80997ca716f50fb8e5f4f5f3f8d57e85079581fa89a2"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def drawing_geometry(path: Path) -> dict:
    try:
        import fitz
    except ImportError as exc:
        return {"status": "NO_PDF_PARSER", "reason": type(exc).__name__}
    try:
        with fitz.open(str(path)) as native:
            if not native.is_pdf or native.page_count < 1:
                return {"status": "NOT_PDF_COMPATIBLE"}
            pages = []
            for page in native:
                drawings = []
                for item in page.get_drawings():
                    rect = item.get("rect")
                    if rect is None:
                        continue
                    points = [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]
                    if not all(math.isfinite(z) for z in points):
                        continue
                    color = item.get("fill")
                    drawings.append({
                        "bbox": [round(z, 2) for z in points],
                        "width": round(points[2] - points[0], 2),
                        "height": round(points[3] - points[1], 2),
                        "filled": color is not None,
                        "fill_rgb": [round(float(v), 3) for v in color[:3]] if color is not None else None,
                    })
                pages.append({
                    "index": page.number,
                    "width": round(float(page.rect.width), 2),
                    "height": round(float(page.rect.height), 2),
                    "drawings": drawings,
                    "drawing_count": len(drawings)
                })
            return {"status": "PDF_GEOMETRY_READ", "pages": pages}
    except Exception as exc:
        return {"status": "PDF_PARSE_FAILED", "error_type": type(exc).__name__,
                "error": str(exc)[:180]}


def comparable_second_vector(base: dict, after: dict) -> dict:
    if base.get("status") != "PDF_GEOMETRY_READ" or after.get("status") != "PDF_GEOMETRY_READ":
        return {"verified": False, "reason": "NO_COMPARABLE_NATIVE_PDF_GEOMETRY"}
    a, b = base.get("pages") or [], after.get("pages") or []
    if len(a) != 1 or len(b) != 1:
        return {"verified": False, "reason": "EXPECTED_ONE_ARTBOARD"}
    total_base = a[0]["drawing_count"]
    total_after = b[0]["drawing_count"]
    candidate = [
        drawing for drawing in b[0]["drawings"]
        if drawing["filled"] and abs(drawing["width"] - 880) < 8
        and abs(drawing["height"] - 700) < 8
    ]
    # More drawing operations do not mathematically guarantee more Illustrator
    # objects; this is evidence of persisted visible vector geometry only.
    confirmed = total_after > total_base and bool(candidate)
    return {
        "verified": confirmed,
        "reason": "ADDITIONAL_PERSISTED_UPPER_FIELD_DRAWING" if confirmed else "GEOMETRY_DIFFERENCE_NOT_CONCLUSIVE",
        "baseline_drawing_count": total_base,
        "target_drawing_count": total_after,
        "upper_field_candidates": candidate[:3],
        "note": "PDF drawing counts are not an Illustrator scenegraph object-count readback."
    }


def inspect(source: Path, target: Path) -> dict:
    if not source.is_file() or not target.is_file():
        raise FileNotFoundError("NATIVE_AI_SOURCE_OR_TARGET_NOT_FOUND")
    before = {"source": sha(source), "target": sha(target)}
    if before != {"source": BASELINE_SHA, "target": TARGET_SHA}:
        raise RuntimeError("ILLUSTRATOR_NATIVE_SHA_CHANGED_REFUSE_STALE_ASSUMPTIONS " + str(before))
    base_geometry = drawing_geometry(source)
    after_geometry = drawing_geometry(target)
    evidence = {
        "schema": "panda-illustrator-pdf-comparison-v1",
        "source_sha256": before["source"],
        "target_sha256": before["target"],
        "source_size": source.stat().st_size,
        "target_size": target.stat().st_size,
        "source_geometry": base_geometry,
        "target_geometry": after_geometry,
        "additional_vector_evidence": comparable_second_vector(base_geometry, after_geometry),
        "native_save_persisted": before["source"] != before["target"]
    }
    end = {"source": sha(source), "target": sha(target)}
    if before != end:
        raise RuntimeError("ILLUSTRATOR_NATIVE_FILE_CHANGED_DURING_READONLY_AUDIT")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.source, args.target)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf8")
    print("PANDA_AI_OFFLINE_NATIVE_AUDIT=" + json.dumps({
        "native_saved": result["native_save_persisted"],
        "two_vector_pdf_evidence": result["additional_vector_evidence"],
        "source_drawing_count": (result["source_geometry"].get("pages") or [{}])[0].get("drawing_count"),
        "target_drawing_count": (result["target_geometry"].get("pages") or [{}])[0].get("drawing_count"),
        "file_unchanged": True
    }, default=str), flush=True)


if __name__ == "__main__":
    main()
