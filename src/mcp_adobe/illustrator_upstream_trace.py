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


def _verified_payload_completion(envelope: dict[str, Any], pending: Any) -> bool:
    """Only a successfully assembled, correlated payload proves prior host completion.

    Upstream can ACK and set the predecessor fence on a C014 complete message;
    that transport acknowledgement alone cannot prove host effects finished.
    """
    if envelope.get("type", "complete") != "complete" or envelope.get("payloadError"):
        return False
    token = envelope.get("requestToken")
    if not isinstance(token, str) or not token or pending is None or pending.request_token != token:
        return False
    receiver = getattr(pending, "payload", None)
    return bool(receiver is not None
                and isinstance(getattr(receiver, "descriptor", None), dict)
                and getattr(receiver, "failure", None) is None)


def install_trace(bridge_class: type) -> None:
    # Separate upstream file: gateway parent logs do not capture every child.
    trace_path = Path(os.environ.get("LOCALAPPDATA", ".")) / "MCPAdobe" / "illustrator-mcp" / "callback_trace.log"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == str(trace_path) for h in log.handlers):
        handler = logging.FileHandler(trace_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
    log.setLevel(logging.WARNING)
    # The JSX payload epoch changes when the Illustrator host reloads. Never
    # carry a cached hostSession pin into a new CEP WebSocket connection.
    # Old in-flight receivers retain their own descriptor expectations.
    original_disconnect = getattr(bridge_class, "_handle_disconnect", None)
    if original_disconnect is not None and not getattr(original_disconnect, "_mcp_adobe_epoch_reset", False):
        async def traced_disconnect(self: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                return await original_disconnect(self, *args, **kwargs)
            finally:
                if getattr(self, "_host_payload_session", None) is not None:
                    self._host_payload_session = None
                    log.warning("CEP_HOST_EPOCH_CACHE_INVALIDATED reason=disconnect")
        traced_disconnect._mcp_adobe_epoch_reset = True
        bridge_class._handle_disconnect = traced_disconnect

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
                # The upstream handler itself records matched late completions.
                # Snapshot the exact fence before invoking it, then undo only
                # an unauthorized stale-generation transition after handling.
                tracked_fence = None
                tracked_prior = None
                if kind == "complete" and isinstance(envelope, dict):
                    from illustrator_mcp.execution import get_coordinator
                    upstream_coordinator = get_coordinator()
                    candidate = upstream_coordinator.probe_fence
                    if (isinstance(candidate, dict)
                            and candidate.get("requestId") == request_id
                            and candidate.get("requestToken") == envelope.get("requestToken")
                            and isinstance(candidate.get("connectionGeneration"), int)):
                        tracked_fence = candidate
                        tracked_prior = candidate.get("priorCompletionObserved")
                result = await original_handle(self, message)
                if tracked_fence is not None and upstream_coordinator.probe_fence is tracked_fence:
                    same_generation = tracked_fence["connectionGeneration"] == upstream_coordinator.connection_generation
                    verified = same_generation and _verified_payload_completion(envelope, pending)
                    if verified and tracked_fence.get("priorCompletionObserved") is True:
                        log.warning("CEP_VERIFIED_FENCE_COMPLETION requestId=%s generation=%s",
                                    str(request_id)[:48], tracked_fence["connectionGeneration"])
                    else:
                        # Upstream may optimistically mark any matching complete,
                        # even C014 missing_descriptor. Undo that unproven promotion.
                        tracked_fence["priorCompletionObserved"] = tracked_prior
                        log.warning("CEP_UNVERIFIED_FENCE_COMPLETION_IGNORED requestId=%s generation=%s payloadError=%s",
                                    str(request_id)[:48], tracked_fence["connectionGeneration"],
                                    str(envelope.get("payloadError"))[:80])
                # A C013 result is terminal/unknown for this request, not a
                # license to retry. Discard ONLY the cached epoch hint so a
                # future safely admitted request can bind to the actual JSX
                # payload-store epoch after reconciliation.
                if (kind == "complete" and isinstance(envelope, dict)
                        and envelope.get("payloadError") == "stale_host_session"):
                    self._host_payload_session = None
                    log.warning("CEP_HOST_EPOCH_CACHE_INVALIDATED reason=C013")
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
