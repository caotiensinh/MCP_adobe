from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp_adobe.auth import OAuthResourceConfig
from mcp_adobe.server import _load_audit_sink


_OAUTH_ENV = {
    "MCP_ADOBE_OAUTH_ISSUER_URL",
    "MCP_ADOBE_OAUTH_RESOURCE_URL",
    "MCP_ADOBE_OAUTH_INTROSPECTION_ENDPOINT",
    "MCP_ADOBE_OAUTH_REQUIRED_SCOPES",
    "MCP_ADOBE_OAUTH_CLIENT_ID",
    "MCP_ADOBE_OAUTH_CLIENT_SECRET",
    "MCP_ADOBE_OAUTH_VALIDATE_RESOURCE",
}
_AUDIT_ENV = {
    "MCP_ADOBE_AUDIT_PATH",
    "MCP_ADOBE_AUDIT_MAX_BYTES",
    "MCP_ADOBE_AUDIT_BACKUP_COUNT",
}
_SUBPROCESS_TIMEOUT_SECONDS = 45


def _base_env(audit_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    for name in _OAUTH_ENV | _AUDIT_ENV:
        env.pop(name, None)
    env.update(
        {
            "MCP_ADOBE_OAUTH_ISSUER_URL": "http://127.0.0.1:19000",
            "MCP_ADOBE_OAUTH_RESOURCE_URL": "http://127.0.0.1:18787/mcp",
            "MCP_ADOBE_OAUTH_INTROSPECTION_ENDPOINT": "http://127.0.0.1:19000/introspect",
            "MCP_ADOBE_OAUTH_REQUIRED_SCOPES": "creative:access",
            "MCP_ADOBE_AUDIT_PATH": str(audit_path),
        }
    )
    return env


def _run_server_with_env(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mcp_adobe.server",
            "--transport",
            "streamable-http",
            "--host",
            "127.0.0.1",
            "--port",
            "18787",
            "--path",
            "/mcp",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
    )


class AuditConfigurationCliTests(unittest.TestCase):
    def test_invalid_max_bytes_exits_cleanly_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = _base_env(Path(temp_dir) / "security-audit.jsonl")
            env["MCP_ADOBE_AUDIT_MAX_BYTES"] = "0"
            completed = _run_server_with_env(env)

        output = completed.stdout + completed.stderr
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Invalid MCP Adobe audit configuration", output)
        self.assertIn("MCP_ADOBE_AUDIT_MAX_BYTES must be a positive integer", output)
        self.assertNotIn("Traceback", output)

    def test_invalid_backup_count_exits_cleanly_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = _base_env(Path(temp_dir) / "security-audit.jsonl")
            env["MCP_ADOBE_AUDIT_BACKUP_COUNT"] = "not-an-integer"
            completed = _run_server_with_env(env)

        output = completed.stdout + completed.stderr
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Invalid MCP Adobe audit configuration", output)
        self.assertIn("MCP_ADOBE_AUDIT_BACKUP_COUNT must be a positive integer", output)
        self.assertNotIn("Traceback", output)

    def test_filesystem_error_is_converted_to_clean_system_exit(self) -> None:
        config = OAuthResourceConfig(
            issuer_url="http://127.0.0.1:19000",
            resource_url="http://127.0.0.1:18787/mcp",
            introspection_endpoint="http://127.0.0.1:19000/introspect",
            required_scopes=("creative:access",),
        )
        with patch(
            "mcp_adobe.server.JsonLineSecurityAuditSink",
            side_effect=OSError("permission denied"),
        ):
            with self.assertRaisesRegex(
                SystemExit,
                "Invalid MCP Adobe audit configuration: permission denied",
            ):
                _load_audit_sink(config)


if __name__ == "__main__":
    unittest.main()
