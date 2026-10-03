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
    "creative_authorized_write",
}
EXPECTED_APPLICATIONS = {"photoshop", "illustrator", "xd"}


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


async def _exercise_bundle(extracted: Path, *, exercise_adapters: bool) -> None:
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

        if not exercise_adapters:
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

        # Photoshop and Illustrator are subprocess MCP adapters. Requiring them
        # to report connected proves the packaged UV process can resolve and
        # launch the pinned npx upstream servers. Adobe itself does not need to
        # be interactive merely to initialize/list the upstream MCP tools.
        for application in ("photoshop", "illustrator"):
            if by_name[application].get("connected") is not True:
                raise AssertionError(
                    f"packaged {application} upstream MCP did not initialize via npx: {by_name[application]}"
                )
        _emit(
            "PASS",
            "packaged_adapter_bootstrap",
            {
                "photoshop_connected": by_name["photoshop"].get("connected"),
                "illustrator_connected": by_name["illustrator"].get("connected"),
                "xd_connected": by_name["xd"].get("connected"),
            },
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test an MCP Adobe .mcpb package")
    parser.add_argument("package", type=Path)
    parser.add_argument(
        "--exercise-adapters",
        action="store_true",
        help="Also call creative_discover and require packaged Photoshop/Illustrator npx upstreams to initialize.",
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
        asyncio.run(_exercise_bundle(temp_root, exercise_adapters=args.exercise_adapters))
        _emit("PASS", "mcpb_runtime", {"package": package.name})
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
