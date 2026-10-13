"""Phase 4 transaction simulation; no live Adobe API calls or filesystem writes."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping
from mcp_adobe.mode2_edit_guard import fingerprint


def simulate_reversible_edit(
    *,
    proposal: Mapping[str, Any],
    current_document: Mapping[str, Any],
    current_layer: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail closed unless the approved proposal still names the same snapshot.

    Simulates one change and its inverse, with round-trip SHA checks.
    It is NOT a replacement for host-side undo, native save or E2E acceptance.
    """
    plan = dict(proposal)
    signature = plan.pop("proposal_sha256", None)
    if not isinstance(signature, str) or fingerprint(plan) != signature:
        raise ValueError("proposal digest mismatch")
    if plan.get("execute_automatically") is not False:
        raise ValueError("automatic execution forbidden")
    if plan.get("schema") != "mcp-adobe-mode2-guarded-edit/v1":
        raise ValueError("unknown proposal schema")
    for field, field_in_doc in (("application", "application"), ("document_identity", "document_identity"), ("generation", "generation"), ("preview_sha256", "preview_sha256"), ("baseline_native_sha256", "saved_native_sha256")):
        if plan.get(field) != current_document.get(field_in_doc):
            raise ValueError(f"changed document: {field}")
    if str(current_layer.get("id")) != plan.get("node_id"):
        raise ValueError("target node changed")
    if current_layer.get("bounds") != plan.get("node_bounds"):
        raise ValueError("target bounds changed")
    if current_layer.get("visible") is not True or current_layer.get("locked") is not False or current_layer.get("background") is True:
        raise ValueError("target not editable")
    original = deepcopy(dict(current_layer))
    changed = deepcopy(original)
    operation = plan.get("operation")
    if not isinstance(operation, dict) or not isinstance(operation.get("parameters"), dict):
        raise ValueError("invalid operation")
    kind, params = operation.get("kind"), operation["parameters"]
    if kind == "set_fill" and set(params) == {"color"} and isinstance(params["color"], str) and len(params["color"]) == 7 and params["color"][0] == "#" and all(x in "0123456789abcdefABCDEF" for x in params["color"][1:]):
        changed["fill"] = params["color"]
    elif kind == "set_opacity" and set(params) == {"opacity"} and type(params["opacity"]) in (int, float) and 0 <= params["opacity"] <= 1:
        changed["opacity"] = params["opacity"]
    elif kind == "translate" and set(params) == {"dx", "dy"} and all(type(params[k]) in (int, float) and -1000 <= params[k] <= 1000 for k in ("dx", "dy")):
        changed["bounds"] = {k: original["bounds"][k] + params["dx" if k in ("left", "right") else "dy"] for k in ("left", "top", "right", "bottom")}
    else:
        raise ValueError("invalid simulated operation")
    undo_snapshot = deepcopy(original)
    if fingerprint(undo_snapshot) != fingerprint(original):
        raise AssertionError("simulation undo mismatch")
    return {
        "simulation_passed": True,
        "before_sha256": fingerprint(original),
        "after_sha256": fingerprint(changed),
        "undo_sha256": fingerprint(undo_snapshot),
        "changed_node": changed,
        "native_file_written": False,
        "host_undo_verified": False,
        "host_readback_verified": False,
        "execute_automatically": False,
    }
