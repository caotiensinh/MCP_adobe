from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse


_EXPECTED_GATEWAY_TOOLS = {
    "creative_discover",
    "creative_read",
    "creative_write",
    "creative_authorized_write",
}
_RESOURCE_METADATA_RE = re.compile(r'resource_metadata=(?:"([^"]+)"|([^,\s]+))', re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ProbeFinding:
    status: str
    check: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"status": self.status, "check": self.check, "detail": self.detail}


def _is_loopback(hostname: str | None) -> bool:
    return hostname in {"127.0.0.1", "localhost", "::1"}


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlparse(url)
    return parsed.scheme, parsed.hostname or "", parsed.port


def validate_probe_url(url: str, *, allow_loopback_http: bool = False) -> None:
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc:
        return
    if (
        allow_loopback_http
        and parsed.scheme == "http"
        and parsed.netloc
        and _is_loopback(parsed.hostname)
    ):
        return
    raise ValueError("remote MCP URL must use https; loopback http requires --allow-loopback-http")


def extract_resource_metadata_url(www_authenticate: str) -> str | None:
    match = _RESOURCE_METADATA_RE.search(www_authenticate or "")
    if not match:
        return None
    return match.group(1) or match.group(2)


def _summary(findings: list[ProbeFinding]) -> dict[str, int]:
    return {
        "pass": sum(item.status == "PASS" for item in findings),
        "warn": sum(item.status == "WARN" for item in findings),
        "fail": sum(item.status == "FAIL" for item in findings),
    }


async def _list_tools_with_token(url: str, token: str) -> set[str]:
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(10.0, read=30.0),
    ) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(transport) as client:
            listed = await client.list_tools()
            return {tool.name for tool in listed.tools}


async def probe_remote(
    url: str,
    *,
    token: str | None = None,
    allow_loopback_http: bool = False,
) -> dict[str, Any]:
    """Probe only the remote MCP/OAuth boundary; never execute an Adobe tool."""

    validate_probe_url(url, allow_loopback_http=allow_loopback_http)
    findings: list[ProbeFinding] = []

    def add(status: str, check: str, detail: str) -> None:
        findings.append(ProbeFinding(status, check, detail))

    import httpx2

    async with httpx2.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        try:
            anonymous = await client.post(
                url,
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                headers={"Accept": "application/json, text/event-stream"},
            )
        except Exception as exc:
            add("FAIL", "anonymous_challenge", f"request failed: {type(exc).__name__}: {exc}")
            return {"url": url, "authenticated": False, "summary": _summary(findings), "findings": [x.as_dict() for x in findings]}

        if anonymous.status_code != 401:
            add(
                "FAIL",
                "anonymous_challenge",
                f"expected HTTP 401 before MCP parsing, received HTTP {anonymous.status_code}",
            )
            return {"url": url, "authenticated": False, "summary": _summary(findings), "findings": [x.as_dict() for x in findings]}
        add("PASS", "anonymous_challenge", "unauthenticated MCP request rejected with HTTP 401")

        challenge = anonymous.headers.get("www-authenticate", "")
        metadata_url = extract_resource_metadata_url(challenge)
        if not metadata_url:
            add("FAIL", "resource_metadata_pointer", "WWW-Authenticate is missing resource_metadata")
            return {"url": url, "authenticated": False, "summary": _summary(findings), "findings": [x.as_dict() for x in findings]}

        try:
            validate_probe_url(metadata_url, allow_loopback_http=allow_loopback_http)
        except ValueError as exc:
            add("FAIL", "resource_metadata_pointer", str(exc))
            return {"url": url, "authenticated": False, "summary": _summary(findings), "findings": [x.as_dict() for x in findings]}
        if _origin(metadata_url) != _origin(url):
            add("FAIL", "resource_metadata_pointer", "resource metadata URL must stay on the MCP resource origin")
            return {"url": url, "authenticated": False, "summary": _summary(findings), "findings": [x.as_dict() for x in findings]}
        add("PASS", "resource_metadata_pointer", metadata_url)

        try:
            response = await client.get(metadata_url)
        except Exception as exc:
            add("FAIL", "resource_metadata", f"request failed: {type(exc).__name__}: {exc}")
            return {"url": url, "authenticated": False, "summary": _summary(findings), "findings": [x.as_dict() for x in findings]}
        if response.status_code != 200:
            add("FAIL", "resource_metadata", f"expected HTTP 200, received HTTP {response.status_code}")
            return {"url": url, "authenticated": False, "summary": _summary(findings), "findings": [x.as_dict() for x in findings]}
        try:
            metadata = response.json()
        except Exception as exc:
            add("FAIL", "resource_metadata", f"invalid JSON: {exc}")
            return {"url": url, "authenticated": False, "summary": _summary(findings), "findings": [x.as_dict() for x in findings]}
        if not isinstance(metadata, Mapping):
            add("FAIL", "resource_metadata", "metadata is not a JSON object")
            return {"url": url, "authenticated": False, "summary": _summary(findings), "findings": [x.as_dict() for x in findings]}
        add("PASS", "resource_metadata", "protected resource metadata returned HTTP 200")

    resource = metadata.get("resource")
    if isinstance(resource, str) and resource.rstrip("/") == url.rstrip("/"):
        add("PASS", "resource_binding", "metadata resource matches the probed MCP URL")
    else:
        add("FAIL", "resource_binding", f"metadata resource {resource!r} does not match {url!r}")

    authorization_servers = metadata.get("authorization_servers")
    if isinstance(authorization_servers, list) and authorization_servers:
        add("PASS", "authorization_servers", f"advertised {len(authorization_servers)} authorization server(s)")
    else:
        add("FAIL", "authorization_servers", "protected resource metadata has no authorization_servers")

    scopes = metadata.get("scopes_supported")
    if isinstance(scopes, list) and scopes:
        add("PASS", "scopes_supported", ", ".join(str(scope) for scope in scopes))
    else:
        add("WARN", "scopes_supported", "protected resource metadata does not advertise scopes_supported")

    authenticated = False
    tool_names: list[str] = []
    if token:
        try:
            tools = await _list_tools_with_token(url, token)
        except Exception as exc:
            add("FAIL", "authenticated_tools_list", f"MCP authentication/tools-list failed: {type(exc).__name__}: {exc}")
        else:
            authenticated = True
            tool_names = sorted(tools)
            missing = sorted(_EXPECTED_GATEWAY_TOOLS - tools)
            if missing:
                add("FAIL", "authenticated_tools_list", "missing expected gateway tools: " + ", ".join(missing))
            else:
                add("PASS", "authenticated_tools_list", f"authenticated MCP tools/list returned {len(tools)} tool(s)")
    else:
        add("WARN", "authenticated_tools_list", "no probe bearer token supplied; authenticated MCP tools/list was not attempted")

    return {
        "url": url,
        "authenticated": authenticated,
        "tool_names": tool_names,
        "summary": _summary(findings),
        "findings": [item.as_dict() for item in findings],
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely probe a deployed MCP Adobe HTTPS/OAuth boundary without executing Adobe tools."
    )
    parser.add_argument("--url", required=True, help="Public MCP URL, for example https://creative.example.com/mcp")
    parser.add_argument(
        "--token-env",
        default="MCP_ADOBE_PROBE_TOKEN",
        help="Environment variable containing an optional bearer token; the token is never printed",
    )
    parser.add_argument("--require-token", action="store_true", help="Fail if the token environment variable is empty")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--allow-loopback-http",
        action="store_true",
        help="Allow http://127.0.0.1/localhost only for local verification",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    token = os.environ.get(args.token_env, "").strip() or None
    if args.require_token and token is None:
        print(f"FAIL probe_token: environment variable {args.token_env} is empty", file=sys.stderr)
        return 2
    try:
        result = asyncio.run(
            probe_remote(
                args.url,
                token=token,
                allow_loopback_http=args.allow_loopback_http,
            )
        )
    except ValueError as exc:
        print(f"FAIL probe_url: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for finding in result["findings"]:
            print(f"[{finding['status']}] {finding['check']}: {finding['detail']}")
        summary = result["summary"]
        print(f"SUMMARY pass={summary['pass']} warn={summary['warn']} fail={summary['fail']}")

    return 1 if result["summary"]["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
