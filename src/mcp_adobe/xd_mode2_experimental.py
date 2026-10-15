"""Opt-in experimental Adobe XD Mode 2 bridge surface.

The known-good XdAdapter and production Adobe XD plugin are deliberately
untouched. This adapter exposes the experimental plugin's guarded inspect and
approval-queued fill endpoints only when constructed explicitly. It does not
attest native file ownership, press Apply, perform Undo, or enable the full
production transaction coordinator; those need independent host evidence.
"""
from __future__ import annotations

from dataclasses import replace
from collections.abc import Mapping
from math import isfinite
import re
from typing import Any

from .core import RiskClass
from .photoshop import OperationUnknownError
from .verification import pending_user_approval, unverified_mutation
from .xd import ToolBinding, XdAdapter

EXPERIMENTAL_BRIDGE_BUILD = "xd-mode2-guarded-experimental-v1"

_EXPERIMENTAL: dict[str, ToolBinding] = {
    "xd.mode2.node.inspect": ToolBinding("xd.mode2.node.inspect", RiskClass.READ),
    "xd.queue.mode2_fill": ToolBinding("xd.queue.mode2_fill", RiskClass.WRITE_REVERSIBLE),
}


def validate_mode2_arguments(capability: str, args: Mapping[str, Any]) -> None:
    """Refuse stale/oversized/ambiguous requests before contacting Adobe."""
    if capability not in _EXPERIMENTAL:
        raise LookupError(f"unsupported Mode 2 experimental capability: {capability}")
    required = {"document_id", "node_id", "bounds"}
    allowed = required if capability == "xd.mode2.node.inspect" else (
        required | {"fill", "isolated_test_copy", "user_confirmed"}
    )
    if not isinstance(args, Mapping) or set(args) != allowed:
        raise ValueError("Mode 2 requires exact experimental argument keys")
    for name in ("document_id", "node_id"):
        if not isinstance(args[name], str) or not (1 <= len(args[name]) <= 128):
            raise ValueError("Mode 2 requires nonempty exact document/node identity")
    bounds = args["bounds"]
    if not isinstance(bounds, Mapping) or set(bounds) != {"left", "top", "right", "bottom"}:
        raise ValueError("Mode 2 requires four global node bounds")
    if any(type(v) not in (int, float) or not isfinite(v) or abs(v) > 1_000_000
           for v in bounds.values()):
        raise ValueError("Mode 2 coordinates must be finite bounded numbers")
    if bounds["right"] <= bounds["left"] or bounds["bottom"] <= bounds["top"]:
        raise ValueError("Mode 2 selected node must have positive area")
    if capability == "xd.queue.mode2_fill":
        if (args["isolated_test_copy"] is not True
                or args["user_confirmed"] is not True
                or not isinstance(args["fill"], str)
                or re.fullmatch(r"#[0-9a-fA-F]{6}", args["fill"]) is None):
            raise ValueError("Mode 2 fill requires experimental copy approval and hex color")


class ExperimentalXdMode2Adapter(XdAdapter):
    """A separate, explicitly instantiated transport for the experimental UXP."""

    def info(self):
        base = super().info()
        return replace(
            base,
            native_capabilities=base.native_capabilities | frozenset(_EXPERIMENTAL),
            # Never claim an implemented Undo gateway based on UIA experiments.
            undo_supported=False,
        )

    def execute(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        binding = _EXPERIMENTAL.get(capability)
        if binding is None:
            return super().execute(capability, arguments)
        validate_mode2_arguments(capability, arguments)
        if binding.risk is not RiskClass.READ and not self._writes_enabled:
            raise PermissionError("experimental Mode 2 writes are disabled")
        # The production XD plugin implements only the known-good API; an
        # opt-in Python object alone is NOT proof the experimental UXP is loaded.
        # This read-only host attestation must pass before *any* Mode 2 request.
        health = self._client.call_tool("xd.health", {})
        if (not isinstance(health, Mapping)
                or health.get("bridge") != "connected"
                or health.get("bridge_build") != EXPERIMENTAL_BRIDGE_BUILD):
            raise RuntimeError("experimental XD UXP build is not connected")
        if (capability == "xd.queue.mode2_fill"
                and (type(health.get("pending_count")) is not int
                     or health["pending_count"] != 0)):
            raise RuntimeError("Mode 2 requires empty pending XD queue")
        try:
            result = self._client.call_tool(binding.bridge_method, dict(arguments))
        except TimeoutError as exc:
            if binding.risk is RiskClass.READ:
                raise
            # A queued write may have reached Adobe. NEVER retry on a timeout.
            raise OperationUnknownError(capability, binding.bridge_method) from exc
        payload: dict[str, Any] = {
            "ok": True, "application": "xd", "capability": capability,
            "bridge_method": binding.bridge_method, "result": result,
        }
        if binding.risk is RiskClass.READ:
            payload["outcome"] = "read"
            payload["verification"] = {"status": "not_applicable"}
        elif isinstance(result, Mapping) and (
            result.get("approval_required") is True or result.get("status") == "queued"
        ):
            payload["outcome"], payload["verification"] = pending_user_approval(result.get("operation_id"))
        else:
            payload["outcome"], payload["verification"] = unverified_mutation(
                "mode2-experimental-response-not-confirmed-applied"
            )
        return payload
