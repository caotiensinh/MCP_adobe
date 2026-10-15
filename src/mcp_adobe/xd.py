from __future__ import annotations

import time
from math import isfinite
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .core import AdapterInfo, RiskClass
from .photoshop import OperationUnknownError, UpstreamToolClient
from .verification import pending_user_approval, unverified_mutation

OFFICIAL_API_REPOSITORY = "AdobeXD/plugin-docs"
OFFICIAL_API_SNAPSHOT = "c1abde873604a1606a5fdd5a578fba4502a7bdfc"
READINESS_TTL_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class ToolBinding:
    bridge_method: str
    risk: RiskClass


_BINDINGS: dict[str, ToolBinding] = {
    "creative.health": ToolBinding("xd.health", RiskClass.READ),
    "creative.context.get": ToolBinding("xd.document.info", RiskClass.READ),
    "creative.document.info": ToolBinding("xd.document.info", RiskClass.READ),
    "creative.selection.get": ToolBinding("xd.selection.get", RiskClass.READ),
    "creative.scenegraph.list": ToolBinding("xd.scenegraph.snapshot", RiskClass.READ),
    "creative.canvas.frame": ToolBinding("xd.canvas.frame", RiskClass.READ),
    "creative.shape.rectangle": ToolBinding("xd.queue.rectangle_create", RiskClass.WRITE_REVERSIBLE),
    "creative.path.create": ToolBinding("xd.queue.path_create", RiskClass.WRITE_REVERSIBLE),
    "creative.shape.ellipse": ToolBinding("xd.queue.ellipse_create", RiskClass.WRITE_REVERSIBLE),
    "creative.text.create": ToolBinding("xd.queue.text_create", RiskClass.WRITE_REVERSIBLE),
    "xd.queue.status": ToolBinding("xd.queue.status", RiskClass.READ),
    "xd.export.png": ToolBinding("xd.export.png", RiskClass.FILE_WRITE),
    "xd.queue.clear": ToolBinding("xd.queue.clear", RiskClass.WRITE_REVERSIBLE),
    "xd.queue.rectangle_create": ToolBinding("xd.queue.rectangle_create", RiskClass.WRITE_REVERSIBLE),
    "xd.queue.path_create": ToolBinding("xd.queue.path_create", RiskClass.WRITE_REVERSIBLE),
    "xd.queue.ellipse_create": ToolBinding("xd.queue.ellipse_create", RiskClass.WRITE_REVERSIBLE),
    "xd.queue.ellipse_geometry_repair": ToolBinding("xd.queue.ellipse_geometry_repair", RiskClass.WRITE_REVERSIBLE),
    "xd.queue.rectangle_position_repair": ToolBinding("xd.queue.rectangle_position_repair", RiskClass.WRITE_REVERSIBLE),
    "xd.queue.text_create": ToolBinding("xd.queue.text_create", RiskClass.WRITE_REVERSIBLE),
    "xd.queue.selection_resize": ToolBinding("xd.queue.selection_resize", RiskClass.WRITE_REVERSIBLE),
    "xd.queue.selection_fill": ToolBinding("xd.queue.selection_fill", RiskClass.WRITE_REVERSIBLE),
}

# These bridge methods exist only in experimental/mode2-xd-uxp.
# The installed production plugin does not implement them.
_MODE2_EXPERIMENTAL_BINDINGS: dict[str, ToolBinding] = {
    "xd.mode2.node.inspect": ToolBinding("xd.mode2.node.inspect", RiskClass.READ),
    "xd.queue.mode2_fill": ToolBinding("xd.queue.mode2_fill", RiskClass.WRITE_REVERSIBLE),
}


def _validate_mode2_arguments(capability: str, args: Mapping[str, Any]) -> None:
    required = {"document_id", "node_id", "bounds"}
    allowed = required if capability == "xd.mode2.node.inspect" else (
        required | {"fill", "isolated_test_copy", "user_confirmed"}
    )
    if set(args) != allowed:
        raise ValueError("Mode 2 requires exact, bounded experimental arguments")
    for name in ("document_id", "node_id"):
        if not isinstance(args[name], str) or not (1 <= len(args[name]) <= 128):
            raise ValueError("Mode 2 requires nonempty exact document/node identity")
    bounds = args["bounds"]
    if not isinstance(bounds, Mapping) or set(bounds) != {"left", "top", "right", "bottom"}:
        raise ValueError("Mode 2 bounds must have four global coordinates")
    if any(type(value) not in (float, int) or not isfinite(value) or
           abs(value) > 1_000_000 for value in bounds.values()):
        raise ValueError("Mode 2 bounds must be bounded finite numbers")
    if bounds["right"] <= bounds["left"] or bounds["bottom"] <= bounds["top"]:
        raise ValueError("Mode 2 bounds must have positive area")
    if capability == "xd.queue.mode2_fill":
        if (args["isolated_test_copy"] is not True or args["user_confirmed"] is not True
                or not isinstance(args["fill"], str)
                or re.fullmatch(r"#[0-9a-fA-F]{6}", args["fill"]) is None):
            raise ValueError("Mode 2 fill requires explicit test-copy approval and hex color")


class XdAdapter:
    def __init__(self, client: UpstreamToolClient, *, version: str | None = None, writes_enabled: bool = True, experimental_mode2: bool = False) -> None:
        self._client = client
        self._version = version
        self._writes_enabled = writes_enabled
        self._experimental_mode2 = experimental_mode2
        self._ready_until = 0.0

    def info(self) -> AdapterInfo:
        common = frozenset(name for name in _BINDINGS if name.startswith("creative."))
        native = frozenset(name for name in _BINDINGS if name.startswith("xd."))
        if self._experimental_mode2:
            native |= frozenset(_MODE2_EXPERIMENTAL_BINDINGS)
        return AdapterInfo(
            application="xd",
            connected=self._client.connected,
            version=self._version,
            common_capabilities=common,
            native_capabilities=native,
            capability_risks={name: binding.risk for name, binding in _BINDINGS.items()},
            writes_enabled=self._writes_enabled,
            undo_supported=False,
            transport="uxp-websocket-one-click-approval",
            upstream_repository=OFFICIAL_API_REPOSITORY,
            upstream_snapshot=OFFICIAL_API_SNAPSHOT,
            readiness_probe="creative.health",
        )

    @staticmethod
    def _is_mutating(capability: str) -> bool:
        return (_BINDINGS.get(capability) or _MODE2_EXPERIMENTAL_BINDINGS[capability]).risk is not RiskClass.READ

    @staticmethod
    def _health_ready(result: Mapping[str, Any]) -> bool:
        status = result.get("status")
        if isinstance(status, str) and status.lower() in {"ok", "ready", "connected"}:
            return True
        if result.get("bridge") == "connected":
            return True
        return result.get("application") == "xd" and result.get("error") is not True

    def probe_ready(self) -> Mapping[str, Any]:
        now = time.monotonic()
        if self._ready_until > now:
            return {"ready": True, "application": "xd", "source": "xd.health", "cached": True}
        try:
            result = self._client.call_tool("xd.health", {})
        except Exception:
            self._ready_until = 0.0
            return {"ready": False, "application": "xd", "source": "xd.health", "cached": False, "reason": "xd_health_probe_failed"}
        ready = self._health_ready(result)
        self._ready_until = now + READINESS_TTL_SECONDS if ready else 0.0
        return {"ready": ready, "application": "xd", "source": "xd.health", "cached": False, "reason": None if ready else "xd_health_probe_not_ready"}

    def execute(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            if capability in _MODE2_EXPERIMENTAL_BINDINGS:
                if not self._experimental_mode2:
                    raise LookupError("experimental XD Mode 2 is disabled")
                _validate_mode2_arguments(capability, arguments)
                if capability == "xd.queue.mode2_fill" and not self._writes_enabled:
                    raise PermissionError("experimental XD Mode 2 writes are disabled")
                binding = _MODE2_EXPERIMENTAL_BINDINGS[capability]
            else:
                binding = _BINDINGS[capability]
        except KeyError as exc:
            raise LookupError(f"unsupported Adobe XD capability: {capability}") from exc

        try:
            if capability == "creative.context.get":
                document = self._client.call_tool("xd.document.info", {})
                selection = self._client.call_tool("xd.selection.get", {})
                result: Mapping[str, Any] = {"document": document, "selection": selection}
                bridge_method = "xd.document.info+xd.selection.get"
            else:
                result = self._client.call_tool(binding.bridge_method, dict(arguments))
                bridge_method = binding.bridge_method
        except TimeoutError as exc:
            if self._is_mutating(capability):
                self._ready_until = 0.0
                raise OperationUnknownError(capability, binding.bridge_method) from exc
            raise

        if capability == "creative.health":
            self._ready_until = time.monotonic() + READINESS_TTL_SECONDS if self._health_ready(result) else 0.0

        payload: dict[str, Any] = {
            "ok": True,
            "application": "xd",
            "capability": capability,
            "bridge_method": bridge_method,
            "result": result,
        }
        if capability == "creative.context.get":
            payload["context_source"] = "live-document+selection"
        if binding.risk is RiskClass.READ:
            payload["outcome"] = "read"
            payload["verification"] = {"status": "not_applicable"}
            return payload

        if isinstance(result, Mapping) and (
            result.get("approval_required") is True or result.get("status") == "queued"
        ):
            outcome, verification = pending_user_approval(result.get("operation_id"))
        else:
            outcome, verification = unverified_mutation("xd-mutation-response-not-confirmed-applied")
        payload["outcome"] = outcome
        payload["verification"] = verification
        return payload
