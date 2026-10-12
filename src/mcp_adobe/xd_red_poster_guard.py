"""Fail-closed, read-only XD red-poster target guard.

Pure validation: it sends no MCP commands, never changes a document or queue,
and never infers an identity from the foreground Windows HWND. The caller must
first discover the saved XD document UUID read-only and *pin* it separately,
then run this gate again immediately before any future queued mutation.
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

OLD_DOCUMENT_ID = "98d6635b-3767-4254-b200-ec8442b69ad2"
ORIGINAL_SHA256 = "3a10e1510abc41eccd4485d6f852ea6ced7acc2cf50109e7c1bd123353589ed1"
NEW_NATIVE_SHA256 = "58966788cf369885c2395ce217d6e0443ed57bcd7f40bd550b2f3a24c2b5b831"
ORIGINAL_FILENAME = "MCP_Mode1_Panda_XD_38136531800.xd"
NEW_FILENAME = "MCP_KFP4_Red_XD_38205166138.xd"
WIDTH, HEIGHT = 880, 700


class XdRedGuardError(ValueError):
    """Unverified state: do not queue a new XD write or send Apply."""


def _digest(path: Path) -> str:
    if not path.is_file():
        raise XdRedGuardError("XD_RED_NATIVE_FILE_MISSING: " + path.name)
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_native_files(root: Path) -> dict[str, Any]:
    """Verify both immutable files and return evidence without changing them."""
    root = Path(root)
    original = root / ORIGINAL_FILENAME
    draft = root / NEW_FILENAME
    original_digest = _digest(original)
    draft_digest = _digest(draft)
    if original_digest != ORIGINAL_SHA256:
        raise XdRedGuardError("XD_RED_ORIGINAL_SHA_MISMATCH")
    if draft_digest != NEW_NATIVE_SHA256:
        raise XdRedGuardError("XD_RED_DRAFT_SHA_MISMATCH")
    return {
        "original_sha256": original_digest,
        "draft_sha256": draft_digest,
        "draft_bytes": draft.stat().st_size,
        "native_checkpoint_verified": True,
    }


def _valid_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise XdRedGuardError("XD_RED_DOCUMENT_ID_UNAVAILABLE")
    return value.strip()


def _bounds(node: Mapping[str, Any]) -> None:
    rect = node.get("bounds")
    if not isinstance(rect, Mapping):
        raise XdRedGuardError("XD_RED_ARTBOARD_BOUNDS_MISSING")
    try:
        values = [float(rect[k]) for k in ("left", "top", "right", "bottom")]
    except (ValueError, TypeError, KeyError) as exc:
        raise XdRedGuardError("XD_RED_ARTBOARD_BOUNDS_INVALID") from exc
    if not all(math.isfinite(v) for v in values):
        raise XdRedGuardError("XD_RED_ARTBOARD_BOUNDS_NONFINITE")
    l, t, r, b = values
    if not (math.isclose(l, 0, abs_tol=0.5) and math.isclose(t, 0, abs_tol=0.5)
            and math.isclose(r - l, WIDTH, abs_tol=0.5)
            and math.isclose(b - t, HEIGHT, abs_tol=0.5)):
        raise XdRedGuardError("XD_RED_ARTBOARD_SIZE_MISMATCH")


def validate_live_target(
    health: Mapping[str, Any],
    document: Mapping[str, Any],
    scenegraph: Mapping[str, Any],
    *,
    expected_document_id: str | None,
) -> dict[str, Any]:
    """Fail closed unless a *pinned* new document and empty 880x700 artboard agree.

    expected_document_id=None is discovery mode and always raises: capture the
    read-only UUID first and review/record it before enabling any future write.
    """
    if not all(isinstance(item, Mapping) for item in (health, document, scenegraph)):
        raise XdRedGuardError("XD_RED_MCP_RESPONSE_NOT_MAPPING")
    if health.get("bridge") != "connected" or type(health.get("pending_count")) is not int or health["pending_count"] != 0:
        raise XdRedGuardError("XD_RED_BRIDGE_NOT_CONNECTED_OR_IDLE")
    doc_id = _valid_id(document.get("id") or document.get("document_id"))
    scene_id = _valid_id(scenegraph.get("document_id"))
    if doc_id == OLD_DOCUMENT_ID or scene_id == OLD_DOCUMENT_ID:
        raise XdRedGuardError("XD_RED_OLD_32_OBJECT_DOCUMENT_ACTIVE")
    if doc_id != scene_id:
        raise XdRedGuardError("XD_RED_DOCUMENT_SCENEGRAPH_MISMATCH")
    if not expected_document_id:
        raise XdRedGuardError("XD_RED_NEW_UUID_MUST_BE_PINNED_BEFORE_WRITE: " + doc_id)
    pinned = _valid_id(expected_document_id)
    if pinned == OLD_DOCUMENT_ID or doc_id != pinned:
        raise XdRedGuardError("XD_RED_UNEXPECTED_ACTIVE_DOCUMENT")
    if scenegraph.get("complete") is not True:
        raise XdRedGuardError("XD_RED_INCOMPLETE_SCENEGRAPH")
    nodes = scenegraph.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 1:
        raise XdRedGuardError("XD_RED_ARTBOARD_COUNT_NOT_ONE")
    artboard = nodes[0]
    if not isinstance(artboard, Mapping) or artboard.get("type") != "Artboard":
        raise XdRedGuardError("XD_RED_ROOT_NOT_ARTBOARD")
    if not isinstance(artboard.get("children"), list) or artboard["children"]:
        raise XdRedGuardError("XD_RED_ARTBOARD_NOT_EMPTY")
    artboard_id = _valid_id(artboard.get("id"))
    _bounds(artboard)
    return {
        "ready_for_first_write": True,
        "document_id": doc_id,
        "artboard_id": artboard_id,
        "width": WIDTH,
        "height": HEIGHT,
        "pending_count": 0,
        "scenegraph_complete": True,
    }
