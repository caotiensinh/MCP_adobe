from __future__ import annotations

import os
import subprocess
import unittest


_OAUTH_ENV = {
    "MCP_ADOBE_OAUTH_ISSUER_URL",
    "MCP_ADOBE_OAUTH_RESOURCE_URL",
    "MCP_ADOBE_OAUTH_INTROSPECTION_ENDPOINT",
    "MCP_ADOBE_OAUTH_REQUIRED_SCOPES",
    "MCP_ADOBE_OAUTH_CLIENT_ID",
    "MCP_ADOBE_OAUTH_CLIENT_SECRET",
    "MCP_ADOBE_OAUTH_VALIDATE_RESOURCE",
}


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    for name in _OAUTH_ENV:
        env.pop(name, None)
    return env


class OAuthPreflightCliTests(unittest.TestCase):
    def test_installed_console_entrypoint_has_help(self) -> None:
        completed = subprocess.run(
            ["mcp-adobe-oauth-preflight", "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("OAuth provider compatibility", completed.stdout)
        self.assertIn("--json", completed.stdout)

    def test_installed_console_entrypoint_fails_closed_without_oauth_env(self) -> None:
        completed = subprocess.run(
            ["mcp-adobe-oauth-preflight"],
            env=_clean_env(),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("OAuth environment is not configured", completed.stderr)


if __name__ == "__main__":
    unittest.main()
