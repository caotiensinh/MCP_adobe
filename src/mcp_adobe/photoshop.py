from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .core import AdapterInfo, RiskClass
from .verification import capture_file_snapshot, evaluate_file_snapshot, unverified_mutation


UPSTREAM_REPOSITORY = "alisaitteke/photoshop-mcp"
UPSTREAM_SNAPSHOT = "ecd502c666f0e5b3889d3ef7bc42e5b3eb1119c2"
READINESS_TTL_SECONDS = 30.0


class UpstreamToolClient(Protocol):
    @property
    def connected(self) -> bool:
        ...

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class OperationUnknownError(RuntimeError):
    def __init__(self, capability: str, upstream_tool: str) -> None:
        super().__init__(
            f"operation outcome is unknown after timeout: {capability} via {upstream_tool}; "
            "inspect Photoshop state before retrying"
        )
        self.capability = capability
        self.upstream_tool = upstream_tool


@dataclass(frozen=True, slots=True)
class ToolBinding:
    upstream_tool: str
    risk: RiskClass


_BINDINGS: dict[str, ToolBinding] = {
    "creative.health": ToolBinding("photoshop_ping", RiskClass.READ),
    "creative.capabilities": ToolBinding("photoshop_get_capabilities", RiskClass.READ),
    "creative.context.get": ToolBinding("photoshop_get_state", RiskClass.READ),
    "creative.document.info": ToolBinding("photoshop_get_state", RiskClass.READ),
    "creative.document.preview": ToolBinding("photoshop_get_preview", RiskClass.READ),
    "creative.selection.get": ToolBinding("photoshop_get_state", RiskClass.READ),
    "creative.layer.list": ToolBinding("photoshop_get_layers", RiskClass.READ),
    "creative.document.create": ToolBinding("photoshop_create_document", RiskClass.WRITE_REVERSIBLE),
    "creative.document.open": ToolBinding("photoshop_open_image", RiskClass.WRITE_REVERSIBLE),
    "creative.document.save": ToolBinding("photoshop_save_document", RiskClass.FILE_WRITE),
    "creative.document.export": ToolBinding("photoshop_export_as", RiskClass.FILE_WRITE),
    "creative.layer.select": ToolBinding("photoshop_select_layer_by_name", RiskClass.WRITE_REVERSIBLE),
    "creative.layer.create": ToolBinding("photoshop_create_layer", RiskClass.WRITE_REVERSIBLE),
    "creative.layer.rename": ToolBinding("photoshop_rename_layer", RiskClass.WRITE_REVERSIBLE),
    "creative.layer.delete": ToolBinding("photoshop_delete_layer", RiskClass.DESTRUCTIVE),
    "creative.text.create": ToolBinding("photoshop_create_text_layer", RiskClass.WRITE_REVERSIBLE),
    "creative.text.update": ToolBinding("photoshop_update_text_content", RiskClass.WRITE_REVERSIBLE),
    "creative.object.move": ToolBinding("photoshop_move_layer", RiskClass.WRITE_REVERSIBLE),
    "creative.object.scale": ToolBinding("photoshop_scale_layer", RiskClass.WRITE_REVERSIBLE),
    "creative.object.rotate": ToolBinding("photoshop_rotate_layer", RiskClass.WRITE_REVERSIBLE),
    "creative.style.fill": ToolBinding("photoshop_fill_layer", RiskClass.DESTRUCTIVE),
    "creative.style.opacity": ToolBinding("photoshop_set_layer_opacity", RiskClass.WRITE_REVERSIBLE),
    "creative.style.blend_mode": ToolBinding("photoshop_set_layer_blend_mode", RiskClass.WRITE_REVERSIBLE),
    "creative.selection.rectangle": ToolBinding("photoshop_select_rectangle", RiskClass.WRITE_REVERSIBLE),
    "creative.selection.ellipse": ToolBinding("photoshop_select_ellipse", RiskClass.WRITE_REVERSIBLE),
    "creative.selection.clear": ToolBinding("photoshop_deselect", RiskClass.WRITE_REVERSIBLE),
    "creative.mask.create": ToolBinding("photoshop_create_layer_mask", RiskClass.WRITE_REVERSIBLE),
    "creative.mask.delete": ToolBinding("photoshop_delete_layer_mask", RiskClass.DESTRUCTIVE),
    "creative.undo": ToolBinding("photoshop_undo", RiskClass.WRITE_REVERSIBLE),
    "creative.redo": ToolBinding("photoshop_redo", RiskClass.WRITE_REVERSIBLE),
    "photoshop.execute_script": ToolBinding("photoshop_execute_script", RiskClass.NATIVE_SCRIPT),
}


class PhotoshopAdapter:
    def __init__(
        self,
        client: UpstreamToolClient,
        *,
        version: str | None = None,
        writes_enabled: bool = True,
    ) -> None:
        self._client = client
        self._version = version
        self._writes_enabled = writes_enabled
        self._ready_until = 0.0

    def info(self) -> AdapterInfo:
        common = frozenset(name for name in _BINDINGS if name.startswith("creative."))
        native = frozenset(name for name in _BINDINGS if name.startswith("photoshop."))
        return AdapterInfo(
            application="photoshop",
            connected=self._client.connected,
            version=self._version,
            common_capabilities=common,
            native_capabilities=native,
            capability_risks={name: binding.risk for name, binding in _BINDINGS.items()},
            writes_enabled=self._writes_enabled,
            undo_supported=True,
            transport="mcp",
            upstream_repository=UPSTREAM_REPOSITORY,
            upstream_snapshot=UPSTREAM_SNAPSHOT,
            readiness_probe="creative.health",
        )

    @staticmethod
    def _translate_arguments(capability: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        args = dict(arguments)
        args.pop("overwrite", None)
        if capability == "creative.document.open":
            path = args.pop("path", None)
            if path is not None:
                args["filePath"] = path
        return args

    @staticmethod
    def _is_mutating(capability: str) -> bool:
        return _BINDINGS[capability].risk is not RiskClass.READ

    @staticmethod
    def _ping_ready(result: Mapping[str, Any]) -> bool:
        if result.get("connected") is True:
            return True
        for key in ("text", "value", "message"):
            value = result.get(key)
            if isinstance(value, str) and "successfully connected to photoshop" in value.lower():
                return True
        return False

    def probe_ready(self) -> Mapping[str, Any]:
        now = time.monotonic()
        if self._ready_until > now:
            return {"ready": True, "application": "photoshop", "source": "photoshop_ping", "cached": True}
        try:
            result = self._client.call_tool("photoshop_ping", {})
        except Exception:
            self._ready_until = 0.0
            return {"ready": False, "application": "photoshop", "source": "photoshop_ping", "cached": False, "reason": "photoshop_ping_failed"}
        ready = self._ping_ready(result)
        self._ready_until = now + READINESS_TTL_SECONDS if ready else 0.0
        return {"ready": ready, "application": "photoshop", "source": "photoshop_ping", "cached": False, "reason": None if ready else "photoshop_ping_not_connected"}

    def execute(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            binding = _BINDINGS[capability]
        except KeyError as exc:
            raise LookupError(f"unsupported Photoshop capability: {capability}") from exc

        file_snapshot = capture_file_snapshot(arguments) if binding.risk is RiskClass.FILE_WRITE else None
        upstream_args = self._translate_arguments(capability, arguments)
        try:
            result = self._client.call_tool(binding.upstream_tool, upstream_args)
        except TimeoutError as exc:
            if self._is_mutating(capability):
                self._ready_until = 0.0
                raise OperationUnknownError(capability, binding.upstream_tool) from exc
            raise

        if capability == "creative.health":
            self._ready_until = time.monotonic() + READINESS_TTL_SECONDS if self._ping_ready(result) else 0.0

        payload: dict[str, Any] = {
            "ok": True,
            "application": "photoshop",
            "capability": capability,
            "upstream_tool": binding.upstream_tool,
            "result": result,
        }
        if capability == "creative.context.get":
            payload["context_source"] = "live-photoshop-state"
        if binding.risk is RiskClass.READ:
            payload["outcome"] = "read"
            payload["verification"] = {"status": "not_applicable"}
        elif file_snapshot is not None:
            outcome, verification = evaluate_file_snapshot(file_snapshot)
            payload["outcome"] = outcome
            payload["verification"] = verification
        else:
            outcome, verification = unverified_mutation()
            payload["outcome"] = outcome
            payload["verification"] = verification
        return payload
