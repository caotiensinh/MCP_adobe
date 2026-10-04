from __future__ import annotations

import os
import subprocess
import time

from mcp_adobe.mcp_stdio import McpSubprocessToolClient, SubprocessMcpConfig


def _layers(payload: object) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    layers = data.get("layers")
    return layers if isinstance(layers, dict) else None


def _layer_status(layers: dict[str, object], name: str) -> str | None:
    layer = layers.get(name)
    if not isinstance(layer, dict):
        return None
    status = layer.get("status")
    return status if isinstance(status, str) else None


def _host_connected(payload: object) -> bool:
    layers = _layers(payload)
    if layers is None:
        return False
    return (
        _layer_status(layers, "panel") == "ok"
        and _layer_status(layers, "illustrator") == "ok"
    )


def _document_open(payload: object) -> bool:
    layers = _layers(payload)
    if layers is None:
        return False
    document = layers.get("document")
    if not isinstance(document, dict):
        return False
    status = document.get("status")
    open_count = document.get("openCount")
    if status == "ok":
        return True
    return isinstance(open_count, int) and not isinstance(open_count, bool) and open_count > 0


def _result_has_failure(payload: object) -> bool:
    if not isinstance(payload, dict):
        return True
    if payload.get("ok") is False:
        return True
    execution = payload.get("execution")
    if isinstance(execution, str) and execution.lower() in {"failed", "error"}:
        return True
    return payload.get("error") not in (None, False, "")


def _dump_cep_runtime(label: str) -> None:
    if os.name != "nt":
        return
    command = rf"""
$ErrorActionPreference='Continue'
Write-Host '=== CEP runtime snapshot: {label} ==='
Get-CimInstance Win32_Process -Filter "Name='CEPHtmlEngine.exe'" -ErrorAction SilentlyContinue |
  Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine |
  Format-List
Get-CimInstance Win32_Process -Filter "Name='Illustrator.exe'" -ErrorAction SilentlyContinue |
  Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine |
  Format-List
"""
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        print(completed.stdout, flush=True)
        if completed.stderr:
            print(completed.stderr, flush=True)
    except Exception as exc:
        print(f"CEP_DIAGNOSTIC_EXCEPTION={exc!r}", flush=True)


def main() -> int:
    upstream_python = os.environ["UPSTREAM_PYTHON"]
    illustrator_exe = os.environ["ILLUSTRATOR_EXE"]
    client = McpSubprocessToolClient(
        SubprocessMcpConfig(
            command=upstream_python,
            args=("-B", "-m", "illustrator_mcp.server"),
            env={"WS_HOST": "127.0.0.1", "WS_PORT": "8081", "TIMEOUT": "30"},
            startup_timeout_seconds=90,
            call_timeout_seconds=90,
        )
    )
    try:
        try:
            client.start()
        except Exception:
            _dump_cep_runtime("startup-failure")
            raise
        print(f"TOOLS_COUNT={len(client.tool_names)}", flush=True)
        required = {"illustrator_connection_status", "illustrator_document"}
        missing = required - set(client.tool_names)
        if missing:
            raise RuntimeError(f"missing required tools: {sorted(missing)!r}")

        subprocess.Popen([illustrator_exe])
        deadline = time.time() + 90
        last: object = None
        while time.time() < deadline:
            try:
                last = client.call_tool(
                    "illustrator_connection_status", {"params": {"probe": True}}
                )
                print(f"CONNECTION_STATUS={last!r}", flush=True)
                if _host_connected(last):
                    print("CEP_HOST_READY=PASS", flush=True)
                    break
            except Exception as exc:
                last = {"exception": repr(exc)}
                print(f"CONNECTION_RETRY={last!r}", flush=True)
            time.sleep(2)
        else:
            _dump_cep_runtime("final-before-timeout")
            raise RuntimeError(f"CEP panel/Illustrator host did not become ready: {last!r}")

        result = client.call_tool(
            "illustrator_document", {"params": {"action": "create"}}
        )
        print(f"CREATE_RESULT={result!r}", flush=True)
        if _result_has_failure(result):
            raise RuntimeError(f"document create returned failure: {result!r}")

        verify_deadline = time.time() + 15
        verified: object = None
        while time.time() < verify_deadline:
            verified = client.call_tool(
                "illustrator_connection_status", {"params": {"probe": True}}
            )
            print(f"POST_CREATE_STATUS={verified!r}", flush=True)
            if _host_connected(verified) and _document_open(verified):
                print("CEP_DOCUMENT_VERIFY=PASS", flush=True)
                print("CEP_LIVE_CREATE=PASS", flush=True)
                return 0
            time.sleep(1)

        raise RuntimeError(
            f"document create was accepted but no open document was verified: {verified!r}"
        )
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
