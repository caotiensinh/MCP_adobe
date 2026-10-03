from __future__ import annotations

import json
from dataclasses import dataclass
from threading import Event, Lock, Thread
from typing import Any, Mapping
from uuid import uuid4


@dataclass(slots=True)
class _PendingCall:
    event: Event
    result: Mapping[str, Any] | None = None
    error: str | None = None


class XdWebSocketBridgeClient:
    """Synchronous gateway client for an Adobe XD UXP plugin connection.

    The Python process listens only on loopback. The XD plugin initiates the
    WebSocket connection because UXP exposes WebSocket client APIs. Requests are
    correlated by UUID and the synchronous gateway call blocks until the plugin
    responds or the configured timeout expires.
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        startup_timeout_seconds: float = 5.0,
        call_timeout_seconds: float = 30.0,
    ) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Adobe XD bridge must bind to loopback only")
        if not (1 <= port <= 65535):
            raise ValueError("port must be between 1 and 65535")

        self.host = host
        self.port = port
        self.startup_timeout_seconds = startup_timeout_seconds
        self.call_timeout_seconds = call_timeout_seconds

        self._thread: Thread | None = None
        self._server: Any = None
        self._connection: Any = None
        self._server_ready = Event()
        self._plugin_ready = Event()
        self._startup_error: BaseException | None = None
        self._lock = Lock()
        self._send_lock = Lock()
        self._pending: dict[str, _PendingCall] = {}
        self._plugin_info: dict[str, Any] = {}

    @property
    def connected(self) -> bool:
        try:
            self.start()
        except BaseException:
            return False
        return self._plugin_ready.is_set() and self._connection is not None

    @property
    def plugin_info(self) -> Mapping[str, Any]:
        return dict(self._plugin_info)

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                if self._startup_error:
                    raise RuntimeError("Adobe XD bridge failed to start") from self._startup_error
                return

            self._server_ready.clear()
            self._startup_error = None
            self._thread = Thread(target=self._thread_main, name="xd-uxp-bridge", daemon=True)
            self._thread.start()

        if not self._server_ready.wait(self.startup_timeout_seconds):
            raise TimeoutError("timed out starting Adobe XD bridge server")
        if self._startup_error:
            raise RuntimeError("Adobe XD bridge failed to start") from self._startup_error

    def _thread_main(self) -> None:
        try:
            from websockets.sync.server import serve

            with serve(self._handle_connection, self.host, self.port) as server:
                self._server = server
                self._server_ready.set()
                server.serve_forever()
        except BaseException as exc:
            self._startup_error = exc
            self._server_ready.set()
        finally:
            self._server = None
            self._disconnect_current("bridge server stopped")

    def _handle_connection(self, websocket: Any) -> None:
        try:
            hello_raw = websocket.recv(timeout=self.call_timeout_seconds)
            hello = self._decode_message(hello_raw)
            if hello.get("type") != "hello" or hello.get("application") != "xd":
                websocket.close(code=1008, reason="Adobe XD hello required")
                return

            with self._lock:
                previous = self._connection
                self._connection = websocket
                self._plugin_info = dict(hello)
                self._plugin_ready.set()
            if previous is not None and previous is not websocket:
                try:
                    previous.close(code=1012, reason="new Adobe XD bridge connection")
                except Exception:
                    pass

            for raw in websocket:
                message = self._decode_message(raw)
                request_id = message.get("id")
                if not isinstance(request_id, str):
                    continue
                with self._lock:
                    pending = self._pending.get(request_id)
                if pending is None:
                    continue

                if message.get("ok") is True:
                    result = message.get("result")
                    pending.result = dict(result) if isinstance(result, Mapping) else {"value": result}
                else:
                    pending.error = str(message.get("error") or "Adobe XD bridge request failed")
                pending.event.set()
        except Exception:
            pass
        finally:
            with self._lock:
                is_current = self._connection is websocket
            if is_current:
                self._disconnect_current("Adobe XD plugin disconnected")

    @staticmethod
    def _decode_message(raw: Any) -> dict[str, Any]:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            raise ValueError("bridge message must be text")
        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            raise ValueError("bridge message must be a JSON object")
        return decoded

    def _disconnect_current(self, reason: str) -> None:
        with self._lock:
            self._connection = None
            self._plugin_info = {}
            self._plugin_ready.clear()
            pending = list(self._pending.values())
        for item in pending:
            if item.error is None and item.result is None:
                item.error = reason
            item.event.set()

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self.start()
        with self._lock:
            websocket = self._connection
        if websocket is None or not self._plugin_ready.is_set():
            raise RuntimeError(
                f"Adobe XD plugin is not connected to {self.url}; open the MCP Adobe Bridge panel in XD"
            )

        request_id = uuid4().hex
        pending = _PendingCall(event=Event())
        with self._lock:
            self._pending[request_id] = pending

        payload = json.dumps(
            {
                "id": request_id,
                "method": name,
                "params": dict(arguments),
            },
            separators=(",", ":"),
        )

        try:
            with self._send_lock:
                websocket.send(payload)
            if not pending.event.wait(self.call_timeout_seconds):
                raise TimeoutError(f"Adobe XD bridge call timed out: {name}")
            if pending.error:
                raise RuntimeError(pending.error)
            return pending.result or {}
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def close(self) -> None:
        with self._lock:
            websocket = self._connection
            server = self._server
            thread = self._thread
        if websocket is not None:
            try:
                websocket.close(code=1001, reason="gateway shutdown")
            except Exception:
                pass
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
        if thread is not None:
            thread.join(timeout=5.0)
        self._thread = None
        self._server = None
        self._disconnect_current("gateway shutdown")

    def __enter__(self) -> "XdWebSocketBridgeClient":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()
