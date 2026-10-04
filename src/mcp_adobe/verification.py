from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    path: str | None
    existed_before: bool = False
    size_before: int | None = None
    mtime_ns_before: int | None = None


def capture_file_snapshot(arguments: Mapping[str, Any]) -> FileSnapshot:
    raw_path = arguments.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return FileSnapshot(path=None)

    path = Path(raw_path).expanduser()
    try:
        stat = path.stat()
    except FileNotFoundError:
        return FileSnapshot(path=str(path), existed_before=False)

    if not path.is_file():
        return FileSnapshot(path=str(path), existed_before=True)
    return FileSnapshot(
        path=str(path),
        existed_before=True,
        size_before=stat.st_size,
        mtime_ns_before=stat.st_mtime_ns,
    )


def evaluate_file_snapshot(snapshot: FileSnapshot) -> tuple[str, dict[str, Any]]:
    if snapshot.path is None:
        return (
            "accepted_unverified",
            {
                "status": "unverified",
                "kind": "filesystem",
                "reason": "no-output-path",
            },
        )

    path = Path(snapshot.path)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return (
            "accepted_unverified",
            {
                "status": "unverified",
                "kind": "filesystem",
                "path": snapshot.path,
                "reason": "output-file-not-observed",
            },
        )

    if not path.is_file():
        return (
            "accepted_unverified",
            {
                "status": "unverified",
                "kind": "filesystem",
                "path": snapshot.path,
                "reason": "output-path-is-not-a-file",
            },
        )

    if not snapshot.existed_before:
        return (
            "verified",
            {
                "status": "verified",
                "kind": "filesystem",
                "path": snapshot.path,
                "evidence": "file-created",
                "bytes": stat.st_size,
            },
        )

    changed = (
        snapshot.size_before != stat.st_size
        or snapshot.mtime_ns_before != stat.st_mtime_ns
    )
    if changed:
        return (
            "verified",
            {
                "status": "verified",
                "kind": "filesystem",
                "path": snapshot.path,
                "evidence": "file-changed",
                "bytes": stat.st_size,
            },
        )

    return (
        "accepted_unverified",
        {
            "status": "unverified",
            "kind": "filesystem",
            "path": snapshot.path,
            "reason": "preexisting-file-unchanged",
        },
    )


def unverified_mutation(reason: str = "no-deterministic-postcondition") -> tuple[str, dict[str, Any]]:
    return (
        "accepted_unverified",
        {
            "status": "unverified",
            "reason": reason,
        },
    )


def pending_user_approval(operation_id: Any = None) -> tuple[str, dict[str, Any]]:
    payload: dict[str, Any] = {
        "status": "pending_user_approval",
        "reason": "adobe-xd-requires-explicit-panel-approval",
    }
    if operation_id is not None:
        payload["operation_id"] = operation_id
    return "pending_user_approval", payload
