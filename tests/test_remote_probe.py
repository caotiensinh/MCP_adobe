from __future__ import annotations

import asyncio
import json
import subprocess
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import AsyncMock, patch

from mcp_adobe.remote_probe import (
    extract_resource_metadata_url,
    probe_remote,
    validate_probe_url,
)


_EXPECTED_TOOLS = {
    "creative_discover",
    "creative_read",
    "creative_write",
    "creative_authorized_write",
}


def _start_resource_server(*, cross_origin_metadata: bool = False):
    state: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path != "/mcp":
                self.send_response(404)
                self.end_headers()
                return
            metadata_url = (
                "https://other.example.com/.well-known/oauth-protected-resource/mcp"
                if cross_origin_metadata
                else state["metadata_url"]
            )
            body = b'{"error":"invalid_token"}'
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "WWW-Authenticate",
                f'Bearer error="invalid_token", resource_metadata="{metadata_url}"',
            )
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path != "/.well-known/oauth-protected-resource/mcp":
                self.send_response(404)
                self.end_headers()
                return
            payload = json.dumps(
                {
                    "resource": state["resource_url"],
                    "authorization_servers": ["https://auth.example.com"],
                    "scopes_supported": ["creative:access"],
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = int(server.server_address[1])
    state["resource_url"] = f"http://127.0.0.1:{port}/mcp"
    state["metadata_url"] = f"http://127.0.0.1:{port}/.well-known/oauth-protected-resource/mcp"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, state["resource_url"]


class _FakeResponse:
    def __init__(self, status_code: int, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}


class _CrossOriginChallengeClient:
    """Deterministic client proving a cross-origin metadata URL is never fetched."""

    def __init__(self) -> None:
        self.get_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        return _FakeResponse(
            401,
            {
                "www-authenticate": (
                    'Bearer error="invalid_token", '
                    'resource_metadata="https://other.example.com/.well-known/oauth-protected-resource/mcp"'
                )
            },
        )

    async def get(self, url, **kwargs):
        self.get_calls += 1
        raise AssertionError("cross-origin resource metadata must be rejected before GET")


class RemoteProbeTests(unittest.TestCase):
    def test_extract_resource_metadata_url_handles_quoted_and_unquoted(self) -> None:
        self.assertEqual(
            extract_resource_metadata_url('Bearer resource_metadata="https://example.com/meta"'),
            "https://example.com/meta",
        )
        self.assertEqual(
            extract_resource_metadata_url("Bearer resource_metadata=https://example.com/meta"),
            "https://example.com/meta",
        )
        self.assertIsNone(extract_resource_metadata_url('Bearer error="invalid_token"'))

    def test_non_loopback_http_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "must use https"):
            validate_probe_url("http://example.com/mcp", allow_loopback_http=True)

    def test_boundary_probe_verifies_401_and_metadata_without_token(self) -> None:
        server, thread, url = _start_resource_server()
        try:
            result = asyncio.run(probe_remote(url, allow_loopback_http=True))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual(result["summary"]["fail"], 0)
        self.assertFalse(result["authenticated"])
        checks = {item["check"]: item["status"] for item in result["findings"]}
        self.assertEqual(checks["anonymous_challenge"], "PASS")
        self.assertEqual(checks["resource_metadata"], "PASS")
        self.assertEqual(checks["resource_binding"], "PASS")
        self.assertEqual(checks["authenticated_tools_list"], "WARN")

    def test_token_probe_only_lists_tools_and_checks_expected_gateway_surface(self) -> None:
        server, thread, url = _start_resource_server()
        try:
            with patch(
                "mcp_adobe.remote_probe._list_tools_with_token",
                new=AsyncMock(return_value=set(_EXPECTED_TOOLS)),
            ) as mocked:
                result = asyncio.run(
                    probe_remote(url, token="secret-token", allow_loopback_http=True)
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual(result["summary"]["fail"], 0)
        self.assertTrue(result["authenticated"])
        self.assertEqual(set(result["tool_names"]), _EXPECTED_TOOLS)
        mocked.assert_awaited_once_with(url, "secret-token")
        self.assertNotIn("secret-token", json.dumps(result))

    def test_cross_origin_resource_metadata_pointer_is_rejected_before_fetch(self) -> None:
        fake_client = _CrossOriginChallengeClient()
        with patch("httpx2.AsyncClient", return_value=fake_client):
            result = asyncio.run(
                probe_remote("http://127.0.0.1:8765/mcp", allow_loopback_http=True)
            )

        self.assertGreater(result["summary"]["fail"], 0, result)
        failures = [item for item in result["findings"] if item["status"] == "FAIL"]
        self.assertTrue(
            any(item["check"] == "resource_metadata_pointer" for item in failures),
            result,
        )
        self.assertEqual(fake_client.get_calls, 0)

    def test_installed_remote_probe_entrypoint_has_help(self) -> None:
        completed = subprocess.run(
            ["mcp-adobe-remote-probe", "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("Safely probe", completed.stdout)
        self.assertIn("--token-env", completed.stdout)


if __name__ == "__main__":
    unittest.main()
