from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import tempfile
import uuid
from pathlib import Path
from typing import Any

import websockets
from websockets.server import ServerConnection

PROTOCOL_VERSION = 2
SERVER_VERSION = "mcp-adobe-live-probe/0.1"
DEFAULT_PORT = 7897
MUTATION_TIMEOUT_SECONDS = 45.0
READ_TIMEOUT_SECONDS = 20.0


class ProbeError(RuntimeError):
    pass


class PhotoshopBridgeProbe:
    def __init__(self, *, port: int, token: str, out_dir: Path) -> None:
        self.port = port
        self.token = token
        self.out_dir = out_dir
        self.connected = asyncio.Event()
        self.done = asyncio.Event()
        self.failure: BaseException | None = None
        self.ws: ServerConnection | None = None
        self.capabilities: set[str] = set()
        self.host_version = ""

    async def handler(self, ws: ServerConnection) -> None:
        if self.ws is not None:
            await ws.close(code=4001, reason="single Photoshop panel expected")
            return
        self.ws = ws
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
            hello = json.loads(raw)
            if hello.get("type") != "hello":
                raise ProbeError(f"expected hello, got {hello!r}")
            if hello.get("protocolVersion") != PROTOCOL_VERSION:
                raise ProbeError(f"protocol mismatch: {hello.get('protocolVersion')!r}")
            if hello.get("appId") != "photoshop":
                raise ProbeError(f"unexpected appId: {hello.get('appId')!r}")
            if not secrets.compare_digest(str(hello.get("token") or ""), self.token):
                raise ProbeError("panel token mismatch")
            self.capabilities = set(hello.get("capabilities") or [])
            self.host_version = str(hello.get("hostVersion") or "")
            print(
                "PHOTOSHOP_PANEL_CONNECTED="
                + json.dumps(
                    {
                        "hostVersion": self.host_version,
                        "panelVersion": hello.get("panelVersion"),
                        "capabilityCount": len(self.capabilities),
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                ),
                flush=True,
            )
            await ws.send(
                json.dumps(
                    {
                        "type": "welcome",
                        "serverVersion": SERVER_VERSION,
                        "heartbeatIntervalMs": 15000,
                    }
                )
            )
            self.connected.set()
            await self.run_operations()
        except BaseException as exc:
            self.failure = exc
            self.connected.set()
            raise
        finally:
            self.done.set()

    def require_capability(self, name: str) -> None:
        if name not in self.capabilities:
            raise ProbeError(f"panel missing required capability: {name}")

    async def call(self, name: str, params: dict[str, Any], *, mutation: bool) -> Any:
        if self.ws is None:
            raise ProbeError("Photoshop panel is not connected")
        self.require_capability(name)
        request_id = str(uuid.uuid4())
        await self.ws.send(json.dumps({"type": "cmd", "id": request_id, "name": name, "params": params}))
        timeout = MUTATION_TIMEOUT_SECONDS if mutation else READ_TIMEOUT_SECONDS
        try:
            while True:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
                frame = json.loads(raw)
                if frame.get("type") == "pong":
                    continue
                if frame.get("type") != "result" or frame.get("id") != request_id:
                    raise ProbeError(f"unexpected frame while waiting for {name}: {frame!r}")
                if not frame.get("ok"):
                    raise ProbeError(f"{name} failed: {frame.get('error')!r}")
                return frame.get("value")
        except TimeoutError as exc:
            if mutation:
                raise ProbeError(
                    f"{name} timed out after {timeout:.0f}s; mutation outcome is UNKNOWN, inspect Photoshop before retry"
                ) from exc
            raise ProbeError(f"{name} timed out after {timeout:.0f}s") from exc

    async def run_operations(self) -> None:
        host_info = await self.call("ps.host_info", {}, mutation=False)
        print("PHOTOSHOP_HOST_INFO=" + json.dumps(host_info, ensure_ascii=True, sort_keys=True), flush=True)
        print("PHOTOSHOP_HOST_READY=PASS", flush=True)

        docs_before = await self.call("ps.list_documents", {}, mutation=False)
        print(f"PHOTOSHOP_DOCUMENTS_BEFORE={len(docs_before or [])}", flush=True)

        created = await self.call(
            "ps.create_document",
            {
                "width": 320,
                "height": 240,
                "resolution": 72,
                "mode": "rgb",
                "fill": "white",
                "name": "MCP Adobe Live Probe",
            },
            mutation=True,
        )
        if int(created.get("width", 0)) != 320 or int(created.get("height", 0)) != 240:
            raise ProbeError(f"create verification failed: {created!r}")
        print("PHOTOSHOP_CREATE_VERIFY=PASS", flush=True)

        psd_path = self.out_dir / "mcp_adobe_live_probe.psd"
        png_path = self.out_dir / "mcp_adobe_live_probe.png"
        for path in (psd_path, png_path):
            path.unlink(missing_ok=True)

        saved = await self.call("ps.save_document", {"path": str(psd_path)}, mutation=True)
        if not saved or not saved.get("saved"):
            raise ProbeError(f"save command did not confirm success: {saved!r}")
        verify_psd(psd_path)
        print(f"PHOTOSHOP_SAVE_VERIFY=PASS path={psd_path} bytes={psd_path.stat().st_size}", flush=True)

        exported = await self.call(
            "ps.export",
            {"path": str(png_path), "format": "png"},
            mutation=True,
        )
        if not exported or str(exported.get("format") or "").lower() != "png":
            raise ProbeError(f"export command did not confirm PNG: {exported!r}")
        verify_png(png_path)
        print(f"PHOTOSHOP_EXPORT_VERIFY=PASS path={png_path} bytes={png_path.stat().st_size}", flush=True)
        print("PHOTOSHOP_LIVE_WRITE_VERIFY=PASS", flush=True)


def verify_psd(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 26:
        raise ProbeError(f"PSD output missing or empty: {path}")
    with path.open("rb") as fh:
        if fh.read(4) != b"8BPS":
            raise ProbeError(f"PSD signature mismatch: {path}")


def verify_png(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 24:
        raise ProbeError(f"PNG output missing or empty: {path}")
    with path.open("rb") as fh:
        if fh.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ProbeError(f"PNG signature mismatch: {path}")


def handshake_path() -> Path:
    return Path.home() / ".brainferno-mcp-bridge" / "bridge.json"


async def async_main(port: int, out_dir: Path, startup_timeout: float) -> int:
    token = secrets.token_hex(32)
    hs_path = handshake_path()
    hs_path.parent.mkdir(parents=True, exist_ok=True)
    backup: bytes | None = hs_path.read_bytes() if hs_path.exists() else None
    payload = {
        "port": port,
        "token": token,
        "protocolVersion": PROTOCOL_VERSION,
        "pid": os.getpid(),
    }
    hs_path.write_text(json.dumps(payload), encoding="utf-8")
    print(f"PHOTOSHOP_HANDSHAKE_READY={hs_path}", flush=True)

    probe = PhotoshopBridgeProbe(port=port, token=token, out_dir=out_dir)
    server = await websockets.serve(probe.handler, "127.0.0.1", port)
    try:
        try:
            await asyncio.wait_for(probe.connected.wait(), timeout=startup_timeout)
        except TimeoutError as exc:
            raise ProbeError(
                f"Photoshop UXP panel did not connect within {startup_timeout:.0f}s; keep Photoshop open and ensure the panel is loaded"
            ) from exc
        if probe.failure is not None:
            raise probe.failure
        await probe.done.wait()
        if probe.failure is not None:
            raise probe.failure
        return 0
    finally:
        server.close()
        await server.wait_closed()
        try:
            current = json.loads(hs_path.read_text(encoding="utf-8")) if hs_path.exists() else None
        except Exception:
            current = None
        if current and current.get("pid") == os.getpid() and current.get("token") == token:
            if backup is None:
                hs_path.unlink(missing_ok=True)
            else:
                hs_path.write_bytes(backup)


def main() -> int:
    parser = argparse.ArgumentParser(description="Live Photoshop Brainferno UXP protocol-v2 probe")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--startup-timeout", type=float, default=120.0)
    parser.add_argument("--out-dir", type=Path, default=Path(tempfile.gettempdir()) / "mcp-adobe-photoshop-live")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    try:
        return asyncio.run(async_main(args.port, args.out_dir.resolve(), args.startup_timeout))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"PHOTOSHOP_LIVE_PROBE=FAIL error={exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
