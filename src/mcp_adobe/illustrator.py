from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping

from .core import AdapterInfo, RiskClass
from .photoshop import OperationUnknownError, UpstreamToolClient
from .verification import capture_file_snapshot, evaluate_file_snapshot, unverified_mutation

UPSTREAM_REPOSITORY = "jinkeda/Illustrator_MCP"
UPSTREAM_SNAPSHOT = "5d7a3edc8ebc89a0fc56b059e1311d3b2bfca815"
UPSTREAM_PACKAGE = "illustrator-mcp==3.0.0 + CEP panel 1.0.2"
READINESS_TTL_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class ToolBinding:
    upstream_tool: str
    risk: RiskClass


_BINDINGS: dict[str, ToolBinding] = {
    "creative.health": ToolBinding("list_fonts", RiskClass.READ),
    "creative.context.get": ToolBinding("get_document_info", RiskClass.READ),
    "creative.document.info": ToolBinding("get_document_info", RiskClass.READ),
    "creative.document.structure": ToolBinding("get_document_structure", RiskClass.READ),
    "creative.selection.get": ToolBinding("get_selection", RiskClass.READ),
    # These two capabilities intentionally re-read Illustrator selection immediately
    # before the mutation. They never trust a selection UUID cached by the LLM/client.
    "creative.selection.update": ToolBinding("modify_object", RiskClass.WRITE_REVERSIBLE),
    "creative.selection.move": ToolBinding("modify_object", RiskClass.WRITE_REVERSIBLE),
    "creative.artboard.list": ToolBinding("get_artboards", RiskClass.READ),
    "creative.layer.list": ToolBinding("get_layers", RiskClass.READ),
    "creative.path.list": ToolBinding("get_path_items", RiskClass.READ),
    "creative.group.list": ToolBinding("get_groups", RiskClass.READ),
    "creative.text.list": ToolBinding("list_text_frames", RiskClass.READ),
    "creative.object.find": ToolBinding("find_objects", RiskClass.READ),
    "creative.job.status": ToolBinding("illustrator_job_status", RiskClass.READ),
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
    def __init__(self, client: UpstreamToolClient, *, version: str | None = None, writes_enabled: bool = True) -> None:
        self._client = client
        self._version = version
        self._writes_enabled = writes_enabled
        self._ready_until = 0.0

    def _supported_bindings(self) -> dict[str, ToolBinding]:
        supported = getattr(self._client, "supported_legacy_tools", None)
        if supported is None:
            return _BINDINGS
        return {
            capability: binding
            for capability, binding in _BINDINGS.items()
            if binding.upstream_tool in supported
        }

    def info(self) -> AdapterInfo:
        bindings = self._supported_bindings()
        return AdapterInfo(
            application="illustrator",
            connected=self._client.connected,
            version=self._version,
            common_capabilities=frozenset(bindings),
            capability_risks={name: binding.risk for name, binding in bindings.items()},
            writes_enabled=self._writes_enabled,
            undo_supported="creative.undo" in bindings,
            transport="mcp+cep-websocket",
            upstream_repository=UPSTREAM_REPOSITORY,
            upstream_snapshot=UPSTREAM_SNAPSHOT,
            readiness_probe="creative.health",
        )

    @staticmethod
    def _translate_arguments(capability: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if capability == "creative.health":
            translated: dict[str, Any] = {"limit": 1}
            if "probe" in arguments:
                translated["probe"] = arguments["probe"]
            if "timeout" in arguments:
                translated["timeout"] = arguments["timeout"]
            return translated
        if capability == "creative.job.status":
            if arguments.get("finalize_export") is True:
                raise ValueError("creative.job.status is inspection-only; finalize_export is not allowed")
            job_id = arguments.get("jobId", arguments.get("job_id"))
            if not isinstance(job_id, str) or not job_id.strip():
                raise ValueError("creative.job.status requires a non-empty jobId")
            detail = arguments.get("detail", "full")
            if detail not in {"summary", "full"}:
                raise ValueError("creative.job.status detail must be 'summary' or 'full'")
            return {"jobId": job_id.strip(), "detail": detail, "finalize_export": False}
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

    @staticmethod
    def _single_selected_item(selection: Mapping[str, Any]) -> Mapping[str, Any]:
        items = selection.get("items")
        if not isinstance(items, list):
            raise ValueError("Illustrator selection response has no items list")
        if len(items) == 0:
            raise ValueError("no Illustrator object is currently selected")
        if len(items) != 1:
            raise ValueError(
                f"exactly one Illustrator object must be selected for this operation; got {len(items)}"
            )
        item = items[0]
        if not isinstance(item, Mapping):
            raise ValueError("selected Illustrator item has an invalid shape")
        uuid = item.get("uuid")
        if not isinstance(uuid, str) or not uuid.strip():
            raise ValueError("selected Illustrator object has no stable UUID")
        return item

    @staticmethod
    def _selection_coordinate_arguments(arguments: Mapping[str, Any]) -> dict[str, Any]:
        coordinate_system = arguments.get("coordinate_system")
        if isinstance(coordinate_system, str) and coordinate_system.strip():
            return {"coordinate_system": coordinate_system}
        return {}

    def _execute_selected_update(self, arguments: Mapping[str, Any]) -> tuple[Mapping[str, Any], str, str]:
        properties = arguments.get("properties")
        if not isinstance(properties, Mapping) or not properties:
            raise ValueError("creative.selection.update requires a non-empty properties object")

        # The read happens immediately before the mutation so a manual mouse click
        # in Illustrator becomes the target of the very next conversational edit.
        selection_args = self._selection_coordinate_arguments(arguments)
        selection = self._client.call_tool("get_selection", selection_args)
        item = self._single_selected_item(selection)
        selected_uuid = str(item["uuid"])

        modify_args: dict[str, Any] = {
            "uuid": selected_uuid,
            "properties": dict(properties),
        }
        modify_args.update(selection_args)
        try:
            result = self._client.call_tool("modify_object", modify_args)
        except TimeoutError as exc:
            # Selection resolution is read-only; only a timeout after modify_object
            # starts has an ambiguous mutation outcome.
            self._ready_until = 0.0
            raise OperationUnknownError("creative.selection.update", "modify_object") from exc
        return result, "get_selection->modify_object", selected_uuid

    def _execute_selected_move(self, arguments: Mapping[str, Any]) -> tuple[Mapping[str, Any], str, str]:
        dx = arguments.get("deltaX", 0)
        dy = arguments.get("deltaY", 0)
        if not isinstance(dx, (int, float)) or isinstance(dx, bool):
            raise ValueError("creative.selection.move deltaX must be numeric")
        if not isinstance(dy, (int, float)) or isinstance(dy, bool):
            raise ValueError("creative.selection.move deltaY must be numeric")
        if dx == 0 and dy == 0:
            raise ValueError("creative.selection.move requires a non-zero deltaX or deltaY")

        selection_args = self._selection_coordinate_arguments(arguments)
        selection = self._client.call_tool("get_selection", selection_args)
        item = self._single_selected_item(selection)
        selected_uuid = str(item["uuid"])
        bounds = item.get("bounds")
        if not isinstance(bounds, Mapping):
            raise ValueError("selected Illustrator object has no readable bounds")
        x = bounds.get("x")
        y = bounds.get("y")
        if not isinstance(x, (int, float)) or isinstance(x, bool):
            raise ValueError("selected Illustrator object has no numeric x position")
        if not isinstance(y, (int, float)) or isinstance(y, bool):
            raise ValueError("selected Illustrator object has no numeric y position")

        modify_args: dict[str, Any] = {
            "uuid": selected_uuid,
            "properties": {"position": {"x": x + dx, "y": y + dy}},
        }
        modify_args.update(selection_args)
        try:
            result = self._client.call_tool("modify_object", modify_args)
        except TimeoutError as exc:
            self._ready_until = 0.0
            raise OperationUnknownError("creative.selection.move", "modify_object") from exc
        return result, "get_selection->modify_object", selected_uuid

    def probe_ready(self) -> Mapping[str, Any]:
        now = time.monotonic()
        if self._ready_until > now:
            return {"ready": True, "application": "illustrator", "source": "list_fonts", "cached": True}
        try:
            result = self._client.call_tool("list_fonts", {"limit": 1})
        except Exception:
            self._ready_until = 0.0
            return {"ready": False, "application": "illustrator", "source": "list_fonts", "cached": False, "reason": "illustrator_health_probe_failed"}
        ready = self._health_ready(result)
        self._ready_until = now + READINESS_TTL_SECONDS if ready else 0.0
        return {"ready": ready, "application": "illustrator", "source": "list_fonts", "cached": False, "reason": None if ready else "illustrator_health_probe_not_ready"}

    def execute(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            binding = _BINDINGS[capability]
        except KeyError as exc:
            raise LookupError(f"unsupported Illustrator capability: {capability}") from exc
        if capability not in self._supported_bindings():
            raise LookupError(
                f"Illustrator backend does not safely implement capability: {capability}"
            )

        file_snapshot = capture_file_snapshot(arguments) if binding.risk is RiskClass.FILE_WRITE else None
        selected_uuid: str | None = None
        try:
            if capability == "creative.context.get":
                document = self._client.call_tool("get_document_info", {})
                selection = self._client.call_tool("get_selection", {})
                result: Mapping[str, Any] = {"document": document, "selection": selection}
                upstream_tool = "get_document_info+get_selection"
            elif capability == "creative.selection.update":
                # Any timeout in the live selection read remains a normal read timeout.
                result, upstream_tool, selected_uuid = self._execute_selected_update(arguments)
            elif capability == "creative.selection.move":
                result, upstream_tool, selected_uuid = self._execute_selected_move(arguments)
            else:
                result = self._client.call_tool(binding.upstream_tool, self._translate_arguments(capability, arguments))
                upstream_tool = binding.upstream_tool
        except TimeoutError as exc:
            if capability in {"creative.selection.update", "creative.selection.move"}:
                # The composite helpers already convert only the mutating timeout to UNKNOWN;
                # a TimeoutError reaching here came from the read-only get_selection call.
                raise
            if self._is_mutating(capability):
                self._ready_until = 0.0
                raise OperationUnknownError(capability, binding.upstream_tool) from exc
            raise

        if capability == "creative.health":
            self._ready_until = time.monotonic() + READINESS_TTL_SECONDS if self._health_ready(result) else 0.0

        payload: dict[str, Any] = {
            "ok": True,
            "application": "illustrator",
            "capability": capability,
            "upstream_tool": upstream_tool,
            "result": result,
        }
        if capability == "creative.context.get":
            payload["context_source"] = "live-document+selection"
        if selected_uuid is not None:
            payload["selection_source"] = "live-get_selection"
            payload["selected_uuid"] = selected_uuid
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
