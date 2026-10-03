from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Protocol, TextIO

from mcp.server.auth.provider import AccessToken


@dataclass(frozen=True, slots=True)
class SecurityAuditEvent:
    tool: str
    decision: str
    application: str | None = None
    capability: str | None = None
    reason: str | None = None


class SecurityAuditSink(Protocol):
    def emit(self, event: SecurityAuditEvent, access_token: AccessToken | None) -> None:
        ...


class NullSecurityAuditSink:
    def emit(self, event: SecurityAuditEvent, access_token: AccessToken | None) -> None:
        return


def security_audit_payload(
    event: SecurityAuditEvent,
    access_token: AccessToken | None,
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build a deliberately redacted audit payload.

    The bearer token and tool arguments are intentionally never accepted by this
    function, so they cannot be serialized accidentally.
    """

    payload: dict[str, Any] = {
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": "mcp_adobe.security",
        "tool": event.tool,
        "decision": event.decision,
        "application": event.application,
        "capability": event.capability,
        "reason": event.reason,
    }
    if access_token is None:
        payload["principal"] = {
            "auth_mode": "local-or-unavailable",
            "subject": None,
            "client_id": None,
            "scopes": [],
        }
    else:
        payload["principal"] = {
            "auth_mode": "oauth",
            "subject": access_token.subject,
            "client_id": access_token.client_id,
            "scopes": sorted(set(access_token.scopes or [])),
        }
    return payload


class JsonLineSecurityAuditSink:
    """Thread-safe JSONL security audit sink, defaulting to stderr."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stderr
        self._lock = Lock()

    def emit(self, event: SecurityAuditEvent, access_token: AccessToken | None) -> None:
        line = json.dumps(
            security_audit_payload(event, access_token),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()
