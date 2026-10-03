from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .core import AdapterInfo, RiskClass
from .photoshop import OperationUnknownError, UpstreamToolClient

OFFICIAL_API_REPOSITORY = "AdobeXD/plugin-docs"
OFFICIAL_API_SNAPSHOT = "c1abde873604a1606a5fdd5a578fba4502a7bdfc"


@dataclass(frozen=True, slots=True)
class ToolBinding:
    bridge_method: str
    risk: RiskClass


_BINDINGS: dict[str, ToolBinding] = {
    "creative.health": ToolBinding("xd.health", RiskClass.READ),
    "creative.document.info": ToolBinding("xd.document.info", RiskClass.READ),
    "creative.selection.get": ToolBinding("xd.selection.get", RiskClass.READ),
    "creative.object.rectangle.create": ToolBinding("xd.rectangle.create", RiskClass.WRITE_REVERSIBLE),
    "creative.object.text.create": ToolBinding("xd.text.create", RiskClass.WRITE_REVERSIBLE),
    "creative.selection.resize": ToolBinding("xd.selection.resize", RiskClass.WRITE_REVERSIBLE),
    "creative.selection.fill": ToolBinding("xd.selection.fill", RiskClass.WRITE_REVERSIBLE),
}


class XdAdapter:
    """Live Adobe XD adapter backed by the local UXP WebSocket bridge.

    The bridge is intentionally small: the UXP plugin owns all XD API calls and
    this adapter only normalizes the gateway capability surface. XD mutations are
    issued by the plugin inside ``application.editDocument()`` edit operations.
    """

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
            application="xd",
            connected=self._client.connected,
            version=self._version,
            common_capabilities=frozenset(_BINDINGS),
            capability_risks={name: binding.risk for name, binding in _BINDINGS.items()},
            writes_enabled=self._writes_enabled,
            # Adobe XD exposes atomic edit operations, but the audited API surface
            # does not expose a documented programmatic undo primitive.
            undo_supported=False,
            transport="uxp-websocket",
            upstream_repository=OFFICIAL_API_REPOSITORY,
            upstream_snapshot=OFFICIAL_API_SNAPSHOT,
        )

    @staticmethod
    def _is_mutating(capability: str) -> bool:
        return _BINDINGS[capability].risk is not RiskClass.READ

    def execute(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            binding = _BINDINGS[capability]
        except KeyError as exc:
            raise LookupError(f"unsupported Adobe XD capability: {capability}") from exc

        try:
            result = self._client.call_tool(binding.bridge_method, dict(arguments))
        except TimeoutError as exc:
            if self._is_mutating(capability):
                raise OperationUnknownError(capability, binding.bridge_method) from exc
            raise

        return {
            "ok": True,
            "application": "xd",
            "capability": capability,
            "bridge_method": binding.bridge_method,
            "result": result,
        }
