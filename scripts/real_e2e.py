from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from mcp_adobe.mcp_stdio import (
    McpSubprocessToolClient,
    illustrator_stdio_config,
    photoshop_stdio_config,
)


class SmokeFailure(RuntimeError):
    pass


def _emit(status: str, step: str, detail: Any = None) -> None:
    payload = {"status": status, "step": step}
    if detail is not None:
        payload["detail"] = detail
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _call(client: Any, tool: str, arguments: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    try:
        result = client.call_tool(tool, arguments or {})
    except Exception as exc:
        raise SmokeFailure(f"{tool}: {exc}") from exc
    if not isinstance(result, Mapping):
        raise SmokeFailure(f"{tool}: non-mapping result {type(result).__name__}")
    return result


def _require_tools(client: Any, required: set[str]) -> None:
    available = set(client.tool_names)
    missing = sorted(required - available)
    if missing:
        raise SmokeFailure(f"missing upstream tools: {missing}")
    _emit("PASS", "tools/list", {"required": sorted(required), "available_count": len(available)})


def _photoshop_ping_ready(result: Mapping[str, Any]) -> bool:
    if result.get("connected") is True:
        return True
    for key in ("text", "value", "message"):
        value = result.get(key)
        if isinstance(value, str) and "successfully connected to photoshop" in value.lower():
            return True
    return False


def _photoshop(client: Any, write: bool, output_dir: Path) -> None:
    required = {"photoshop_ping", "photoshop_get_state"}
    if write:
        required |= {"photoshop_create_document", "photoshop_save_document", "photoshop_export_as", "photoshop_undo"}
    _require_tools(client, required)

    ping = _call(client, "photoshop_ping")
    if not _photoshop_ping_ready(ping):
        raise SmokeFailure(f"photoshop_ping not connected: {dict(ping)}")
    _emit("PASS", "photoshop_ping", ping)
    state = _call(client, "photoshop_get_state")
    _emit("PASS", "photoshop_get_state", state)

    if not write:
        _emit("SKIP", "photoshop_write", "rerun with --write to enable create/save/export")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    psd = output_dir / "mcp_adobe_smoke.psd"
    png = output_dir / "mcp_adobe_smoke.png"
    for p in (psd, png):
        if p.exists():
            raise SmokeFailure(f"refusing to overwrite existing smoke output: {p}")

    _call(client, "photoshop_create_document", {"width": 320, "height": 240, "resolution": 72, "colorMode": "RGB"})
    _emit("PASS", "photoshop_create_document")

    _call(client, "photoshop_save_document", {"path": str(psd), "format": "PSD"})
    if not psd.exists():
        raise SmokeFailure(f"save reported success but file does not exist: {psd}")
    _emit("PASS", "photoshop_save_verify", {"path": str(psd), "bytes": psd.stat().st_size})

    _call(client, "photoshop_export_as", {"path": str(png), "format": "PNG"})
    if not png.exists():
        raise SmokeFailure(f"export reported success but file does not exist: {png}")
    _emit("PASS", "photoshop_export_verify", {"path": str(png), "bytes": png.stat().st_size})


def _illustrator(client: Any, write: bool, output_dir: Path) -> None:
    required = {"get_document_info"}
    if write:
        required |= {"create_document", "save_document", "export", "undo"}
    _require_tools(client, required)

    try:
        info = _call(client, "get_document_info")
        _emit("PASS", "illustrator_get_document_info", info)
    except SmokeFailure as exc:
        if write:
            raise
        _emit("SKIP", "illustrator_get_document_info", str(exc))

    if not write:
        _emit("SKIP", "illustrator_write", "rerun with --write to enable create/save/export")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    ai_path = output_dir / "mcp_adobe_smoke.ai"
    png_path = output_dir / "mcp_adobe_smoke.png"
    for p in (ai_path, png_path):
        if p.exists():
            raise SmokeFailure(f"refusing to overwrite existing smoke output: {p}")

    _call(client, "create_document", {"width": 320, "height": 240})
    _emit("PASS", "illustrator_create_document")

    _call(client, "save_document", {"mode": "save_as", "path": str(ai_path), "overwrite": False})
    if not ai_path.exists():
        raise SmokeFailure(f"save reported success but file does not exist: {ai_path}")
    _emit("PASS", "illustrator_save_verify", {"path": str(ai_path), "bytes": ai_path.stat().st_size})

    _call(client, "export", {"target": "artboard:0", "format": "png", "output_path": str(png_path), "overwrite": False})
    if not png_path.exists():
        raise SmokeFailure(f"export reported success but file does not exist: {png_path}")
    _emit("PASS", "illustrator_export_verify", {"path": str(png_path), "bytes": png_path.stat().st_size})


def run(
    application: str,
    *,
    write: bool = False,
    output_dir: Path | None = None,
    client_factory: Callable[[Any], Any] = McpSubprocessToolClient,
) -> int:
    if application == "photoshop":
        config = photoshop_stdio_config()
        runner = _photoshop
    elif application == "illustrator":
        config = illustrator_stdio_config()
        runner = _illustrator
    else:
        raise ValueError(f"unsupported application: {application}")

    target = output_dir or Path(tempfile.gettempdir()) / "mcp_adobe_e2e" / application

    try:
        with client_factory(config) as client:
            _emit("PASS", "mcp_connect", {"application": application})
            runner(client, write, target)
    except Exception as exc:
        _emit("FAIL", "real_e2e", str(exc))
        return 1

    _emit("PASS", "real_e2e", {"application": application, "write": write})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Real Adobe MCP smoke test using pinned upstream servers.")
    parser.add_argument("application", choices=("photoshop", "illustrator"))
    parser.add_argument("--write", action="store_true", help="Enable create/save/export checks. Default is read-only.")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    return run(args.application, write=args.write, output_dir=args.output_dir)


if __name__ == "__main__":
    sys.exit(main())
