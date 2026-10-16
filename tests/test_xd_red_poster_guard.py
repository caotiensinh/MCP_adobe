"""XD native 880x700 first-write safety gate: positive/negative/regression."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest
from mcp_adobe import xd_red_poster_guard as guard


DOC = guard.NEW_DOCUMENT_ID
OLD = guard.OLD_DOCUMENT_ID


def states():
    health = {"bridge": "connected", "pending_count": 0}
    document = {"id": DOC}
    scene = {
        "complete": True,
        "document_id": DOC,
        "nodes": [{
            "id": guard.NEW_ARTBOARD_ID,
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
        "artboard_id": guard.NEW_ARTBOARD_ID,
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


def adobe_v57_native_live_states():
    """Recorded real XD bridge shape from MRCAO run 38232233337."""
    health, _flat, scene = states()
    document = {
        "rootChildren": 1,
        "insertionParent": {
            "guid": DOC,
            "name": None,
            "type": "RootNode",
            "visible": True,
            "bounds": {"x": 0, "y": 0, "width": 880, "height": 700},
        },
        "insertionParentChildren": [{
            "guid": guard.NEW_ARTBOARD_ID,
            "name": "SPRK_default_preset_name_custom – 1",
            "type": "Artboard",
            "visible": True,
            "bounds": {"x": 0, "y": 0, "width": 880, "height": 700},
        }],
    }
    return health, document, scene


def test_actual_adobe_v57_nested_document_root_matches_saved_native():
    health, document, scene = adobe_v57_native_live_states()
    proof = verify(health, document, scene)
    assert proof["ready_for_first_write"] is True
    assert proof["document_id"] == guard.NEW_DOCUMENT_ID
    assert proof["artboard_id"] == guard.NEW_ARTBOARD_ID


@pytest.mark.parametrize("mutation", [
    "other_root_guid", "conflicting_direct_id", "root_wrong_type",
    "wrong_child_count", "wrong_child_guid", "wrong_child_type",
    "root_width_wrong", "child_height_wrong", "child_bounds_nan",
    "missing_child_bounds",
])
def test_actual_adobe_v57_inconsistent_identity_and_bounds_rejected(mutation):
    health, document, scene = adobe_v57_native_live_states()
    root = document["insertionParent"]
    child = document["insertionParentChildren"][0]
    if mutation == "other_root_guid":
        root["guid"] = "untrusted-other-open-document"
    elif mutation == "conflicting_direct_id":
        document["id"] = "another-document-id"
    elif mutation == "root_wrong_type":
        root["type"] = "Artboard"
    elif mutation == "wrong_child_count":
        document["rootChildren"] = 2
    elif mutation == "wrong_child_guid":
        child["guid"] = "wrong-artboard"
    elif mutation == "wrong_child_type":
        child["type"] = "Rectangle"
    elif mutation == "root_width_wrong":
        root["bounds"]["width"] = 881
    elif mutation == "child_height_wrong":
        child["bounds"]["height"] = 699
    elif mutation == "child_bounds_nan":
        child["bounds"]["x"] = float("nan")
    elif mutation == "missing_child_bounds":
        child["bounds"] = None
    with pytest.raises(guard.XdRedGuardError):
        verify(health, document, scene)


def test_correct_doc_wrong_native_artboard_guid_refused():
    health, document, scene = adobe_v57_native_live_states()
    scene["nodes"][0]["id"] = "fake-but-identical-880x700-artboard"
    with pytest.raises(guard.XdRedGuardError, match="NATIVE_ARTBOARD_ID_MISMATCH"):
        verify(health, document, scene)
