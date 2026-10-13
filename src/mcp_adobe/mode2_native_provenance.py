"""Read-only filesystem provenance for an isolated Adobe XD native test copy.

No Adobe host claims are made here. A separate trusted XD host must attest
the active document path and Undo capability before editing.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_native_copy_files(
    *,
    origin_path: str,
    copy_path: str,
    allowed_test_directory: str,
    expected_sha256: str,
) -> dict[str, Any]:
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64 or any(
        char not in "0123456789abcdefABCDEF" for char in expected_sha256
    ):
        raise ValueError("invalid expected native SHA-256")
    if not all(isinstance(v, str) and v for v in (origin_path, copy_path, allowed_test_directory)):
        raise ValueError("absolute origin, copy and test directory required")
    origin, duplicate, test_dir = map(Path, (origin_path, copy_path, allowed_test_directory))
    if not all(p.is_absolute() for p in (origin, duplicate, test_dir)):
        raise ValueError("native paths must be absolute")
    if origin.suffix.lower() != ".xd" or duplicate.suffix.lower() != ".xd":
        raise ValueError("native file must be .xd")
    if any(p.is_symlink() for p in (origin, duplicate, test_dir)):
        raise ValueError("symlinks are not trusted for native provenance")
    root = test_dir.resolve(strict=True)
    source = origin.resolve(strict=True)
    destination = duplicate.resolve(strict=True)
    if not root.is_dir() or destination.parent != root:
        raise ValueError("native copy outside dedicated test directory")
    if source == destination or source.parent == root:
        raise ValueError("original and test copy are not isolated")
    if not source.is_file() or not destination.is_file():
        raise ValueError("missing native file")
    source_stat, copy_stat = source.stat(), destination.stat()
    if source_stat.st_size == 0 or source_stat.st_size != copy_stat.st_size:
        raise ValueError("native copy size mismatch")
    source_sha = _sha256(source)
    copy_sha = _sha256(destination)
    if source_sha.lower() != expected_sha256.lower() or copy_sha.lower() != expected_sha256.lower():
        raise ValueError("native SHA-256 mismatch")
    if source.stat() != source_stat or destination.stat() != copy_stat:
        raise ValueError("native file changed during verification")
    return {
        "verified": True,
        "origin_path": str(source),
        "copy_path": str(destination),
        "native_sha256": copy_sha,
        "copy_bytes": copy_stat.st_size,
        "origin_unchanged": True,
        "host_active_document_verified": False,
        "undo_capability_verified": False,
        "live_mutation_authorized": False,
    }
