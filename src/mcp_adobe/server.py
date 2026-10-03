from __future__ import annotations

import argparse
import atexit
import os
from dataclasses import dataclass
from threading import Lock
from typing import Any, Mapping, Protocol

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
from .photoshop import PhotoshopAdapter
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
    ) -> None:
        security_audit.emit(
            SecurityAuditEvent(
                tool=tool,
                decision=decision,
                application=application,
                capability=capability,
                reason=reason,
            ),
            get_access_token(),
        )

    def require_oauth_profile_scope(
        scope: str,
        tool_name: str,
        *,
        application: str,
        capability: str,
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
            )
            raise PolicyError(
                f"{tool_name} is disabled for this OAuth deployment; add {scope} to "
                "MCP_ADOBE_OAUTH_REQUIRED_SCOPES and obtain a token carrying that scope"
            )

    @mcp.tool(
        title="Discover Adobe applications and capabilities",
        annotations=ToolAnnotations(
            read_only_hint=True,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    def creative_discover() -> dict[str, Any]:
        """List Adobe adapters, connection state, capability names and risk classes."""
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
        require_oauth_profile_scope(
            WRITE_SCOPE,
            "creative_write",
            application=application,
            capability=capability,
        )
        audit("creative_write", "allowed", application=application, capability=capability)
        return dict(
            current_runtime().write(
                application,
                capability,
                arguments or {},
                allow_overwrite=allow_overwrite,
            )
        )

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
        require_oauth_profile_scope(
            WRITE_SCOPE,
            "creative_authorized_write",
            application=application,
            capability=capability,
        )
        require_oauth_profile_scope(
            HIGH_RISK_SCOPE,
            "creative_authorized_write",
            application=application,
            capability=capability,
        )
        audit(
            "creative_authorized_write",
            "allowed",
            application=application,
            capability=capability,
        )
        return dict(
            current_runtime().authorized_write(
                application,
                capability,
                arguments or {},
                allow_overwrite=allow_overwrite,
                allow_destructive=allow_destructive,
                allow_native_script=allow_native_script,
                allow_external_ai=allow_external_ai,
            )
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

    mcp = build_server(
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
