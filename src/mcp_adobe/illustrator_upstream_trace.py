"""Diagnostic-only, fail-closed upstream bridge instrumentation.

Installs a wrapper on the *loaded class* without changing request admission,
fence decisions, or retry behavior. Logs only correlation-safe fields.
"""
from __future__ import annotations
import logging
from typing import Any

log = logging.getLogger("mcp_adobe.illustrator_trace")


def install_trace(bridge_class: type) -> None:
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
