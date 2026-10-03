from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl


DEFAULT_SCOPE = "creative:access"
WRITE_SCOPE = "creative:write"
HIGH_RISK_SCOPE = "creative:high-risk"


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_scopes(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return (DEFAULT_SCOPE,)
    scopes = tuple(dict.fromkeys(part for part in raw.replace(",", " ").split() if part))
    if not scopes:
        raise ValueError("MCP_ADOBE_OAUTH_REQUIRED_SCOPES must contain at least one scope")
    return scopes


def _require_safe_url(value: str, *, name: str, allow_local_http: bool = True) -> None:
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.netloc:
        return
    if allow_local_http and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return
    raise ValueError(f"{name} must use https (or loopback http for local testing)")


@dataclass(frozen=True, slots=True)
class OAuthResourceConfig:
    issuer_url: str
    resource_url: str
    introspection_endpoint: str
    required_scopes: tuple[str, ...] = (DEFAULT_SCOPE,)
    client_id: str | None = None
    client_secret: str | None = None
    validate_token_resource: bool = True

    def __post_init__(self) -> None:
        _require_safe_url(self.issuer_url, name="issuer_url")
        _require_safe_url(self.resource_url, name="resource_url")
        _require_safe_url(self.introspection_endpoint, name="introspection_endpoint")
        if not self.required_scopes:
            raise ValueError("required_scopes must not be empty")
        if bool(self.client_id) != bool(self.client_secret):
            raise ValueError("OAuth introspection client_id and client_secret must be configured together")

    @classmethod
    def from_env(cls) -> "OAuthResourceConfig | None":
        names = {
            "issuer_url": "MCP_ADOBE_OAUTH_ISSUER_URL",
            "resource_url": "MCP_ADOBE_OAUTH_RESOURCE_URL",
            "introspection_endpoint": "MCP_ADOBE_OAUTH_INTROSPECTION_ENDPOINT",
        }
        values = {key: _env(env_name) for key, env_name in names.items()}
        if not any(values.values()):
            return None
        missing = [names[key] for key, value in values.items() if not value]
        if missing:
            raise ValueError("incomplete OAuth configuration; missing: " + ", ".join(sorted(missing)))

        client_id = _env("MCP_ADOBE_OAUTH_CLIENT_ID")
        client_secret = _env("MCP_ADOBE_OAUTH_CLIENT_SECRET")
        return cls(
            issuer_url=str(values["issuer_url"]),
            resource_url=str(values["resource_url"]),
            introspection_endpoint=str(values["introspection_endpoint"]),
            required_scopes=_parse_scopes(_env("MCP_ADOBE_OAUTH_REQUIRED_SCOPES")),
            client_id=client_id,
            client_secret=client_secret,
            validate_token_resource=_env("MCP_ADOBE_OAUTH_VALIDATE_RESOURCE") not in {"0", "false", "no", "off"},
        )

    def auth_settings(self) -> AuthSettings:
        return AuthSettings(
            issuer_url=AnyHttpUrl(self.issuer_url),
            resource_server_url=AnyHttpUrl(self.resource_url),
            required_scopes=list(self.required_scopes),
            validate_token_resource=self.validate_token_resource,
        )


class IntrospectionTokenVerifier(TokenVerifier):
    """RFC 7662 verifier for an external OAuth/OIDC authorization server.

    The gateway remains a resource server: it validates bearer tokens but never
    implements login, consent, authorization-code exchange, or token issuance.
    """

    def __init__(self, config: OAuthResourceConfig) -> None:
        self.config = config

    @staticmethod
    def _scopes(data: Mapping[str, Any]) -> list[str]:
        raw = data.get("scope")
        if isinstance(raw, str):
            return [part for part in raw.split() if part]
        if isinstance(raw, (list, tuple, set)):
            return [str(part) for part in raw if str(part)]
        return []

    def _resource(self, data: Mapping[str, Any]) -> str | None:
        raw = data.get("aud")
        if isinstance(raw, str):
            audiences = [raw]
        elif isinstance(raw, (list, tuple, set)):
            audiences = [str(item) for item in raw]
        else:
            audiences = []
        expected = self.config.resource_url.rstrip("/")
        for audience in audiences:
            if audience.rstrip("/") == expected:
                return audience
        return audiences[0] if audiences else None

    async def verify_token(self, token: str) -> AccessToken | None:
        import httpx2

        timeout = httpx2.Timeout(10.0, connect=5.0)
        limits = httpx2.Limits(max_connections=10, max_keepalive_connections=5)
        kwargs: dict[str, Any] = {
            "data": {"token": token},
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        }
        if self.config.client_id and self.config.client_secret:
            kwargs["auth"] = (self.config.client_id, self.config.client_secret)

        try:
            async with httpx2.AsyncClient(timeout=timeout, limits=limits, verify=True) as client:
                response = await client.post(self.config.introspection_endpoint, **kwargs)
        except Exception:
            return None

        if response.status_code != 200:
            return None
        try:
            data = response.json()
        except Exception:
            return None
        if not isinstance(data, Mapping) or not data.get("active", False):
            return None

        expires_at = data.get("exp")
        if expires_at is not None:
            try:
                expires_at = int(expires_at)
            except (TypeError, ValueError):
                return None

        return AccessToken(
            token=token,
            client_id=str(data.get("client_id") or "unknown"),
            scopes=self._scopes(data),
            expires_at=expires_at,
            resource=self._resource(data),
            subject=str(data["sub"]) if data.get("sub") is not None else None,
            claims=dict(data),
        )
