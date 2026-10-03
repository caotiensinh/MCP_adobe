from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse, urlunparse

from .auth import OAuthResourceConfig


@dataclass(frozen=True, slots=True)
class PreflightFinding:
    status: str
    check: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"status": self.status, "check": self.check, "detail": self.detail}


def discovery_urls(issuer_url: str) -> tuple[str, ...]:
    """Return OIDC and RFC 8414 discovery URLs for an issuer, including path issuers."""
    parsed = urlparse(issuer_url)
    issuer = issuer_url.rstrip("/")
    oidc = issuer + "/.well-known/openid-configuration"
    issuer_path = parsed.path.rstrip("/")
    oauth_path = "/.well-known/oauth-authorization-server" + issuer_path
    oauth = urlunparse((parsed.scheme, parsed.netloc, oauth_path, "", "", ""))
    return tuple(dict.fromkeys((oidc, oauth)))


def _safe_endpoint(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.netloc:
        return True
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def evaluate_provider_metadata(
    config: OAuthResourceConfig,
    metadata: Mapping[str, Any],
    *,
    source_url: str,
) -> list[PreflightFinding]:
    findings: list[PreflightFinding] = []

    def add(status: str, check: str, detail: str) -> None:
        findings.append(PreflightFinding(status, check, detail))

    issuer = metadata.get("issuer")
    if issuer == config.issuer_url:
        add("PASS", "issuer", f"issuer exactly matches {config.issuer_url}")
    else:
        add("FAIL", "issuer", f"metadata issuer {issuer!r} does not exactly match {config.issuer_url!r}")

    for field in ("authorization_endpoint", "token_endpoint"):
        value = metadata.get(field)
        if _safe_endpoint(value):
            add("PASS", field, str(value))
        else:
            add("FAIL", field, f"missing or insecure {field}: {value!r}")

    pkce = metadata.get("code_challenge_methods_supported")
    if isinstance(pkce, list) and "S256" in pkce:
        add("PASS", "pkce_s256", "authorization server advertises S256")
    else:
        add("FAIL", "pkce_s256", "code_challenge_methods_supported must include S256")

    methods = metadata.get("token_endpoint_auth_methods_supported")
    supported_methods = {"none", "private_key_jwt", "client_secret_post", "client_secret_basic"}
    if isinstance(methods, list) and supported_methods.intersection(str(item) for item in methods):
        add("PASS", "token_endpoint_auth", "compatible token endpoint authentication method is advertised")
    else:
        add("FAIL", "token_endpoint_auth", "no supported token_endpoint_auth_methods_supported value is advertised")

    if metadata.get("client_id_metadata_document_supported") is True:
        add("PASS", "client_registration", "CIMD is advertised")
    elif _safe_endpoint(metadata.get("registration_endpoint")):
        add("PASS", "client_registration", "DCR registration_endpoint is advertised")
    else:
        add(
            "WARN",
            "client_registration",
            "CIMD/DCR not advertised; a predefined OAuth client may be required in ChatGPT/Codex",
        )

    scopes = metadata.get("scopes_supported")
    if isinstance(scopes, list):
        scope_set = {str(item) for item in scopes}
        missing = [scope for scope in config.required_scopes if scope not in scope_set]
        if missing:
            add("FAIL", "required_scopes", "authorization server metadata is missing: " + ", ".join(missing))
        else:
            add("PASS", "required_scopes", "all MCP Adobe required scopes are advertised")
        if "offline_access" in scope_set:
            add("PASS", "refresh_access", "offline_access is advertised for refresh-token capable sessions")
        else:
            add(
                "WARN",
                "refresh_access",
                "offline_access is not advertised; ChatGPT may require reauthentication after token expiry",
            )
    else:
        add("WARN", "required_scopes", "scopes_supported is not advertised; verify required scopes manually")
        add("WARN", "refresh_access", "cannot confirm offline_access from provider metadata")

    if metadata.get("authorization_response_iss_parameter_supported") is True:
        add("PASS", "authorization_response_iss", "issuer identification is advertised")
    else:
        add(
            "WARN",
            "authorization_response_iss",
            "issuer identification is not advertised; ChatGPT may use callback-specific OAuth client metadata",
        )

    advertised_introspection = metadata.get("introspection_endpoint")
    if advertised_introspection is None:
        add("WARN", "introspection_endpoint", "provider metadata does not advertise introspection_endpoint")
    elif advertised_introspection == config.introspection_endpoint:
        add("PASS", "introspection_endpoint", "configured introspection endpoint matches provider metadata")
    else:
        add(
            "WARN",
            "introspection_endpoint",
            f"configured introspection endpoint differs from metadata: {advertised_introspection}",
        )

    add("PASS", "metadata_source", source_url)
    return findings


async def fetch_provider_metadata(config: OAuthResourceConfig) -> tuple[dict[str, Any], str]:
    import httpx2

    timeout = httpx2.Timeout(10.0, connect=5.0)
    errors: list[str] = []
    async with httpx2.AsyncClient(timeout=timeout, verify=True) as client:
        for url in discovery_urls(config.issuer_url):
            try:
                response = await client.get(url)
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}: {exc}")
                continue
            if response.status_code != 200:
                errors.append(f"{url}: HTTP {response.status_code}")
                continue
            try:
                payload = response.json()
            except Exception as exc:
                errors.append(f"{url}: invalid JSON: {exc}")
                continue
            if isinstance(payload, Mapping):
                return dict(payload), url
            errors.append(f"{url}: metadata is not a JSON object")
    raise RuntimeError("unable to load OAuth/OIDC provider metadata; " + " | ".join(errors))


async def run_provider_preflight(config: OAuthResourceConfig) -> list[PreflightFinding]:
    try:
        metadata, source_url = await fetch_provider_metadata(config)
    except Exception as exc:
        return [PreflightFinding("FAIL", "provider_metadata", str(exc))]
    return evaluate_provider_metadata(config, metadata, source_url=source_url)


def preflight_summary(findings: list[PreflightFinding]) -> dict[str, int]:
    return {
        "pass": sum(item.status == "PASS" for item in findings),
        "warn": sum(item.status == "WARN" for item in findings),
        "fail": sum(item.status == "FAIL" for item in findings),
    }
