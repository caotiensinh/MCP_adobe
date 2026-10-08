from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from mcp import Client, StdioServerParameters


EXPECTED_TOOLS = {
    "creative_discover",
    "creative_read",
    "creative_write",
    "creative_live_build",
    "creative_authorized_write",
}
EXPECTED_APPLICATIONS = {"photoshop", "illustrator", "xd"}
EXPECTED_READINESS_PROBE = "creative.health"
DEFAULT_TIMEOUT_SECONDS = 180.0


def _emit(status: str, step: str, detail: object | None = None) -> None:
    payload: dict[str, object] = {"status": status, "step": step}
    if detail is not None:
        payload["detail"] = detail
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _validate_archive(package: Path) -> None:
    with zipfile.ZipFile(package) as archive:
        names = {name.replace("\\", "/") for name in archive.namelist()}
    required = {
        "manifest.json",
        "pyproject.toml",
        "src/mcp_adobe/server.py",
        "src/mcp_adobe/mcp_stdio.py",
    }
    missing = sorted(required - names)
    if missing:
        raise AssertionError(f"MCPB archive is missing runtime files: {missing}")
    forbidden = sorted(name for name in names if ".egg-info/" in name or name.startswith("tests/"))
    if forbidden:
        raise AssertionError(f"MCPB archive contains generated/development files: {forbidden}")
    _emit("PASS", "archive_contents", {"files": len(names)})


def _validate_discovery_contract(
    payload: dict[str, object],
    by_name: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    contract = payload.get("connection_contract")
    expected_contract = {
        "connected_means": "transport_connected",
        "application_ready_requires": "declared_readiness_probe",
        "discovery_probes_application": False,
    }
    if contract != expected_contract:
        raise AssertionError(
            "packaged creative_discover connection contract drifted: "
            f"expected={expected_contract!r} actual={contract!r}"
        )

    readiness: dict[str, dict[str, object]] = {}
    for application in sorted(EXPECTED_APPLICATIONS):
        item = by_name[application]
        if item.get("connection_semantics") != "transport_only":
            raise AssertionError(
                f"packaged {application} connection_semantics must be transport_only: {item}"
            )
        if item.get("transport_connected") != item.get("connected"):
            raise AssertionError(
                f"packaged {application} transport_connected must mirror backward-compatible connected: {item}"
            )
        if item.get("readiness_probe") != EXPECTED_READINESS_PROBE:
            raise AssertionError(
                f"packaged {application} readiness_probe drifted from {EXPECTED_READINESS_PROBE}: {item}"
            )
        if item.get("readiness_status") != "not_probed":
            raise AssertionError(
                f"packaged {application} discovery must remain non-probing: {item}"
            )
        readiness[application] = {
            "transport_connected": bool(item.get("transport_connected")),
            "readiness_probe": item.get("readiness_probe"),
            "readiness_status": item.get("readiness_status"),
        }
    return readiness


async def _exercise_bundle(
    extracted: Path,
    *,
    exercise_adapters: bool,
    require_connected: frozenset[str],
) -> None:
    env = dict(os.environ)
    # A packaged Claude Desktop extension is local stdio. Ignore any remote OAuth
    # variables inherited by CI or a developer shell.
    for name in list(env):
        if name.startswith("MCP_ADOBE_OAUTH_"):
            env.pop(name, None)
    env["MCP_ADOBE_TRANSPORT"] = "stdio"

    server = StdioServerParameters(
        command="uv",
        args=[
            "run",
            "--directory",
            str(extracted),
            "mcp-adobe",
            "--transport",
            "stdio",
        ],
        env=env,
    )
    async with Client(server) as client:
        listed = await client.list_tools()
        tools = {tool.name for tool in listed.tools}
        if tools != EXPECTED_TOOLS:
            raise AssertionError(f"unexpected packaged MCP tool surface: {sorted(tools)}")
        _emit("PASS", "packaged_tools_list", sorted(tools))

        if not exercise_adapters and not require_connected:
            return

        discovered = await client.call_tool("creative_discover", {})
        if discovered.is_error:
            raise AssertionError("packaged creative_discover returned an MCP tool error")
        payload = discovered.structured_content or {}
        applications = payload.get("applications")
        if not isinstance(applications, list):
            raise AssertionError(f"creative_discover returned invalid applications: {payload}")
        by_name = {
            str(item.get("application")): item
            for item in applications
            if isinstance(item, dict) and item.get("application")
        }
        if set(by_name) != EXPECTED_APPLICATIONS:
            raise AssertionError(f"unexpected packaged applications: {sorted(by_name)}")

        readiness = _validate_discovery_contract(payload, by_name)
        connection_state = {
            application: bool(by_name[application].get("transport_connected"))
            for application in sorted(EXPECTED_APPLICATIONS)
        }
        upstreams = {
            application: {
                "repository": by_name[application].get("upstream_repository"),
                "snapshot": by_name[application].get("upstream_snapshot"),
                "transport": by_name[application].get("transport"),
            }
            for application in sorted(EXPECTED_APPLICATIONS)
        }
        _emit(
            "PASS",
            "packaged_adapter_discovery",
            {
                "applications": sorted(by_name),
                "transport_connected": connection_state,
                "readiness": readiness,
                "upstreams": upstreams,
            },
        )

        # Transport connectivity is a separate live-environment assertion. It is
        # not application readiness: all built-in mutations perform the declared
        # readiness probe before touching an Adobe document.
        for application in sorted(require_connected):
            if not connection_state[application]:
                raise AssertionError(
                    f"packaged {application} adapter was required to have transport connectivity but reported disconnected: "
                    f"{by_name[application]}"
                )
        if require_connected:
            _emit("PASS", "packaged_required_connectivity", sorted(require_connected))


def _positive_timeout(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a positive number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive number")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test an MCP Adobe .mcpb package")
    parser.add_argument("package", type=Path)
    parser.add_argument(
        "--exercise-adapters",
        action="store_true",
        help="Call creative_discover and verify the packaged Photoshop/Illustrator/XD adapter metadata surface.",
    )
    parser.add_argument(
        "--require-connected",
        action="append",
        choices=sorted(EXPECTED_APPLICATIONS),
        default=[],
        help=(
            "Additionally require one application adapter transport to report connected. Repeat for multiple apps. "
            "This does not claim that the Adobe application itself passed its readiness probe."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=_positive_timeout,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Bound the complete packaged runtime exercise so an upstream process cannot hang CI indefinitely.",
    )
    args = parser.parse_args()

    package = args.package.resolve()
    if not package.is_file():
        raise SystemExit(f"MCPB package not found: {package}")
    _validate_archive(package)

    temp_root = Path(tempfile.mkdtemp(prefix="mcp-adobe-mcpb-"))
    try:
        with zipfile.ZipFile(package) as archive:
            archive.extractall(temp_root)
        _emit("PASS", "archive_extract", str(temp_root))
        try:
            asyncio.run(
                asyncio.wait_for(
                    _exercise_bundle(
                        temp_root,
                        exercise_adapters=args.exercise_adapters,
                        require_connected=frozenset(args.require_connected),
                    ),
                    timeout=args.timeout_seconds,
                )
            )
        except TimeoutError:
            _emit(
                "FAIL",
                "mcpb_runtime_timeout",
                {"timeout_seconds": args.timeout_seconds},
            )
            return 1
        _emit(
            "PASS",
            "mcpb_runtime",
            {
                "package": package.name,
                "required_connected": sorted(set(args.require_connected)),
            },
        )
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
