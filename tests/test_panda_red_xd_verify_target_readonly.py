"""Live-gate CLI behavior under a controlled fake MCP transport (not Adobe E2E)."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
import importlib.util
from pathlib import Path

_cli_path = Path(__file__).resolve().parents[1] / "scripts" / "panda_red_xd_verify_target_readonly.py"
_spec = importlib.util.spec_from_file_location("panda_red_xd_verify_target_readonly", _cli_path)
assert _spec is not None and _spec.loader is not None
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)
from mcp_adobe.xd_red_poster_guard import XdRedGuardError

NEW_DOC = "new-red-doc-pinned-id"


def sample():
    return {
        "creative.health": {"bridge": "connected", "pending_count": 0},
        "creative.document.info": {"id": NEW_DOC},
        "creative.scenegraph.list": {
            "document_id": NEW_DOC, "complete": True,
            "nodes": [{
                "id": "native-red-artboard", "type": "Artboard",
                "bounds": {"left": 0, "top": 0, "right": 880, "bottom": 700},
                "children": [],
            }],
        },
    }


def setup(monkeypatch, tmp_path, snapshots):
    class FakeClient:
        def __init__(self, url):
            assert url == "http://127.0.0.1:8787/mcp"
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def call_tool(self, name, body):
            assert name == "creative_read" and body["application"] == "xd"
            return SimpleNamespace(is_error=False, structured_content={
                "ok": True, "result": snapshots[body["capability"]]
            })
    monkeypatch.setattr(cli, "Client", FakeClient)
    monkeypatch.setattr(cli, "_context", lambda: tmp_path)
    monkeypatch.setattr(cli, "verify_native_files",
                        lambda root: {"native_checkpoint_verified": True, "hashes_match": True})
    return tmp_path / "receipt.json"


def test_discovery_records_uuid_but_never_authorizes_write(monkeypatch, tmp_path):
    report = setup(monkeypatch, tmp_path, sample())
    asyncio.run(cli.inspect(expected_document_id=None, report=report))
    proof = json.loads(report.read_text(encoding="utf-8"))
    assert proof["outcome"] == "DISCOVERED_NOT_AUTHORIZED_FOR_WRITE"
    assert proof["observed_document_id"] == NEW_DOC
    assert proof["ready_for_first_write"] is False
    assert proof["new_native_writes"] == 0
    assert [s["capability"] for s in proof["stages"]] == list(cli.CAPABILITIES)


def test_exact_pinned_uuid_reaches_read_only_first_write_gate(monkeypatch, tmp_path):
    report = setup(monkeypatch, tmp_path, sample())
    asyncio.run(cli.inspect(expected_document_id=NEW_DOC, report=report))
    proof = json.loads(report.read_text(encoding="utf-8"))
    assert proof["outcome"] == "READ_ONLY_PREFLIGHT_PASS"
    assert proof["ready_for_first_write"] is True
    assert proof["binding"]["artboard_id"] == "native-red-artboard"
    assert proof["new_native_writes"] == proof["bridge_gui_actions"] == 0


@pytest.mark.parametrize("case", ["wrong_document", "old_document", "queue_busy", "incomplete", "wrong_artboard"])
def test_unsafe_runtime_fails_with_durable_diagnostics(monkeypatch, tmp_path, case):
    payload = sample()
    if case == "wrong_document":
        payload["creative.document.info"]["id"] = "some-other-open-blank"
        payload["creative.scenegraph.list"]["document_id"] = "some-other-open-blank"
    elif case == "old_document":
        from mcp_adobe.xd_red_poster_guard import OLD_DOCUMENT_ID
        payload["creative.document.info"]["id"] = OLD_DOCUMENT_ID
        payload["creative.scenegraph.list"]["document_id"] = OLD_DOCUMENT_ID
    elif case == "queue_busy":
        payload["creative.health"]["pending_count"] = 1
    elif case == "incomplete":
        payload["creative.scenegraph.list"]["complete"] = False
    elif case == "wrong_artboard":
        payload["creative.scenegraph.list"]["nodes"][0]["bounds"]["right"] = 1024
    report = setup(monkeypatch, tmp_path, payload)
    with pytest.raises(XdRedGuardError):
        asyncio.run(cli.inspect(expected_document_id=NEW_DOC, report=report))
    proof = json.loads(report.read_text(encoding="utf-8"))
    assert proof["outcome"] == "BLOCKED"
    assert proof["ready_for_first_write"] is False
    assert proof["new_native_writes"] == proof["bridge_gui_actions"] == 0


def test_native_checksum_change_blocks_even_read_only_discovery(monkeypatch, tmp_path):
    report = setup(monkeypatch, tmp_path, sample())
    calls = [0]
    def proof(root):
        calls[0] += 1
        return {"hashes_match": True, "revision": calls[0]}
    monkeypatch.setattr(cli, "verify_native_files", proof)
    with pytest.raises(XdRedGuardError, match="NATIVE_CHANGED_DURING_PREFLIGHT"):
        asyncio.run(cli.inspect(expected_document_id=None, report=report))
    assert json.loads(report.read_text(encoding="utf-8"))["outcome"] == "BLOCKED"
