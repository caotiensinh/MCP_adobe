"""XD native 880x700 first-write safety gate: positive/negative/regression."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest
from mcp_adobe import xd_red_poster_guard as guard


DOC = "red-880x700-pinned-uuid"
OLD = guard.OLD_DOCUMENT_ID


def states():
    health = {"bridge": "connected", "pending_count": 0}
    document = {"id": DOC}
    scene = {
        "complete": True,
        "document_id": DOC,
        "nodes": [{
            "id": "red-artboard-id",
            "type": "Artboard",
            "bounds": {"left": 0, "top": 0, "right": 880, "bottom": 700},
            "children": [],
        }],
    }
    return health, document, scene


def verify(health=None, document=None, scene=None, pinned=DOC):
    h, d, g = states()
    return guard.validate_live_target(
        h if health is None else health,
        d if document is None else document,
        g if scene is None else scene,
        expected_document_id=pinned,
    )


def test_correct_pinned_new_empty_artboard_passes():
    result = verify()
    assert result == {
        "ready_for_first_write": True,
        "document_id": DOC,
        "artboard_id": "red-artboard-id",
        "width": 880,
        "height": 700,
        "pending_count": 0,
        "scenegraph_complete": True,
    }


@pytest.mark.parametrize("health", [
    {"bridge": "disconnected", "pending_count": 0},
    {"bridge": "connected", "pending_count": 1},
    {"bridge": "connected", "pending_count": None},
    {"bridge": "connected", "pending_count": False},
    {"bridge": "connected"},
])
def test_bridge_unhealthy_pending_unknown_or_busy_rejected(health):
    with pytest.raises(guard.XdRedGuardError, match="BRIDGE"):
        verify(health=health)


def test_unpinned_uuid_never_authorizes_first_write():
    with pytest.raises(guard.XdRedGuardError, match="MUST_BE_PINNED"):
        verify(pinned=None)


def test_old_bamboo_garden_document_never_authorizes_red_poster_write():
    h, d, g = states()
    d["id"] = OLD
    g["document_id"] = OLD
    with pytest.raises(guard.XdRedGuardError, match="OLD_32"):
        verify(h, d, g, pinned=OLD)


def test_new_document_mismatch_rejected():
    h, d, g = states()
    d["id"] = "another-new-document"
    with pytest.raises(guard.XdRedGuardError, match="SCENEGRAPH_MISMATCH"):
        verify(h, d, g)


def test_unexpected_document_with_identical_canvas_still_rejected():
    h, d, g = states()
    d["id"] = g["document_id"] = "another-blank-880x700-document"
    with pytest.raises(guard.XdRedGuardError, match="UNEXPECTED_ACTIVE_DOCUMENT"):
        verify(h, d, g)


def test_incomplete_scenegraph_rejected():
    h, d, g = states()
    g["complete"] = False
    with pytest.raises(guard.XdRedGuardError, match="INCOMPLETE"):
        verify(h, d, g)


def test_existing_artwork_or_duplicate_artboard_rejected():
    h, d, g = states()
    g["nodes"][0]["children"].append({"id": "foreign-item"})
    with pytest.raises(guard.XdRedGuardError, match="NOT_EMPTY"):
        verify(h, d, g)
    g["nodes"][0]["children"].clear()
    g["nodes"].append(copy.deepcopy(g["nodes"][0]))
    with pytest.raises(guard.XdRedGuardError, match="COUNT_NOT_ONE"):
        verify(h, d, g)


@pytest.mark.parametrize("bounds", [
    {"left": 0, "top": 0, "right": 881, "bottom": 700},
    {"left": 0, "top": 0, "right": 880, "bottom": 699},
    {"left": 0, "top": 0, "right": float("nan"), "bottom": 700},
    {"left": 0, "top": 0, "right": 880},
    None,
])
def test_invalid_canvas_geometry_rejected(bounds):
    h, d, g = states()
    g["nodes"][0]["bounds"] = bounds
    with pytest.raises(guard.XdRedGuardError, match="BOUNDS|SIZE"):
        verify(h, d, g)


def test_native_sha_guards_both_source_and_red_draft(tmp_path, monkeypatch):
    src = tmp_path / guard.ORIGINAL_FILENAME
    dst = tmp_path / guard.NEW_FILENAME
    src.write_bytes(b"protected-old-source")
    dst.write_bytes(b"protected-new-native-draft")
    monkeypatch.setattr(guard, "ORIGINAL_SHA256", hashlib.sha256(src.read_bytes()).hexdigest())
    monkeypatch.setattr(guard, "NEW_NATIVE_SHA256", hashlib.sha256(dst.read_bytes()).hexdigest())
    evidence = guard.verify_native_files(tmp_path)
    assert evidence["native_checkpoint_verified"] is True
    assert evidence["draft_bytes"] == len(b"protected-new-native-draft")
    dst.write_bytes(b"unexpected-concurrent-write")
    with pytest.raises(guard.XdRedGuardError, match="DRAFT_SHA_MISMATCH"):
        guard.verify_native_files(tmp_path)
    dst.unlink()
    with pytest.raises(guard.XdRedGuardError, match="FILE_MISSING"):
        guard.verify_native_files(tmp_path)
