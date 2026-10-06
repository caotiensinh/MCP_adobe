from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping

from .core import AdapterInfo, RiskClass
from .photoshop import OperationUnknownError, UpstreamToolClient
from .verification import capture_file_snapshot, evaluate_file_snapshot, unverified_mutation

UPSTREAM_REPOSITORY = "ie3jp/illustrator-mcp-server"
UPSTREAM_SNAPSHOT = "57c5c101a5192c61535493f39b653e6f92b8eb29"
UPSTREAM_PACKAGE = "illustrator-mcp-server@1.10.3"
READINESS_TTL_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class ToolBinding:
    upstream_tool: str
    risk: RiskClass


# Curated bounded interaction surface. Prefer these object/path/text operations
# for conversational editing instead of monolithic generated scripts.
_BINDINGS: dict[str, ToolBinding] = {
    "creative.health": ToolBinding("list_fonts", RiskClass.READ),
    "creative.document.info": ToolBinding("get_document_info", RiskClass.READ),
    "creative.document.structure": ToolBinding("get_document_structure", RiskClass.READ),
    "creative.selection.get": ToolBinding("get_selection", RiskClass.READ),
    "creative.artboard.list": ToolBinding("get_artboards", RiskClass.READ),
    "creative.layer.list": ToolBinding("get_layers", RiskClass.READ),
    "creative.path.list": ToolBinding("get_path_items", RiskClass.READ),
    "creative.group.list": ToolBinding("get_groups", RiskClass.READ),
    "creative.text.list": ToolBinding("list_text_frames", RiskClass.READ),
    "creative.object.find": ToolBinding("find_objects", RiskClass.READ),
    "creative.document.create": ToolBinding("create_document", RiskClass.WRITE_REVERSIBLE),
    "creative.document.open": ToolBinding("open_document", RiskClass.WRITE_REVERSIBLE),
    "creative.document.save": ToolBinding("save_document", RiskClass.FILE_WRITE),
    "creative.document.export": ToolBinding("export", RiskClass.FILE_WRITE),
    "creative.document.export_pdf": ToolBinding("export_pdf", RiskClass.FILE_WRITE),
    "creative.shape.rectangle": ToolBinding("create_rectangle", RiskClass.WRITE_REVERSIBLE),
    "creative.shape.ellipse": ToolBinding("create_ellipse", RiskClass.WRITE_REVERSIBLE),
    "creative.path.create": ToolBinding("create_path", RiskClass.WRITE_REVERSIBLE),
    "creative.text.create": ToolBinding("create_text_frame", RiskClass.WRITE_REVERSIBLE),
    "creative.object.update": ToolBinding("modify_object", RiskClass.WRITE_REVERSIBLE),
    "creative.object.select": ToolBinding("select_objects", RiskClass.WRITE_REVERSIBLE),
    "creative.object.group": ToolBinding("group_objects", RiskClass.WRITE_REVERSIBLE),
    "creative.object.ungroup": ToolBinding("ungroup_objects", RiskClass.WRITE_REVERSIBLE),
    "creative.object.z_order": ToolBinding("set_z_order", RiskClass.WRITE_REVERSIBLE),
    "creative.object.move_to_layer": ToolBinding("move_to_layer", RiskClass.WRITE_REVERSIBLE),
    "creative.gradient.create": ToolBinding("create_gradient", RiskClass.WRITE_REVERSIBLE),
    "creative.object.delete": ToolBinding("delete_objects", RiskClass.DESTRUCTIVE),
    "creative.undo": ToolBinding("undo", RiskClass.WRITE_REVERSIBLE),
}


class IllustratorAdapter:
    """Thin adapter over the pinned ie3jp Illustrator MCP tool surface."""

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
        return AdapterInfo(
            application="illustrator",
            connected=self._client.connected,
            version=self._version,
            common_capabilities=frozenset(_BINDINGS),
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
        if capability == "creative.health":
            return {"limit": 1}
        args = dict(arguments)
        if capability in {"creative.document.export", "creative.document.export_pdf"}:
            path = args.pop("path", None)
            if path is not None:
                args["output_path"] = path
        return args

    @staticmethod
    def _is_mutating(capability: str) -> bool:
        return _BINDINGS[capability].risk is not RiskClass.READ

    @staticmethod
    def _health_ready(result: Mapping[str, Any]) -> bool:
        if result.get("error") is True:
            return False
        return any(key in result for key in ("totalAvailable", "count", "fonts"))

    def probe_ready(self) -> Mapping[str, Any]:
        now = time.monotonic()
        if self._ready_until > now:
            return {
                "ready": True,
                "application": "illustrator",
                "source": "list_fonts",
                "cached": True,
            }
        try:
            result = self._client.call_tool("list_fonts", {"limit": 1})
        except Exception:
            self._ready_until = 0.0
            return {
                "ready": False,
                "application": "illustrator",
                "source": "list_fonts",
                "cached": False,
                "reason": "illustrator_health_probe_failed",
            }
        ready = self._health_ready(result)
        self._ready_until = now + READINESS_TTL_SECONDS if ready else 0.0
        return {
            "ready": ready,
            "application": "illustrator",
            "source": "list_fonts",
            "cached": False,
            "reason": None if ready else "illustrator_health_probe_not_ready",
        }

    def execute(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            binding = _BINDINGS[capability]
        except KeyError as exc:
            raise LookupError(f"unsupported Illustrator capability: {capability}") from exc

        file_snapshot = (
            capture_file_snapshot(arguments)
            if binding.risk is RiskClass.FILE_WRITE
            else None
        )
        try:
            result = self._client.call_tool(
                binding.upstream_tool,
                self._translate_arguments(capability, arguments),
            )
        except TimeoutError as exc:
            if self._is_mutating(capability):
                self._ready_until = 0.0
                raise OperationUnknownError(capability, binding.upstream_tool) from exc
            raise

        if capability == "creative.health":
            self._ready_until = (
                time.monotonic() + READINESS_TTL_SECONDS if self._health_ready(result) else 0.0
            )

        payload: dict[str, Any] = {
            "ok": True,
            "application": "illustrator",
            "capability": capability,
            "upstream_tool": binding.upstream_tool,
            "result": result,
        }
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
