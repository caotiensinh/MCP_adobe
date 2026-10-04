from __future__ import annotations

import json
import time

from mcp_adobe.xd_bridge import XdWebSocketBridgeClient


def emit(marker: str, payload: object | None = None) -> None:
    if payload is None:
        print(marker, flush=True)
    else:
        print(f"{marker}={json.dumps(payload, ensure_ascii=True, default=str)}", flush=True)


def main() -> int:
    client = XdWebSocketBridgeClient(
        startup_timeout_seconds=10.0,
        call_timeout_seconds=15.0,
    )
    try:
        client.start()
        print(
            "XD_ACTIVATION_REQUIRED=Open Plugins > MCP Adobe Bridge in Adobe XD and keep the panel visible",
            flush=True,
        )
        deadline = time.time() + 180
        while time.time() < deadline:
            if client.connected:
                break
            time.sleep(1)
        else:
            raise RuntimeError(
                "Adobe XD MCP panel did not connect within 180s; open Plugins > MCP Adobe Bridge"
            )

        emit("XD_PANEL_CONNECTED", dict(client.plugin_info))
        health = client.call_tool("xd.health", {})
        if health.get("application") != "xd" or health.get("bridge") != "connected":
            raise RuntimeError(f"XD health not ready: {health!r}")
        emit("XD_HEALTH_PASS", health)

        before = client.call_tool("xd.document.info", {})
        emit("XD_DOCUMENT_BEFORE", before)

        expected_name = "MCP Adobe Live Probe"
        expected_width = 120
        expected_height = 80
        queued = client.call_tool(
            "xd.queue.rectangle_create",
            {
                "name": expected_name,
                "x": 24,
                "y": 24,
                "width": expected_width,
                "height": expected_height,
                "fill": "#4F7CFF",
            },
        )
        if queued.get("status") != "queued" or queued.get("approval_required") is not True:
            raise RuntimeError(f"XD mutation was not queued for approval: {queued!r}")
        operation_id = queued.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            raise RuntimeError(f"XD queue response missing operation_id: {queued!r}")
        emit("XD_APPROVAL_REQUIRED", queued)
        print("XD_ACTION_REQUIRED=Click 'Apply pending' in the MCP Adobe Bridge panel now", flush=True)

        deadline = time.time() + 120
        last_status: dict[str, object] | None = None
        while time.time() < deadline:
            status_payload = client.call_tool("xd.queue.status", {"operation_id": operation_id})
            if not isinstance(status_payload, dict):
                raise RuntimeError(f"XD queue status was not an object: {status_payload!r}")
            last_status = status_payload
            emit("XD_QUEUE_STATUS", last_status)
            status = last_status.get("status")
            if status == "applied":
                break
            if status in {"failed", "rejected"}:
                raise RuntimeError(f"XD queued mutation ended as {status}: {last_status!r}")
            time.sleep(2)
        else:
            raise RuntimeError(f"XD approval timed out; final status: {last_status!r}")

        result = last_status.get("result") if last_status else None
        if not isinstance(result, dict):
            raise RuntimeError(f"XD applied operation missing mutation result: {last_status!r}")
        bounds = result.get("bounds")
        if not isinstance(bounds, dict):
            raise RuntimeError(f"XD applied rectangle missing bounds: {result!r}")
        if (
            not result.get("guid")
            or result.get("type") != "Rectangle"
            or result.get("name") != expected_name
            or int(bounds.get("width", 0)) != expected_width
            or int(bounds.get("height", 0)) != expected_height
        ):
            raise RuntimeError(f"XD applied rectangle result did not match expected effect: {result!r}")
        emit("XD_MUTATION_RESULT_VERIFIED", result)

        after = client.call_tool("xd.document.info", {})
        emit("XD_DOCUMENT_AFTER", after)
        emit(
            "XD_LIVE_WRITE_VERIFY_PASS",
            {
                "operation_id": operation_id,
                "guid": result.get("guid"),
                "type": result.get("type"),
                "name": result.get("name"),
                "bounds": bounds,
            },
        )
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
