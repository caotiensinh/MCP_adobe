"""Mode 2 phase 4: fail-closed edit authorization, no Adobe writes.

This module prepares an immutable proposal only. No MCP command is issued.
"""
from __future__ import annotations

import hashlib
import json
from math import isfinite
from collections.abc import Mapping
from typing import Any

ALLOWED = {"xd", "illustrator", "photoshop"}
EDIT_OPS = {"set_fill", "set_opacity", "translate"}


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def authorize_edit_plan(
    *,
    selection: Mapping[str, Any],
    confirmed_layer_id: str,
    live_document: Mapping[str, Any],
    live_layer: Mapping[str, Any],
    operation: Mapping[str, Any],
    preview_verified: bool,
    user_confirmed: bool,
) -> dict[str, Any]:
    """Return a non-executable edit plan only after exact snapshot revalidation."""
    if selection.get("execute_automatically") is not False:
        raise ValueError("untrusted executable selection")
    if not preview_verified or not user_confirmed:
        raise ValueError("preview and target need explicit confirmation")
    if selection.get("status") not in ("single_candidate", "ambiguous"):
        raise ValueError("selection has no valid candidate")
    if selection.get("application") not in ALLOWED:
        raise ValueError("unsupported Adobe application")
    if live_document.get("application") != selection["application"]:
        raise ValueError("application mismatch")
    for key in ("document_identity", "generation", "preview_sha256"):
        expected = selection.get(key)
        if expected is None or expected == "" or live_document.get(key) != expected:
            raise ValueError(f"stale document snapshot: {key}")
    baseline = live_document.get("saved_native_sha256")
    if not isinstance(baseline, str) or len(baseline) != 64 or any(c not in "0123456789abcdefABCDEF" for c in baseline):
        raise ValueError("valid native baseline SHA-256 is required")
    candidates = selection.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("missing candidates")
    if not isinstance(confirmed_layer_id, str) or not confirmed_layer_id:
        raise ValueError("missing confirmed layer")
    selected = [c for c in candidates if str(c.get("layer_id")) == confirmed_layer_id]
    if len(selected) != 1:
        raise ValueError("confirmed layer not unique in candidates")
    if str(live_layer.get("id")) != confirmed_layer_id:
        raise ValueError("live layer identity mismatch")
    if live_layer.get("visible") is not True or live_layer.get("locked") is not False or live_layer.get("background") is True:
        raise ValueError("live layer is not editable")
    if fingerprint(live_layer.get("bounds")) != fingerprint(selected[0].get("layer_bounds")):
        raise ValueError("layer bounds changed")
    if not isinstance(operation, Mapping) or operation.get("kind") not in EDIT_OPS:
        raise ValueError("operation is not allowlisted")
    parameters = operation.get("parameters")
    if not isinstance(parameters, Mapping) or not parameters:
        raise ValueError("missing operation parameters")
    op_kind = operation["kind"]
    if op_kind == "set_fill":
        value = parameters.get("color")
        if set(parameters) != {"color"} or not isinstance(value, str) or len(value) != 7 or value[0] != "#" or any(c not in "0123456789abcdefABCDEF" for c in value[1:]):
            raise ValueError("invalid fill color")
    elif op_kind == "set_opacity":
        value = parameters.get("opacity")
        if set(parameters) != {"opacity"} or type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
            raise ValueError("invalid opacity")
    else:
        if set(parameters) != {"dx", "dy"} or any(type(parameters[k]) not in (int, float) or not isfinite(parameters[k]) or not -1000 <= parameters[k] <= 1000 for k in ("dx", "dy")):
            raise ValueError("invalid translation")
    proposal = {
        "schema": "mcp-adobe-mode2-guarded-edit/v1",
        "application": selection["application"],
        "document_identity": selection["document_identity"],
        "generation": selection["generation"],
        "preview_sha256": selection["preview_sha256"],
        "baseline_native_sha256": live_document["saved_native_sha256"],
        "node_id": confirmed_layer_id,
        "node_bounds": dict(live_layer["bounds"]),
        "operation": {"kind": op_kind, "parameters": dict(parameters)},
        "requires_fresh_host_readback": True,
        "requires_native_save_and_undo_verification": True,
        "execute_automatically": False,
    }
    proposal["proposal_sha256"] = fingerprint(proposal)
    return proposal
