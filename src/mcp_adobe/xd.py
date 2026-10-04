from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .core import AdapterInfo, RiskClass
from .photoshop import OperationUnknownError, UpstreamToolClient
from .verification import pending_user_approval, unverified_mutation

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
    "xd.queue.status": ToolBinding("xd.queue.status", RiskClass.READ),
    "xd.queue.rectangle_create": ToolBinding("xd.queue.rectangle_create", RiskClass.WRITE_REVERSIBLE),
    "xd.queue.text_create": ToolBinding("xd.queue.text_create", RiskClass.WRITE_REVERSIBLE),
    "xd.queue.selection_resize": ToolBinding("xd.queue.selection_resize", RiskClass.WRITE_REVERSIBLE),
    "xd.queue.selection_fill": ToolBinding("xd.queue.selection_fill", RiskClass.WRITE_REVERSIBLE),
}


class XdAdapter:
    """Adobe XD adapter backed by the local UXP WebSocket bridge.

    Adobe XD only permits ``application.editDocument()`` from explicit user UI
    actions. Therefore bridge-triggered mutations are queued, not applied in the
    WebSocket callback. The user approves the pending batch from the XD panel,
    where the plugin applies it atomically inside ``editDocument()``.
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
        common = frozenset(name for name in _BINDINGS if name.startswith("creative."))
        native = frozenset(name for name in _BINDINGS if name.startswith("xd."))
        return AdapterInfo(
            application="xd",
            connected=self._client.connected,
            version=self._version,
            common_capabilities=common,
            native_capabilities=native,
            capability_risks={name: binding.risk for name, binding in _BINDINGS.items()},
            writes_enabled=self._writes_enabled,
            undo_supported=False,
            transport="uxp-websocket-approval",
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

        payload: dict[str, Any] = {
            "ok": True,
            "application": "xd",
            "capability": capability,
            "bridge_method": binding.bridge_method,
            "result": result,
        }
        if binding.risk is RiskClass.READ:
            payload["outcome"] = "read"
            payload["verification"] = {"status": "not_applicable"}
            return payload

        if isinstance(result, Mapping) and (
            result.get("approval_required") is True or result.get("status") == "queued"
        ):
            outcome, verification = pending_user_approval(result.get("operation_id"))
        else:
            outcome, verification = unverified_mutation(
                "xd-mutation-response-not-confirmed-applied"
            )
        payload["outcome"] = outcome
        payload["verification"] = verification
        return payload
