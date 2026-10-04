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


def _dump_cep_runtime(label: str) -> None:
    if os.name != "nt":
        return
    command = rf"""
$ErrorActionPreference='Continue'
Write-Host '=== CEP runtime snapshot: {label} ==='
Write-Host '=== CEPHtmlEngine runtime diagnostics ==='
Get-CimInstance Win32_Process -Filter "Name='CEPHtmlEngine.exe'" -ErrorAction SilentlyContinue |
  Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine |
  Format-List
Write-Host '=== Illustrator runtime diagnostics ==='
Get-CimInstance Win32_Process -Filter "Name='Illustrator.exe'" -ErrorAction SilentlyContinue |
  Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine |
  Format-List
Write-Host '=== Top-level TEMP CEP/CSXS/PlugPlug files ==='
Get-ChildItem -LiteralPath $env:TEMP -File -ErrorAction SilentlyContinue |
  Where-Object {{ $_.Name -match 'cep|csxs|plugplug|illustrator' }} |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 30 FullName,Length,LastWriteTime |
  Format-Table -AutoSize
Write-Host '=== CEP targeted log paths ==='
$dirs=@(
  (Join-Path $env:LOCALAPPDATA 'Temp\CEPHtmlEngine'),
  (Join-Path $env:LOCALAPPDATA 'Adobe\CEP'),
  (Join-Path $env:LOCALAPPDATA 'Adobe\CSXS'),
  (Join-Path $env:APPDATA 'Adobe\CEP'),
  (Join-Path $env:APPDATA 'Adobe\CSXS')
)
foreach($dir in $dirs){{
  Write-Host "LOGDIR=$dir EXISTS=$(Test-Path -LiteralPath $dir)"
  if(Test-Path -LiteralPath $dir){{
    Get-ChildItem -LiteralPath $dir -Recurse -File -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending |
      Select-Object -First 20 FullName,Length,LastWriteTime |
      Format-Table -AutoSize
  }}
}}
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
        deadline = time.time() + 35
        last: object = None
        dumped_mid = False
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
            if not dumped_mid and time.time() > deadline - 20:
                _dump_cep_runtime("mid-wait")
                dumped_mid = True
            time.sleep(2)
        else:
            _dump_cep_runtime("final-before-timeout")
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
