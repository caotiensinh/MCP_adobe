from __future__ import annotations

import os
import subprocess
import time

from mcp_adobe.mcp_stdio import McpSubprocessToolClient, SubprocessMcpConfig


def _looks_connected(payload: object) -> bool:
    text = repr(payload).lower()
    return (
        "connected" in text
        and "'connected': false" not in text
        and '"connected": false' not in text
        and "not connected" not in text
    )


def main() -> int:
    upstream_python = os.environ["UPSTREAM_PYTHON"]
    illustrator_exe = os.environ["ILLUSTRATOR_EXE"]
    client = McpSubprocessToolClient(
        SubprocessMcpConfig(
            command=upstream_python,
            args=("-B", "-m", "illustrator_mcp.server"),
            env={"WS_HOST": "127.0.0.1", "WS_PORT": "8081", "TIMEOUT": "30"},
            startup_timeout_seconds=45,
            call_timeout_seconds=90,
        )
    )
    try:
        client.start()
        print(f"TOOLS_COUNT={len(client.tool_names)}", flush=True)
        required = {"illustrator_connection_status", "illustrator_document"}
        missing = required - set(client.tool_names)
        if missing:
            raise RuntimeError(f"missing required tools: {sorted(missing)!r}")

        subprocess.Popen([illustrator_exe])
        deadline = time.time() + 75
        last: object = None
        while time.time() < deadline:
            try:
                last = client.call_tool(
                    "illustrator_connection_status", {"params": {"probe": True}}
                )
                print(f"CONNECTION_STATUS={last!r}", flush=True)
                if _looks_connected(last):
                    break
            except Exception as exc:  # diagnostic retry while panel starts
                last = {"exception": repr(exc)}
                print(f"CONNECTION_RETRY={last!r}", flush=True)
            time.sleep(2)
        else:
            raise RuntimeError(f"CEP panel did not connect: {last!r}")

        result = client.call_tool(
            "illustrator_document", {"params": {"action": "create"}}
        )
        print(f"CREATE_RESULT={result!r}", flush=True)
        low = repr(result).lower()
        if "error" in low and any(
            marker in low for marker in ("'error': true", '"error": true', "failed", "not connected")
        ):
            raise RuntimeError(f"document create returned error: {result!r}")
        print("CEP_LIVE_CREATE=PASS", flush=True)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
