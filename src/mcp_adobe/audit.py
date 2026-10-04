from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Protocol, TextIO

from mcp.server.auth.provider import AccessToken


DEFAULT_AUDIT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_AUDIT_BACKUP_COUNT = 5


@dataclass(frozen=True, slots=True)
class SecurityAuditEvent:
    tool: str
    decision: str
    application: str | None = None
    capability: str | None = None
    reason: str | None = None
    operation_id: str | None = None
    outcome: str | None = None


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
        "operation_id": event.operation_id,
        "outcome": event.outcome,
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


def _json_line(event: SecurityAuditEvent, access_token: AccessToken | None) -> str:
    return json.dumps(
        security_audit_payload(event, access_token),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _positive_env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


class RotatingJsonLineFileSecurityAuditSink:
    """Thread-safe JSONL file sink with bounded size and numbered backups."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        max_bytes: int = DEFAULT_AUDIT_MAX_BYTES,
        backup_count: int = DEFAULT_AUDIT_BACKUP_COUNT,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        if backup_count <= 0:
            raise ValueError("backup_count must be a positive integer")
        self._path = Path(path).expanduser()
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._lock = Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def _backup_path(self, index: int) -> Path:
        return self._path.with_name(f"{self._path.name}.{index}")

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        try:
            current_size = self._path.stat().st_size
        except FileNotFoundError:
            return
        if current_size == 0 or current_size + incoming_bytes <= self._max_bytes:
            return

        oldest = self._backup_path(self._backup_count)
        if oldest.exists():
            oldest.unlink()

        for index in range(self._backup_count - 1, 0, -1):
            source = self._backup_path(index)
            if not source.exists():
                continue
            target = self._backup_path(index + 1)
            if target.exists():
                target.unlink()
            source.replace(target)

        first_backup = self._backup_path(1)
        if first_backup.exists():
            first_backup.unlink()
        self._path.replace(first_backup)

    def emit(self, event: SecurityAuditEvent, access_token: AccessToken | None) -> None:
        line = _json_line(event, access_token) + "\n"
        encoded_size = len(line.encode("utf-8"))
        with self._lock:
            self._rotate_if_needed(encoded_size)
            with self._path.open("a", encoding="utf-8", newline="") as stream:
                stream.write(line)
                stream.flush()


class JsonLineSecurityAuditSink:
    """Thread-safe JSONL security audit sink.

    By default events are written to stderr. When MCP_ADOBE_AUDIT_PATH is set,
    the sink transparently switches to a bounded rotating JSONL file. Supplying
    an explicit stream always wins over environment configuration, which keeps
    tests and embedded callers deterministic.
    """

    def __init__(self, stream: TextIO | None = None) -> None:
        self._delegate: RotatingJsonLineFileSecurityAuditSink | None = None
        self._lock = Lock()

        if stream is not None:
            self._stream = stream
            return

        audit_path = os.environ.get("MCP_ADOBE_AUDIT_PATH", "").strip()
        if audit_path:
            self._stream = None
            self._delegate = RotatingJsonLineFileSecurityAuditSink(
                audit_path,
                max_bytes=_positive_env_int(
                    "MCP_ADOBE_AUDIT_MAX_BYTES",
                    DEFAULT_AUDIT_MAX_BYTES,
                ),
                backup_count=_positive_env_int(
                    "MCP_ADOBE_AUDIT_BACKUP_COUNT",
                    DEFAULT_AUDIT_BACKUP_COUNT,
                ),
            )
            return

        self._stream = sys.stderr

    def emit(self, event: SecurityAuditEvent, access_token: AccessToken | None) -> None:
        if self._delegate is not None:
            self._delegate.emit(event, access_token)
            return

        line = _json_line(event, access_token)
        assert self._stream is not None
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()
