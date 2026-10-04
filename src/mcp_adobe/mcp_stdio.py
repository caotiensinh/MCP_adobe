from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from threading import Event, Lock, Thread
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SubprocessMcpConfig:
    """How to launch one local stdio MCP server."""

    command: str
    args: tuple[str, ...]
    env: Mapping[str, str] = field(default_factory=dict)
    startup_timeout_seconds: float = 30.0
    call_timeout_seconds: float = 120.0


class UpstreamToolError(RuntimeError):
    """The downstream MCP server returned an MCP tool error."""


class McpSubprocessToolClient:
    """Persistent synchronous facade over the official MCP Python SDK Client.

    JSON-RPC framing, initialize, tools/list, stdio process lifecycle and MCP
    protocol handling are delegated to the official `mcp` package. This class
    only bridges that async client to the gateway's synchronous adapter contract.
    """

    def __init__(self, config: SubprocessMcpConfig) -> None:
        self.config = config
        self._thread: Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: Any = None
        self._stop_async: asyncio.Event | None = None
        self._ready = Event()
        self._lock = Lock()
        self._startup_error: BaseException | None = None
        self._connected = False
        self._tool_names: frozenset[str] = frozenset()

    @property
    def connected(self) -> bool:
        try:
            self.start()
        except BaseException:
            return False
        return self._connected

    @property
    def tool_names(self) -> frozenset[str]:
        self.start()
        return self._tool_names

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                if self._ready.wait(self.config.startup_timeout_seconds):
                    if self._startup_error:
                        raise RuntimeError("MCP subprocess failed to start") from self._startup_error
                    return
                raise TimeoutError("timed out waiting for MCP subprocess startup")

            self._ready.clear()
            self._startup_error = None
            self._connected = False
            self._thread = Thread(target=self._thread_main, name="mcp-stdio-client", daemon=True)
            self._thread.start()

        if not self._ready.wait(self.config.startup_timeout_seconds):
            raise TimeoutError("timed out waiting for MCP subprocess startup")
        if self._startup_error:
            raise RuntimeError("MCP subprocess failed to start") from self._startup_error

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._serve())
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
        finally:
            self._connected = False

    async def _serve(self) -> None:
        from mcp import Client, StdioServerParameters

        self._loop = asyncio.get_running_loop()
        server = StdioServerParameters(
            command=self.config.command,
            args=list(self.config.args),
            env=dict(self.config.env),
        )
        self._stop_async = asyncio.Event()

        async with Client(server) as client:
            self._client = client
            listed = await client.list_tools()
            self._tool_names = frozenset(tool.name for tool in listed.tools)
            self._connected = True
            self._ready.set()
            await self._stop_async.wait()

    @staticmethod
    def _normalize_result(result: Any) -> Mapping[str, Any]:
        is_error = bool(getattr(result, "is_error", False))
        structured = getattr(result, "structured_content", None)
        if is_error:
            text = McpSubprocessToolClient._text_content(result)
            raise UpstreamToolError(text or "upstream MCP tool returned an error")
        if isinstance(structured, Mapping):
            return dict(structured)

        text = McpSubprocessToolClient._text_content(result)
        if text:
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
            if isinstance(decoded, Mapping):
                return dict(decoded)
            return {"value": decoded}
        return {}

    @staticmethod
    def _text_content(result: Any) -> str:
        parts: list[str] = []
        for item in getattr(result, "content", ()) or ():
            if getattr(item, "type", None) == "text":
                text = getattr(item, "text", None)
                if text:
                    parts.append(str(text))
        return "\n".join(parts)

    async def _call_tool_async(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        if self._client is None:
            raise RuntimeError("MCP client is not connected")
        result = await self._client.call_tool(name, dict(arguments))
        return self._normalize_result(result)

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self.start()
        if name not in self._tool_names:
            raise LookupError(f"upstream MCP tool not found: {name}")
        if self._loop is None:
            raise RuntimeError("MCP event loop is unavailable")

        future = asyncio.run_coroutine_threadsafe(self._call_tool_async(name, arguments), self._loop)
        try:
            return future.result(timeout=self.config.call_timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"upstream MCP tool timed out: {name}") from exc

    def close(self) -> None:
        loop = self._loop
        stop = self._stop_async
        thread = self._thread
        if loop is not None and stop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(stop.set)
        if thread is not None:
            thread.join(timeout=5.0)
        self._thread = None
        self._loop = None
        self._client = None
        self._stop_async = None
        self._connected = False

    def __enter__(self) -> "McpSubprocessToolClient":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


def _running_photoshop_path() -> str | None:
    """Resolve a running Photoshop executable without assuming its install directory."""
    if sys.platform != "win32":
        return None
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "$p=Get-Process -Name Photoshop -ErrorAction SilentlyContinue | Where-Object {$_.Path} | Select-Object -First 1; if($p){$p.Path}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    path = completed.stdout.strip().splitlines()
    return path[0].strip() if path and path[0].strip() else None


def photoshop_stdio_config() -> SubprocessMcpConfig:
    """Pinned launcher matching the audited Photoshop snapshot/package release.

    The pinned upstream Windows detector checks PHOTOSHOP_PATH first. Preserve an
    explicit override, otherwise derive it from the running Photoshop process so
    custom/portable installs work without patching the upstream package.
    """
    env = {
        "LOG_LEVEL": "0",
        "PSMCP_FEEDBACK": "0",
        "PSMCP_UPDATE_CHECK": "0",
    }
    photoshop_path = os.environ.get("PHOTOSHOP_PATH", "").strip() or _running_photoshop_path()
    if photoshop_path:
        env["PHOTOSHOP_PATH"] = photoshop_path

    return SubprocessMcpConfig(
        command="npx",
        args=("-y", "@alisaitteke/photoshop-mcp@1.7.32"),
        env=env,
        call_timeout_seconds=180.0,
    )


def illustrator_stdio_config() -> SubprocessMcpConfig:
    """Pinned launcher matching the audited Illustrator snapshot/package release."""
    return SubprocessMcpConfig(
        command="npx",
        args=("-y", "illustrator-mcp-server@1.10.3"),
        call_timeout_seconds=180.0,
    )
