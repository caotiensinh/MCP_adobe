from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client


_EXPECTED_TOOLS = {
    "creative_discover",
    "creative_read",
    "creative_write",
    "creative_authorized_write",
}
_OAUTH_ENV = {
    "MCP_ADOBE_OAUTH_ISSUER_URL",
    "MCP_ADOBE_OAUTH_RESOURCE_URL",
    "MCP_ADOBE_OAUTH_INTROSPECTION_ENDPOINT",
    "MCP_ADOBE_OAUTH_REQUIRED_SCOPES",
    "MCP_ADOBE_OAUTH_CLIENT_ID",
    "MCP_ADOBE_OAUTH_CLIENT_SECRET",
    "MCP_ADOBE_OAUTH_VALIDATE_RESOURCE",
}


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    for name in _OAUTH_ENV:
        env.pop(name, None)
    return env


async def _list_stdio_tools() -> set[str]:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_adobe.server", "--transport", "stdio"],
        env=_clean_env(),
    )
    async with Client(server) as client:
        listed = await client.list_tools()
        return {tool.name for tool in listed.tools}


async def _list_http_tools(url: str) -> set[str]:
    async with Client(url) as client:
        listed = await client.list_tools()
        return {tool.name for tool in listed.tools}


async def _list_http_tools_with_token(url: str, token: str) -> set[str]:
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(10.0, read=30.0),
    ) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(transport) as client:
            listed = await client.list_tools()
            return {tool.name for tool in listed.tools}


async def _get_json(url: str) -> tuple[int, dict[str, object], dict[str, str]]:
    async with httpx2.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        payload = response.json() if response.content else {}
        return response.status_code, payload, dict(response.headers)


async def _post_unauthenticated(url: str) -> tuple[int, dict[str, str]]:
    async with httpx2.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={"Accept": "application/json, text/event-stream"},
        )
        return response.status_code, dict(response.headers)


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_tcp(port: int, process: subprocess.Popen[str], timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=2)
            raise AssertionError(
                f"MCP HTTP server exited early rc={process.returncode}\nstdout={stdout}\nstderr={stderr}"
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"MCP HTTP server did not listen on port {port}: {last_error}")


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()


def _start_introspection_server(resource_url: str) -> tuple[ThreadingHTTPServer, Thread]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            token = parse_qs(body).get("token", [""])[0]
            payload = {
                "active": token == "good-token",
                "client_id": "chatgpt-test-client",
                "scope": "creative:access offline_access",
                "aud": resource_url,
                "sub": "test-user",
                "exp": 1900000000,
            }
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


class McpServerTransportTests(unittest.TestCase):
    def test_stdio_cli_lists_gateway_tools(self) -> None:
        tools = asyncio.run(_list_stdio_tools())
        self.assertEqual(tools, _EXPECTED_TOOLS)

    def test_streamable_http_cli_lists_gateway_tools(self) -> None:
        port = _free_loopback_port()
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "mcp_adobe.server",
                "--transport",
                "streamable-http",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--path",
                "/mcp",
            ],
            env=_clean_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            _wait_for_tcp(port, process)
            tools = asyncio.run(_list_http_tools(f"http://127.0.0.1:{port}/mcp"))
            self.assertEqual(tools, _EXPECTED_TOOLS)
        finally:
            _stop_process(process)

    def test_non_loopback_http_refuses_to_start_without_oauth(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "mcp_adobe.server",
                "--transport",
                "streamable-http",
                "--host",
                "0.0.0.0",
                "--port",
                str(_free_loopback_port()),
                "--allow-non-loopback",
            ],
            env=_clean_env(),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn(
            "Refusing unauthenticated non-loopback MCP HTTP",
            completed.stdout + completed.stderr,
        )

    def test_oauth_http_publishes_metadata_rejects_anonymous_and_accepts_bearer(self) -> None:
        port = _free_loopback_port()
        resource_url = f"http://127.0.0.1:{port}/mcp"
        introspection, thread = _start_introspection_server(resource_url)
        introspection_port = int(introspection.server_address[1])
        env = _clean_env()
        env.update(
            {
                "MCP_ADOBE_OAUTH_ISSUER_URL": f"http://127.0.0.1:{introspection_port}",
                "MCP_ADOBE_OAUTH_RESOURCE_URL": resource_url,
                "MCP_ADOBE_OAUTH_INTROSPECTION_ENDPOINT": f"http://127.0.0.1:{introspection_port}/introspect",
                "MCP_ADOBE_OAUTH_REQUIRED_SCOPES": "creative:access",
            }
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "mcp_adobe.server",
                "--transport",
                "streamable-http",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--path",
                "/mcp",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            _wait_for_tcp(port, process)
            status, metadata, _ = asyncio.run(
                _get_json(f"http://127.0.0.1:{port}/.well-known/oauth-protected-resource/mcp")
            )
            self.assertEqual(status, 200)
            self.assertEqual(metadata["resource"], resource_url)
            self.assertEqual(metadata["scopes_supported"], ["creative:access"])

            status, headers = asyncio.run(_post_unauthenticated(resource_url))
            self.assertEqual(status, 401)
            self.assertIn("resource_metadata=", headers.get("www-authenticate", ""))

            tools = asyncio.run(_list_http_tools_with_token(resource_url, "good-token"))
            self.assertEqual(tools, _EXPECTED_TOOLS)
        finally:
            _stop_process(process)
            introspection.shutdown()
            introspection.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
