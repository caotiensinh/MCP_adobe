from __future__ import annotations

import json
import time

from mcp_adobe.xd_bridge import XdWebSocketBridgeClient


def emit(marker: str, payload: object | None = None) -> None:
    if payload is None:
        print(marker, flush=True)
    else:
        print(f"{marker}={json.dumps(payload, ensure_ascii=False, default=str)}", flush=True)


def main() -> int:
    client = XdWebSocketBridgeClient(
        startup_timeout_seconds=10.0,
        call_timeout_seconds=15.0,
    )
    try:
        client.start()
        deadline = time.time() + 60
        while time.time() < deadline:
            if client.connected:
                break
            time.sleep(1)
        else:
            raise RuntimeError(
                "Adobe XD MCP panel did not connect within 60s; keep Plugins > MCP Adobe Bridge open"
            )

        emit("XD_PANEL_CONNECTED", dict(client.plugin_info))
        health = client.call_tool("xd.health", {})
        if health.get("application") != "xd" or health.get("bridge") != "connected":
            raise RuntimeError(f"XD health not ready: {health!r}")
        emit("XD_HEALTH_PASS", health)

        before = client.call_tool("xd.document.info", {})
        before_count = int(before.get("rootChildren", 0))
        emit("XD_DOCUMENT_BEFORE", before)

        queued = client.call_tool(
            "xd.queue.rectangle_create",
            {
                "name": "MCP Adobe Live Probe",
                "x": 24,
                "y": 24,
                "width": 120,
                "height": 80,
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
        last_status: object = None
        while time.time() < deadline:
            last_status = client.call_tool("xd.queue.status", {"operation_id": operation_id})
            emit("XD_QUEUE_STATUS", last_status)
            status = last_status.get("status")
            if status == "applied":
                break
            if status in {"failed", "rejected"}:
                raise RuntimeError(f"XD queued mutation ended as {status}: {last_status!r}")
            time.sleep(2)
        else:
            raise RuntimeError(f"XD approval timed out; final status: {last_status!r}")

        after = client.call_tool("xd.document.info", {})
        after_count = int(after.get("rootChildren", 0))
        emit("XD_DOCUMENT_AFTER", after)
        if after_count <= before_count:
            raise RuntimeError(
                f"XD operation reported applied but document child count did not increase: "
                f"before={before_count} after={after_count}"
            )

        emit(
            "XD_LIVE_WRITE_VERIFY_PASS",
            {"operation_id": operation_id, "before": before_count, "after": after_count},
        )
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
