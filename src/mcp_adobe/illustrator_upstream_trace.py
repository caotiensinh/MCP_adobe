"""Diagnostic-only, fail-closed upstream bridge instrumentation.

Installs a wrapper on the *loaded class* without changing request admission,
fence decisions, or retry behavior. Logs only correlation-safe fields.
"""
from __future__ import annotations
import logging
import json
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("mcp_adobe.illustrator_trace")


def install_trace(bridge_class: type) -> None:
    # Separate upstream file: gateway parent logs do not capture every child.
    trace_path = Path(os.environ.get("LOCALAPPDATA", ".")) / "MCPAdobe" / "illustrator-mcp" / "callback_trace.log"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == str(trace_path) for h in log.handlers):
        handler = logging.FileHandler(trace_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
    log.setLevel(logging.WARNING)
    original_handle = getattr(bridge_class, '_handle_message', None)
    if original_handle is not None and not getattr(original_handle, "_mcp_adobe_trace", False):
        async def traced_handle(self: Any, message: str) -> Any:
            kind = None
            request_id = None
            try:
                envelope = json.loads(message)
                kind = envelope.get("type", "complete")
                if kind != "heartbeat":
                    request_id = envelope.get("id")
                    pending = self.registry.get_pending(request_id) if request_id else None
                    log.warning(
                        "CEP_CALLBACK kind=%s requestId=%s pending=%s tokenMatch=%s payloadError=%s descriptorPresent=%s panelBusy=%s activeRequest=%s",
                        str(kind)[:36], str(request_id)[:48], bool(pending),
                        bool(pending and pending.request_token == envelope.get("requestToken")),
                        str(envelope.get("payloadError"))[:80],
                        isinstance(envelope.get("descriptor"), dict),
                        bool(self._panel_busy), str(self._panel_active_request)[:48],
                    )
            except Exception as exc:
                log.warning("CEP_CALLBACK_PARSE_ERROR class=%s", type(exc).__name__)
            try:
                result = await original_handle(self, message)
                # Correlate a late completion after the original handler safely
                # discarded/ACKed it. Never unlock here: only establish the
                # observed predecessor completion required by a later trusted probe.
                if kind == "complete" and isinstance(envelope, dict):
                    from illustrator_mcp.execution import get_coordinator
                    coordinator = get_coordinator()
                    fence = coordinator.probe_fence
                    if (isinstance(fence, dict)
                            and fence.get("requestId") == request_id
                            and fence.get("requestToken") == envelope.get("requestToken")
                            and isinstance(envelope.get("requestToken"), str)
                            and envelope.get("requestToken")):
                        fence["priorCompletionObserved"] = True
                        log.warning("CEP_LATE_FENCE_COMPLETION requestId=%s generation=%s",
                                    str(request_id)[:48], fence.get("connectionGeneration"))
                if kind is not None and kind != "heartbeat":
                    log.warning("CEP_CALLBACK_HANDLED kind=%s requestId=%s panelBusy=%s activeRequest=%s",
                                str(kind)[:36], str(request_id)[:48],
                                bool(self._panel_busy), str(self._panel_active_request)[:48])
                return result
            except Exception as exc:
                log.exception("CEP_CALLBACK_EXCEPTION class=%s", type(exc).__name__)
                raise
        traced_handle._mcp_adobe_trace = True
        bridge_class._handle_message = traced_handle

    original = bridge_class.execute_script_async
    if getattr(original, "_mcp_adobe_trace", False):
        return

    async def traced(self: Any, *args: Any, **kwargs: Any) -> Any:
        from illustrator_mcp.execution import get_coordinator
        coordinator = get_coordinator()
        fence_before = coordinator.probe_fence
        job = kwargs.get("command")
        log.warning(
            "HOST_TRACE start fence=%s priorCompletion=%s generation=%s command_type=%s",
            bool(fence_before),
            fence_before.get("priorCompletionObserved") if isinstance(fence_before, dict) else None,
            coordinator.connection_generation,
            type(job).__name__,
        )
        try:
            result = await original(self, *args, **kwargs)
            fence_after = coordinator.probe_fence
            log.warning(
                "HOST_TRACE result type=%s error=%s fence=%s priorCompletion=%s generation=%s",
                type(result).__name__,
                str(result.get("error"))[:240] if isinstance(result, dict) else None,
                bool(fence_after),
                fence_after.get("priorCompletionObserved") if isinstance(fence_after, dict) else None,
                coordinator.connection_generation,
            )
            return result
        except Exception as exc:
            log.exception("HOST_TRACE exception class=%s", type(exc).__name__)
            raise

    traced._mcp_adobe_trace = True
    bridge_class.execute_script_async = traced
