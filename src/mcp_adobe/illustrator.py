from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .core import AdapterInfo, RiskClass
from .photoshop import OperationUnknownError, UpstreamToolClient
from .verification import capture_file_snapshot, evaluate_file_snapshot, unverified_mutation

UPSTREAM_REPOSITORY = "ie3jp/illustrator-mcp-server"
UPSTREAM_SNAPSHOT = "57c5c101a5192c61535493f39b653e6f92b8eb29"
UPSTREAM_PACKAGE = "illustrator-mcp-server@1.10.3"


@dataclass(frozen=True, slots=True)
class ToolBinding:
    upstream_tool: str
    risk: RiskClass


_BINDINGS: dict[str, ToolBinding] = {
    "creative.document.info": ToolBinding("get_document_info", RiskClass.READ),
    "creative.document.structure": ToolBinding("get_document_structure", RiskClass.READ),
    "creative.selection.get": ToolBinding("get_selection", RiskClass.READ),
    "creative.document.create": ToolBinding("create_document", RiskClass.WRITE_REVERSIBLE),
    "creative.document.open": ToolBinding("open_document", RiskClass.WRITE_REVERSIBLE),
    "creative.document.save": ToolBinding("save_document", RiskClass.FILE_WRITE),
    "creative.document.export": ToolBinding("export", RiskClass.FILE_WRITE),
    "creative.document.export_pdf": ToolBinding("export_pdf", RiskClass.FILE_WRITE),
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
        )

    @staticmethod
    def _translate_arguments(capability: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        args = dict(arguments)
        if capability in {"creative.document.export", "creative.document.export_pdf"}:
            path = args.pop("path", None)
            if path is not None:
                args["output_path"] = path
        return args

    @staticmethod
    def _is_mutating(capability: str) -> bool:
        return _BINDINGS[capability].risk is not RiskClass.READ

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
                raise OperationUnknownError(capability, binding.upstream_tool) from exc
            raise

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
