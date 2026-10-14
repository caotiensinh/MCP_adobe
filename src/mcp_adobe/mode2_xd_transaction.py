"""Mode 2 XD execution coordinator with mandatory isolated-native and undo proof.

The gateway is injected; this module cannot open an Adobe session itself.
No host mutation is possible unless the caller opts in *and* the gateway
implements every required operation. Default execution is dry-run.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mcp_adobe.mode2_edit_guard import fingerprint


def execute_guarded_xd_edit(
    *,
    proposal: Mapping[str, Any],
    gateway: Any,
    isolated_copy: Mapping[str, Any],
    allow_live_mutation: bool = False,
) -> dict[str, Any]:
    if proposal.get("application") != "xd" or proposal.get("execute_automatically") is not False:
        raise ValueError("invalid XD proposal")
    signed = dict(proposal)
    signature = signed.pop("proposal_sha256", None)
    if not isinstance(signature, str) or fingerprint(signed) != signature:
        raise ValueError("tampered XD proposal")
    if not allow_live_mutation:
        return {"status": "dry_run", "mutation_attempted": False, "proposal_sha256": signature}
    if isolated_copy.get("is_copy") is not True or isolated_copy.get("origin_readonly") is not True:
        raise ValueError("isolated test copy and read-only origin required")
    if isolated_copy.get("native_sha256") != proposal.get("baseline_native_sha256"):
        raise ValueError("isolated copy baseline SHA mismatch")
    # Never enter a real host mutation for a proposal with unclear or
    # unsupported semantics, even if a gateway advertises a valid copy.
    operation = proposal.get("operation")
    if (not isinstance(operation, Mapping)
            or operation.get("kind") != "set_fill"
            or not isinstance(operation.get("parameters"), Mapping)
            or not isinstance(operation["parameters"].get("color"), str)
            or len(operation["parameters"]["color"]) != 7
            or not operation["parameters"]["color"].startswith("#")
            or any(c not in "0123456789abcdefABCDEF" for c in operation["parameters"]["color"][1:])):
        raise ValueError("unsupported XD operation before host mutation")
    required = ("read_document", "read_layer", "edit_layer", "undo", "save_native",
                "read_native_sha256", "verify_copy_provenance", "verify_undo_capability")
    if any(not callable(getattr(gateway, method, None)) for method in required):
        raise ValueError("gateway lacks verified reversible edit API")
    # A caller-supplied is_copy flag or native path string alone is insufficient.
    # Require independent host-backed path/provenance and undo capability proofs.
    if gateway.verify_copy_provenance(isolated_copy) is not True:
        raise ValueError("host could not verify isolated native copy provenance")
    if gateway.verify_undo_capability() is not True:
        raise ValueError("host undo capability unverified")
    document = gateway.read_document()
    for field in ("document_identity", "generation", "preview_sha256"):
        if document.get(field) != proposal.get(field):
            raise ValueError(f"stale XD document: {field}")
    if document.get("isolated_copy") is not True or document.get("native_path") != isolated_copy.get("path"):
        raise ValueError("active document is not the isolated copy")
    node = gateway.read_layer(proposal["node_id"])
    if not isinstance(node, Mapping) or str(node.get("id")) != str(proposal["node_id"]):
        raise ValueError("target missing")
    if node.get("bounds") != proposal.get("node_bounds") or node.get("locked") is not False or node.get("visible") is not True:
        raise ValueError("unsafe or moved target")
    before = fingerprint(node)
    edit_called = False
    try:
        edit_called = True
        gateway.edit_layer(proposal["node_id"], proposal["operation"], expected_generation=proposal["generation"])
        after_node = gateway.read_layer(proposal["node_id"])
        if not isinstance(after_node, Mapping) or str(after_node.get("id")) != str(proposal["node_id"]):
            raise RuntimeError("XD host mutation readback target mismatch")
        if fingerprint(after_node) == before:
            raise RuntimeError("no host mutation detected")
        operation = proposal["operation"]
        if operation.get("kind") != "set_fill":
            raise RuntimeError("XD operation is not supported by verified readback")
        intended = operation.get("parameters", {}).get("color")
        if not isinstance(intended, str) or after_node.get("fill", "").upper() != intended.upper():
            raise RuntimeError("XD mutation did not produce requested fill")
        gateway.undo()
        undone = gateway.read_layer(proposal["node_id"])
        if fingerprint(undone) != before:
            raise RuntimeError("XD undo failed to restore target")
        gateway.save_native()
        native_sha = gateway.read_native_sha256()
        if native_sha != proposal["baseline_native_sha256"]:
            raise RuntimeError("native bytes differ from baseline after undo")
        return {"status": "verified_undo", "mutation_attempted": True,
                "node_before_sha256": before, "node_after_sha256": fingerprint(after_node),
                "node_undo_sha256": fingerprint(undone),
                "native_undo_sha256": native_sha}
    except BaseException:
        # Do not replay uncertain mutations, issue unbounded undo or overwrite
        # the original file. Preserve the isolated document for investigation.
        if edit_called:
            raise RuntimeError("XD edit outcome uncertain; isolated copy quarantined; no retry") from None
        raise
