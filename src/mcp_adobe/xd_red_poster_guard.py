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
# Pinned from the saved native uxdesign#id and read back via real MCP scenegraph.
NEW_DOCUMENT_ID = "304d4d00-6fba-47c0-b67a-d0e8ecf30254"
NEW_ARTBOARD_ID = "b195fab0-c97f-46be-8139-5d30a6149e37"
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


def _live_document_id(document: Mapping[str, Any]) -> str:
    """Read Adobe XD v57's actual nested document info, not a fabricated top-level id."""
    direct = document.get("id") or document.get("document_id")
    root = document.get("insertionParent")
    if root is not None:
        if not isinstance(root, Mapping) or root.get("type") != "RootNode":
            raise XdRedGuardError("XD_RED_INSERTION_ROOT_INVALID")
        derived = _valid_id(root.get("guid"))
        if direct and direct != derived:
            raise XdRedGuardError("XD_RED_CONFLICTING_DOCUMENT_IDENTITIES")
        return derived
    return _valid_id(direct)


def _verify_native_document_info(document: Mapping[str, Any], artboard_id: str) -> None:
    """Require actual insertionParent root and artboard geometry to match scenegraph."""
    root = document.get("insertionParent")
    if root is None:
        return  # Legacy adapter reports direct id; scenegraph remains authoritative.
    if not isinstance(root, Mapping) or root.get("type") != "RootNode":
        raise XdRedGuardError("XD_RED_INSERTION_ROOT_INVALID")
    if document.get("rootChildren") != 1:
        raise XdRedGuardError("XD_RED_DOCUMENT_ROOT_CHILD_COUNT_MISMATCH")
    children = document.get("insertionParentChildren")
    if not isinstance(children, list) or len(children) != 1:
        raise XdRedGuardError("XD_RED_DOCUMENT_ARTBOARD_LIST_INVALID")
    child = children[0]
    if not isinstance(child, Mapping) or child.get("type") != "Artboard":
        raise XdRedGuardError("XD_RED_DOCUMENT_CHILD_NOT_ARTBOARD")
    if _valid_id(child.get("guid")) != artboard_id:
        raise XdRedGuardError("XD_RED_DOCUMENT_ARTBOARD_GUID_MISMATCH")
    for node in (root, child):
        bounds = node.get("bounds")
        if not isinstance(bounds, Mapping):
            raise XdRedGuardError("XD_RED_DOCUMENT_BOUNDS_MISSING")
        try:
            x, y, w, h = (float(bounds[k]) for k in ("x", "y", "width", "height"))
        except (KeyError, TypeError, ValueError) as exc:
            raise XdRedGuardError("XD_RED_DOCUMENT_BOUNDS_INVALID") from exc
        if not all(math.isfinite(v) for v in (x, y, w, h)) or not (
            math.isclose(x, 0, abs_tol=0.5) and math.isclose(y, 0, abs_tol=0.5)
            and math.isclose(w, WIDTH, abs_tol=0.5)
            and math.isclose(h, HEIGHT, abs_tol=0.5)
        ):
            raise XdRedGuardError("XD_RED_DOCUMENT_BOUNDS_SIZE_MISMATCH")


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
    doc_id = _live_document_id(document)
    scene_id = _valid_id(scenegraph.get("document_id"))
    if doc_id == OLD_DOCUMENT_ID or scene_id == OLD_DOCUMENT_ID:
        raise XdRedGuardError("XD_RED_OLD_32_OBJECT_DOCUMENT_ACTIVE")
    if doc_id != scene_id:
        raise XdRedGuardError("XD_RED_DOCUMENT_SCENEGRAPH_MISMATCH")
    if not expected_document_id:
        raise XdRedGuardError("XD_RED_NEW_UUID_MUST_BE_PINNED_BEFORE_WRITE: " + doc_id)
    pinned = _valid_id(expected_document_id)
    if pinned != NEW_DOCUMENT_ID or doc_id != NEW_DOCUMENT_ID:
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
    if artboard_id != NEW_ARTBOARD_ID:
        raise XdRedGuardError("XD_RED_NATIVE_ARTBOARD_ID_MISMATCH")
    _bounds(artboard)
    _verify_native_document_info(document, artboard_id)
    return {
        "ready_for_first_write": True,
        "document_id": doc_id,
        "artboard_id": artboard_id,
        "width": WIDTH,
        "height": HEIGHT,
        "pending_count": 0,
        "scenegraph_complete": True,
    }
