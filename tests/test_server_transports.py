from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
import unittest

from mcp import Client, StdioServerParameters


_EXPECTED_TOOLS = {
    "creative_discover",
    "creative_read",
    "creative_write",
    "creative_authorized_write",
}


async def _list_stdio_tools() -> set[str]:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_adobe.server", "--transport", "stdio"],
        env=dict(os.environ),
    )
    async with Client(server) as client:
        listed = await client.list_tools()
        return {tool.name for tool in listed.tools}


async def _list_http_tools(url: str) -> set[str]:
    async with Client(url) as client:
        listed = await client.list_tools()
        return {tool.name for tool in listed.tools}


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
            env=dict(os.environ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            _wait_for_tcp(port, process)
            tools = asyncio.run(_list_http_tools(f"http://127.0.0.1:{port}/mcp"))
            self.assertEqual(tools, _EXPECTED_TOOLS)
        finally:
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


if __name__ == "__main__":
    unittest.main()
