from __future__ import annotations

import argparse
import logging
import atexit
import os
import sys
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Iterable, Mapping, Protocol
from uuid import uuid4

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import TokenVerifier
from mcp.types import ToolAnnotations

from .audit import (
    JsonLineSecurityAuditSink,
    NullSecurityAuditSink,
    SecurityAuditEvent,
    SecurityAuditSink,
)
from .auth import HIGH_RISK_SCOPE, WRITE_SCOPE, IntrospectionTokenVerifier, OAuthResourceConfig
from .core import AdapterInfo, CapabilityRegistry, ExecutionPolicy, PolicyError, RiskClass
from .illustrator import IllustratorAdapter
from .mcp_stdio import McpSubprocessToolClient, illustrator_stdio_config, photoshop_stdio_config
from .photoshop import OperationUnknownError, PhotoshopAdapter

logger = logging.getLogger(__name__)
from .xd import XdAdapter
from .xd_bridge import XdWebSocketBridgeClient


class GatewayRuntimeProtocol(Protocol):
    def describe(self) -> tuple[AdapterInfo, ...]:
        ...

    def read(self, application: str, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        ...

    def write(
        self,
        application: str,
        capability: str,
        arguments: Mapping[str, Any],
        *,
        allow_overwrite: bool = False,
    ) -> Mapping[str, Any]:
        ...

    def authorized_write(
        self,
        application: str,
        capability: str,
        arguments: Mapping[str, Any],
        *,
        allow_overwrite: bool = False,
        allow_destructive: bool = False,
        allow_native_script: bool = False,
        allow_external_ai: bool = False,
    ) -> Mapping[str, Any]:
        ...

    def close(self) -> None:
        ...


@dataclass
class GatewayRuntime:
    """Own the local Adobe adapter clients and enforce operation classes."""

    xd_port: int = 8765
    writes_enabled: bool = True

    def __post_init__(self) -> None:
        self._photoshop_client = McpSubprocessToolClient(photoshop_stdio_config())
        self._illustrator_client = McpSubprocessToolClient(illustrator_stdio_config())
        self._xd_client = XdWebSocketBridgeClient(port=self.xd_port)

        self.registry = CapabilityRegistry()
        self.registry.register(
            PhotoshopAdapter(self._photoshop_client, writes_enabled=self.writes_enabled)
        )
        self.registry.register(
            IllustratorAdapter(self._illustrator_client, writes_enabled=self.writes_enabled)
        )
        self.registry.register(XdAdapter(self._xd_client, writes_enabled=self.writes_enabled))

    def describe(self) -> tuple[AdapterInfo, ...]:
        return self.registry.describe()

    def prewarm(
        self,
        applications: Iterable[str],
        *,
        strict: bool = False,
    ) -> dict[str, str]:
        """Start selected Adobe bridges before the first MCP tool call."""
        requested: list[str] = []
        for raw in applications:
            name = str(raw).strip().lower()
            if not name:
                continue
            names = ("photoshop", "illustrator", "xd") if name == "all" else (name,)
            for item in names:
                if item not in {"photoshop", "illustrator", "xd"}:
                    raise ValueError(f"unsupported prewarm application: {item}")
                if item not in requested:
                    requested.append(item)

        starters = {
            "photoshop": self._photoshop_client.start,
            "illustrator": self._illustrator_client.start,
            "xd": self._xd_client.start,
        }
        results: dict[str, str] = {}
        for application in requested:
            try:
                starters[application]()
            except Exception as exc:
                results[application] = f"error:{type(exc).__name__}:{exc}"
                if strict:
                    raise RuntimeError(f"failed to prewarm {application}") from exc
            else:
                results[application] = "started"
        return results

    def _risk(self, application: str, capability: str) -> RiskClass:
        adapter = self.registry.resolve(application, capability)
        return adapter.info().risk_for(capability)

    def read(self, application: str, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        risk = self._risk(application, capability)
        if risk is not RiskClass.READ:
            raise PolicyError(
                f"creative_read only accepts read capabilities; {capability} is {risk.value}"
            )
        return self.registry.execute(application, capability, arguments)

    def write(
        self,
        application: str,
        capability: str,
        arguments: Mapping[str, Any],
        *,
        allow_overwrite: bool = False,
    ) -> Mapping[str, Any]:
        risk = self._risk(application, capability)
        if risk not in {RiskClass.WRITE_REVERSIBLE, RiskClass.FILE_WRITE}:
            raise PolicyError(
                "creative_write only accepts reversible/file writes; "
                f"{capability} is {risk.value}. Use creative_authorized_write for higher-risk actions."
            )
        return self.registry.execute(
            application,
            capability,
            arguments,
            policy=ExecutionPolicy(allow_overwrite=allow_overwrite),
        )

    def authorized_write(
        self,
        application: str,
        capability: str,
        arguments: Mapping[str, Any],
        *,
        allow_overwrite: bool = False,
        allow_destructive: bool = False,
        allow_native_script: bool = False,
        allow_external_ai: bool = False,
    ) -> Mapping[str, Any]:
        risk = self._risk(application, capability)
        if risk is RiskClass.READ:
            raise PolicyError("read capabilities must use creative_read")
        return self.registry.execute(
            application,
            capability,
            arguments,
            policy=ExecutionPolicy(
                allow_overwrite=allow_overwrite,
                allow_destructive=allow_destructive,
                allow_native_script=allow_native_script,
                allow_external_ai=allow_external_ai,
            ),
        )

    def close(self) -> None:
        self._photoshop_client.close()
        self._illustrator_client.close()
        self._xd_client.close()


_DEFAULT_RUNTIME: GatewayRuntime | None = None
_DEFAULT_RUNTIME_LOCK = Lock()


def _get_default_runtime() -> GatewayRuntime:
    global _DEFAULT_RUNTIME
    with _DEFAULT_RUNTIME_LOCK:
        if _DEFAULT_RUNTIME is None:
            xd_port = int(os.environ.get("MCP_ADOBE_XD_PORT", "8765"))
            writes_enabled = os.environ.get("MCP_ADOBE_WRITES", "1").strip().lower() not in {
                "0",
                "false",
                "no",
                "off",
            }
            _DEFAULT_RUNTIME = GatewayRuntime(xd_port=xd_port, writes_enabled=writes_enabled)
        return _DEFAULT_RUNTIME


def shutdown_default_runtime() -> None:
    global _DEFAULT_RUNTIME
    with _DEFAULT_RUNTIME_LOCK:
        runtime = _DEFAULT_RUNTIME
        _DEFAULT_RUNTIME = None
    if runtime is not None:
        runtime.close()


atexit.register(shutdown_default_runtime)


def _adapter_info_payload(info: AdapterInfo) -> dict[str, Any]:
    risks = {
        capability: risk.value
        for capability, risk in sorted(info.capability_risks.items(), key=lambda item: item[0])
    }
    return {
        "application": info.application,
        "connected": info.connected,
        "transport_connected": info.connected,
        "connection_semantics": "transport_only",
        "readiness_probe": info.readiness_probe,
        "readiness_status": "not_probed" if info.readiness_probe else "not_declared",
        "version": info.version,
        "common_capabilities": sorted(info.common_capabilities),
        "native_capabilities": sorted(info.native_capabilities),
        "capability_risks": risks,
        "writes_enabled": info.writes_enabled,
        "undo_supported": info.undo_supported,
        "transport": info.transport,
        "upstream_repository": info.upstream_repository,
        "upstream_snapshot": info.upstream_snapshot,
    }


def build_server(
    runtime: GatewayRuntimeProtocol | None = None,
    *,
    oauth_config: OAuthResourceConfig | None = None,
    token_verifier: TokenVerifier | None = None,
    audit_sink: SecurityAuditSink | None = None,
) -> MCPServer:
    """Build one MCP surface usable over stdio or Streamable HTTP."""

    if bool(oauth_config) != bool(token_verifier):
        raise ValueError("oauth_config and token_verifier must be supplied together")

    server_kwargs: dict[str, Any] = {}
    if oauth_config is not None and token_verifier is not None:
        server_kwargs["auth"] = oauth_config.auth_settings()
        server_kwargs["token_verifier"] = token_verifier

    mcp = MCPServer("MCP Adobe Creative Gateway", **server_kwargs)
    security_audit = audit_sink if audit_sink is not None else NullSecurityAuditSink()

    def current_runtime() -> GatewayRuntimeProtocol:
        return runtime if runtime is not None else _get_default_runtime()

    def audit(
        tool: str,
        decision: str,
        *,
        application: str | None = None,
        capability: str | None = None,
        reason: str | None = None,
        operation_id: str | None = None,
        outcome: str | None = None,
    ) -> None:
        security_audit.emit(
            SecurityAuditEvent(
                tool=tool,
                decision=decision,
                application=application,
                capability=capability,
                reason=reason,
                operation_id=operation_id,
                outcome=outcome,
            ),
            get_access_token(),
        )

    def require_oauth_profile_scope(
        scope: str,
        tool_name: str,
        *,
        application: str,
        capability: str,
        operation_id: str | None = None,
    ) -> None:
        if oauth_config is None:
            return
        if scope not in oauth_config.required_scopes:
            audit(
                tool_name,
                "denied",
                application=application,
                capability=capability,
                reason=f"deployment-profile-missing:{scope}",
                operation_id=operation_id,
                outcome="denied",
            )
            raise PolicyError(
                f"{tool_name} is disabled for this OAuth deployment; add {scope} to "
                "MCP_ADOBE_OAUTH_REQUIRED_SCOPES and obtain a token carrying that scope"
            )

    def run_correlated_write(
        tool_name: str,
        operation_id: str,
        application: str,
        capability: str,
        callback,
    ) -> dict[str, Any]:
        audit(
            tool_name,
            "allowed",
            application=application,
            capability=capability,
            operation_id=operation_id,
        )
        try:
            payload = dict(callback())
        except OperationUnknownError:
            audit(
                tool_name,
                "unknown",
                application=application,
                capability=capability,
                reason="mutating-timeout",
                operation_id=operation_id,
                outcome="unknown",
            )
            raise RuntimeError(
                f"operation outcome is unknown; operation_id={operation_id}; "
                "inspect Adobe state before retrying"
            ) from None
        except PolicyError:
            audit(
                tool_name,
                "denied",
                application=application,
                capability=capability,
                reason="runtime-policy-denied",
                operation_id=operation_id,
                outcome="denied",
            )
            raise RuntimeError(
                f"operation denied by runtime policy; operation_id={operation_id}"
            ) from None
        except Exception as exc:
            audit(
                tool_name,
                "failed",
                application=application,
                capability=capability,
                reason=f"runtime-error:{type(exc).__name__}",
                operation_id=operation_id,
                outcome="failed",
            )
            logger.error(
                "creative operation failed tool=%s application=%s capability=%s operation_id=%s cause_type=%s",
                tool_name,
                application,
                capability,
                operation_id,
                type(exc).__name__,
            )
            raise RuntimeError(
                f"operation failed; operation_id={operation_id}; "
                f"cause_type={type(exc).__name__}"
            ) from None

        outcome = str(payload.get("outcome", "accepted_unverified"))
        payload["operation_id"] = operation_id
        audit(
            tool_name,
            "completed",
            application=application,
            capability=capability,
            operation_id=operation_id,
            outcome=outcome,
        )
        return payload

    @mcp.tool(
        title="Discover Adobe applications and capabilities",
        annotations=ToolAnnotations(
            read_only_hint=True,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    def creative_discover() -> dict[str, Any]:
        """List Adobe adapters, transport state, readiness probes, capabilities and risks."""
        audit("creative_discover", "allowed")
        oauth_policy = None
        if oauth_config is not None:
            required = list(oauth_config.required_scopes)
            oauth_policy = {
                "required_scopes": required,
                "normal_write_enabled": WRITE_SCOPE in oauth_config.required_scopes,
                "high_risk_write_enabled": (
                    WRITE_SCOPE in oauth_config.required_scopes
                    and HIGH_RISK_SCOPE in oauth_config.required_scopes
                ),
            }
        return {
            "applications": [
                _adapter_info_payload(info) for info in current_runtime().describe()
            ],
            "connection_contract": {
                "connected_means": "transport_connected",
                "application_ready_requires": "declared_readiness_probe",
                "discovery_probes_application": False,
            },
            "transports": ["stdio", "streamable-http"],
            "oauth_protected": oauth_config is not None,
            "oauth_policy": oauth_policy,
        }

    @mcp.tool(
        title="Read Adobe application state",
        annotations=ToolAnnotations(
            read_only_hint=True,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    def creative_read(
        application: str,
        capability: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a capability only when its gateway risk class is read-only."""
        audit("creative_read", "allowed", application=application, capability=capability)
        return dict(current_runtime().read(application, capability, arguments or {}))

    @mcp.tool(
        title="Run a normal Adobe write",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )
    def creative_write(
        application: str,
        capability: str,
        arguments: dict[str, Any] | None = None,
        allow_overwrite: bool = False,
    ) -> dict[str, Any]:
        """Execute only reversible or file-write capabilities; overwrite is opt-in."""
        operation_id = str(uuid4())
        require_oauth_profile_scope(
            WRITE_SCOPE,
            "creative_write",
            application=application,
            capability=capability,
            operation_id=operation_id,
        )
        return run_correlated_write(
            "creative_write",
            operation_id,
            application,
            capability,
            lambda: current_runtime().write(
                application,
                capability,
                arguments or {},
                allow_overwrite=allow_overwrite,
            ),
        )

    @mcp.tool(
        title="Build artwork visibly step by step",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )
    def creative_live_build(
        application: str,
        steps: list[dict[str, Any]],
        step_delay_ms: int = 450,
    ) -> dict[str, Any]:
        """Execute an ordered visual build as separate reversible writes.

        Clients should prefer this tool for multi-object drawing requests so the
        user can watch the Adobe canvas change after each step instead of seeing
        only the final composition. The client/LLM remains responsible for
        translating natural-language intent into bounded capabilities/arguments.
        """
        if not isinstance(steps, list) or not steps:
            raise ValueError("creative_live_build requires at least one step")
        if len(steps) > 64:
            raise ValueError("creative_live_build supports at most 64 steps")
        if not isinstance(step_delay_ms, int) or isinstance(step_delay_ms, bool):
            raise ValueError("step_delay_ms must be an integer")
        if step_delay_ms < 0 or step_delay_ms > 3000:
            raise ValueError("step_delay_ms must be between 0 and 3000")

        info = next(
            (item for item in current_runtime().describe() if item.application == application.strip().lower()),
            None,
        )
        if info is None:
            raise LookupError(f"no adapter registered for application: {application}")

        normalized: list[tuple[str, str, dict[str, Any]]] = []
        for index, raw in enumerate(steps, start=1):
            if not isinstance(raw, Mapping):
                raise ValueError(f"creative_live_build step {index} must be an object")
            capability = raw.get("capability")
            if not isinstance(capability, str) or not capability.strip():
                raise ValueError(f"creative_live_build step {index} requires capability")
            capability = capability.strip()
            if not info.supports(capability):
                raise LookupError(
                    f"creative_live_build step {index} unsupported capability: {capability}"
                )
            if info.risk_for(capability) is not RiskClass.WRITE_REVERSIBLE:
                raise PolicyError(
                    "creative_live_build accepts only reversible visual writes; "
                    f"step {index} {capability} is {info.risk_for(capability).value}"
                )
            arguments = raw.get("arguments", {})
            if not isinstance(arguments, Mapping):
                raise ValueError(f"creative_live_build step {index} arguments must be an object")
            label = raw.get("label")
            if label is None:
                label = capability
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"creative_live_build step {index} label must be non-empty")
            normalized.append((label.strip(), capability, dict(arguments)))

        operation_id = str(uuid4())
        require_oauth_profile_scope(
            WRITE_SCOPE,
            "creative_live_build",
            application=application,
            capability="visual-sequence",
            operation_id=operation_id,
        )
        audit(
            "creative_live_build",
            "allowed",
            application=application,
            capability="visual-sequence",
            operation_id=operation_id,
        )

        completed: list[dict[str, Any]] = []
        try:
            for index, (label, capability, arguments) in enumerate(normalized, start=1):
                step_operation_id = f"{operation_id}:{index}"
                payload = run_correlated_write(
                    "creative_live_build",
                    step_operation_id,
                    application,
                    capability,
                    lambda capability=capability, arguments=arguments: current_runtime().write(
                        application,
                        capability,
                        arguments,
                    ),
                )
                completed.append(
                    {
                        "index": index,
                        "label": label,
                        "capability": capability,
                        "outcome": payload.get("outcome", "accepted_unverified"),
                        "operation_id": payload.get("operation_id"),
                    }
                )
                if index < len(normalized) and step_delay_ms:
                    time.sleep(step_delay_ms / 1000.0)
        except Exception:
            audit(
                "creative_live_build",
                "failed",
                application=application,
                capability="visual-sequence",
                reason=f"stopped-after-step:{len(completed)}",
                operation_id=operation_id,
                outcome="partial" if completed else "failed",
            )
            raise

        audit(
            "creative_live_build",
            "completed",
            application=application,
            capability="visual-sequence",
            operation_id=operation_id,
            outcome="completed",
        )
        return {
            "ok": True,
            "application": application,
            "mode": "visual_live_build",
            "operation_id": operation_id,
            "step_delay_ms": step_delay_ms,
            "steps_total": len(normalized),
            "steps_completed": len(completed),
            "steps": completed,
        }

    @mcp.tool(
        title="Run an explicitly authorized high-risk Adobe write",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )
    def creative_authorized_write(
        application: str,
        capability: str,
        arguments: dict[str, Any] | None = None,
        allow_overwrite: bool = False,
        allow_destructive: bool = False,
        allow_native_script: bool = False,
        allow_external_ai: bool = False,
    ) -> dict[str, Any]:
        """Execute a higher-risk capability only with the corresponding explicit flags."""
        operation_id = str(uuid4())
        require_oauth_profile_scope(
            WRITE_SCOPE,
            "creative_authorized_write",
            application=application,
            capability=capability,
            operation_id=operation_id,
        )
        require_oauth_profile_scope(
            HIGH_RISK_SCOPE,
            "creative_authorized_write",
            application=application,
            capability=capability,
            operation_id=operation_id,
        )
        return run_correlated_write(
            "creative_authorized_write",
            operation_id,
            application,
            capability,
            lambda: current_runtime().authorized_write(
                application,
                capability,
                arguments or {},
                allow_overwrite=allow_overwrite,
                allow_destructive=allow_destructive,
                allow_native_script=allow_native_script,
                allow_external_ai=allow_external_ai,
            ),
        )

    return mcp


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCP Adobe Creative Gateway")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=os.environ.get("MCP_ADOBE_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=os.environ.get("MCP_ADOBE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_ADOBE_PORT", "8787")))
    parser.add_argument("--path", default=os.environ.get("MCP_ADOBE_PATH", "/mcp"))
    parser.add_argument(
        "--prewarm",
        action="append",
        choices=("photoshop", "illustrator", "xd", "all"),
        default=[],
        help="Start selected Adobe bridge(s) when the gateway starts; repeatable.",
    )
    parser.add_argument(
        "--prewarm-strict",
        action="store_true",
        help="Exit if a requested prewarm bridge cannot be started.",
    )
    parser.add_argument(
        "--allow-non-loopback",
        action="store_true",
        help="Allow an OAuth-protected non-loopback bind. Prefer Secure MCP Tunnel/reverse proxy.",
    )
    return parser.parse_args()


def _load_oauth_config() -> OAuthResourceConfig | None:
    try:
        return OAuthResourceConfig.from_env()
    except ValueError as exc:
        raise SystemExit(f"Invalid MCP Adobe OAuth configuration: {exc}") from exc


def _load_audit_sink(oauth_config: OAuthResourceConfig | None) -> SecurityAuditSink | None:
    if oauth_config is None:
        return None
    try:
        return JsonLineSecurityAuditSink()
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Invalid MCP Adobe audit configuration: {exc}") from exc


def main() -> None:
    args = _parse_args()
    if not (1 <= args.port <= 65535):
        raise SystemExit("--port must be between 1 and 65535")
    if not args.path.startswith("/"):
        raise SystemExit("--path must start with /")

    oauth_config: OAuthResourceConfig | None = None
    token_verifier: TokenVerifier | None = None
    audit_sink: SecurityAuditSink | None = None
    if args.transport == "streamable-http":
        oauth_config = _load_oauth_config()
        if oauth_config is not None:
            token_verifier = IntrospectionTokenVerifier(oauth_config)
            audit_sink = _load_audit_sink(oauth_config)

        loopback = args.host in {"127.0.0.1", "localhost", "::1"}
        if not loopback and not args.allow_non_loopback:
            raise SystemExit(
                "Refusing non-loopback bind without --allow-non-loopback. "
                "Prefer Secure MCP Tunnel or an authenticated HTTPS reverse proxy."
            )
        if not loopback and oauth_config is None:
            raise SystemExit(
                "Refusing unauthenticated non-loopback MCP HTTP. Configure OAuth resource-server "
                "environment variables before using --allow-non-loopback."
            )
        if not loopback and not oauth_config.resource_url.startswith("https://"):
            raise SystemExit("Non-loopback OAuth resource URL must use https")

    runtime: GatewayRuntime | None = None
    if args.prewarm:
        runtime = _get_default_runtime()
        results = runtime.prewarm(args.prewarm, strict=args.prewarm_strict)
        for application, status in results.items():
            print(f"mcp_adobe_prewarm {application}={status}", file=sys.stderr, flush=True)

    mcp = build_server(
        runtime=runtime,
        oauth_config=oauth_config,
        token_verifier=token_verifier,
        audit_sink=audit_sink,
    )
    try:
        if args.transport == "stdio":
            mcp.run(transport="stdio")
        else:
            mcp.run(
                transport="streamable-http",
                host=args.host,
                port=args.port,
                streamable_http_path=args.path,
                stateless_http=True,
                json_response=True,
            )
    finally:
        shutdown_default_runtime()


if __name__ == "__main__":
    main()
# exact-head visual-build trigger: real-panel-transport
