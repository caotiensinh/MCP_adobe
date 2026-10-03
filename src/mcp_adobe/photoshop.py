from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .core import AdapterInfo, RiskClass


UPSTREAM_REPOSITORY = "alisaitteke/photoshop-mcp"
UPSTREAM_SNAPSHOT = "ecd502c666f0e5b3889d3ef7bc42e5b3eb1119c2"


class UpstreamToolClient(Protocol):
    """Minimal transport-neutral client for a downstream MCP server."""

    @property
    def connected(self) -> bool:
        ...

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class OperationUnknownError(RuntimeError):
    """A mutating call timed out and may still have completed inside Photoshop."""

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
    "creative.document.info": ToolBinding("photoshop_get_state", RiskClass.READ),
    "creative.document.preview": ToolBinding("photoshop_get_preview", RiskClass.READ),
    "creative.document.create": ToolBinding("photoshop_create_document", RiskClass.WRITE_REVERSIBLE),
    "creative.document.open": ToolBinding("photoshop_open_image", RiskClass.WRITE_REVERSIBLE),
    "creative.document.save": ToolBinding("photoshop_save_document", RiskClass.FILE_WRITE),
    "creative.document.export": ToolBinding("photoshop_export_as", RiskClass.FILE_WRITE),
    "creative.undo": ToolBinding("photoshop_undo", RiskClass.WRITE_REVERSIBLE),
    "photoshop.execute_script": ToolBinding("photoshop_execute_script", RiskClass.NATIVE_SCRIPT),
}


class PhotoshopAdapter:
    """Adapter over the pinned alisaitteke/photoshop-mcp tool surface."""

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
        )

    @staticmethod
    def _translate_arguments(capability: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        args = dict(arguments)
        # overwrite is enforced by the gateway; upstream save/export tools do not accept it.
        args.pop("overwrite", None)

        if capability == "creative.document.open":
            path = args.pop("path", None)
            if path is not None:
                args["filePath"] = path
        return args

    @staticmethod
    def _is_mutating(capability: str) -> bool:
        return _BINDINGS[capability].risk is not RiskClass.READ

    def execute(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            binding = _BINDINGS[capability]
        except KeyError as exc:
            raise LookupError(f"unsupported Photoshop capability: {capability}") from exc

        upstream_args = self._translate_arguments(capability, arguments)
        try:
            result = self._client.call_tool(binding.upstream_tool, upstream_args)
        except TimeoutError as exc:
            if self._is_mutating(capability):
                raise OperationUnknownError(capability, binding.upstream_tool) from exc
            raise

        return {
            "ok": True,
            "application": "photoshop",
            "capability": capability,
            "upstream_tool": binding.upstream_tool,
            "result": result,
        }
