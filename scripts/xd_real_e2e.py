from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from mcp_adobe import XdAdapter, XdWebSocketBridgeClient


def emit(status: str, step: str, detail: Any = None) -> None:
    payload: dict[str, Any] = {"status": status, "step": step}
    if detail is not None:
        payload["detail"] = detail
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def wait_connected(client: XdWebSocketBridgeClient, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.connected:
            emit("PASS", "xd_bridge_connect", dict(client.plugin_info))
            return
        time.sleep(0.25)
    raise TimeoutError(
        f"Adobe XD plugin did not connect to {client.url}; open XD, open a document, "
        "then open Plugins > MCP Adobe Bridge"
    )


def require_mapping(value: Any, step: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError(f"{step} returned non-object result: {type(value).__name__}")
    return value


def run_read(adapter: XdAdapter) -> None:
    health = require_mapping(adapter.execute("creative.health", {})["result"], "xd.health")
    if health.get("application") != "xd" or health.get("bridge") != "connected":
        raise RuntimeError(f"unexpected XD health response: {health}")
    emit("PASS", "xd_health", health)

    document = require_mapping(
        adapter.execute("creative.document.info", {})["result"],
        "xd.document.info",
    )
    emit("PASS", "xd_document_info", document)

    selection = require_mapping(
        adapter.execute("creative.selection.get", {})["result"],
        "xd.selection.get",
    )
    if not isinstance(selection.get("items"), list):
        raise RuntimeError(f"XD selection result is missing items list: {selection}")
    emit("PASS", "xd_selection", {"count": len(selection["items"])})


def run_write(adapter: XdAdapter, approval_timeout: float) -> None:
    queued = require_mapping(
        adapter.execute(
            "xd.queue.rectangle_create",
            {
                "name": "MCP_ADOBE_E2E_RECT",
                "width": 96,
                "height": 64,
                "x": 40,
                "y": 40,
                "fill": "#4F7CFF",
            },
        )["result"],
        "xd.queue.rectangle_create",
    )
    operation_id = queued.get("operation_id")
    if queued.get("status") != "queued" or not queued.get("approval_required") or not operation_id:
        raise RuntimeError(f"unexpected XD queue response: {queued}")

    emit(
        "WAITING_APPROVAL",
        "xd_queue_rectangle",
        {
            "operation_id": operation_id,
            "instruction": "Click Apply pending in the MCP Adobe Bridge panel inside Adobe XD.",
        },
    )

    deadline = time.monotonic() + approval_timeout
    last_status: Mapping[str, Any] | None = None
    while time.monotonic() < deadline:
        status = require_mapping(
            adapter.execute("xd.queue.status", {"operation_id": operation_id})["result"],
            "xd.queue.status",
        )
        last_status = status
        state = status.get("status")
        if state == "applied":
            result = status.get("result")
            if not isinstance(result, Mapping):
                raise RuntimeError(f"applied XD operation has no result object: {status}")
            emit("PASS", "xd_write_applied", status)
            return
        if state in {"failed", "rejected"}:
            raise RuntimeError(f"XD write ended with status {state}: {status}")
        time.sleep(0.5)

    emit(
        "BLOCKED",
        "xd_write_approval",
        {
            "operation_id": operation_id,
            "last_status": last_status,
            "instruction": "No Apply pending click was observed before timeout.",
        },
    )
    raise TimeoutError("Adobe XD write approval was not completed before timeout")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Real Adobe XD UXP bridge E2E probe")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--connect-timeout", type=float, default=30.0)
    parser.add_argument("--approval-timeout", type=float, default=90.0)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bridge = XdWebSocketBridgeClient(
        host=args.host,
        port=args.port,
        startup_timeout_seconds=5.0,
        call_timeout_seconds=10.0,
    )
    try:
        bridge.start()
        emit("PASS", "xd_bridge_listen", {"url": bridge.url})
        wait_connected(bridge, args.connect_timeout)
        adapter = XdAdapter(bridge, writes_enabled=args.write)
        run_read(adapter)
        if args.write:
            run_write(adapter, args.approval_timeout)
        else:
            emit("SKIP", "xd_write", "rerun with --write to queue an approval-gated rectangle mutation")
        emit("PASS", "xd_real_e2e", {"write": args.write})
        return 0
    except TimeoutError as exc:
        emit("BLOCKED", "xd_real_e2e", str(exc))
        return 3
    except Exception as exc:
        emit("FAIL", "xd_real_e2e", str(exc))
        return 1
    finally:
        bridge.close()


if __name__ == "__main__":
    raise SystemExit(main())
