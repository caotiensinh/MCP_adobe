from __future__ import annotations

import asyncio
import io
import json
import unittest
from unittest.mock import patch

from mcp import Client
from mcp.server.auth.provider import AccessToken, TokenVerifier

from mcp_adobe.audit import JsonLineSecurityAuditSink, SecurityAuditEvent, security_audit_payload
from mcp_adobe.auth import OAuthResourceConfig
from mcp_adobe.server import build_server


class _NeverVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        return None


class _NeverRuntime:
    def describe(self):
        raise AssertionError("runtime must not be touched by denied profile operation")

    def read(self, application, capability, arguments):
        raise AssertionError("runtime must not be touched by denied profile operation")

    def write(self, application, capability, arguments, *, allow_overwrite=False):
        raise AssertionError("runtime must not be touched by denied profile operation")

    def authorized_write(self, application, capability, arguments, **kwargs):
        raise AssertionError("runtime must not be touched by denied profile operation")

    def close(self):
        return


def _config() -> OAuthResourceConfig:
    return OAuthResourceConfig(
        issuer_url="http://127.0.0.1:9000",
        resource_url="http://127.0.0.1:9001/mcp",
        introspection_endpoint="http://127.0.0.1:9000/introspect",
        required_scopes=("creative:access",),
    )


def _token() -> AccessToken:
    return AccessToken(
        token="DO-NOT-LOG-THIS-BEARER-TOKEN",
        client_id="chatgpt-client",
        scopes=["creative:access", "offline_access"],
        subject="alice@example.test",
        resource="http://127.0.0.1:9001/mcp",
    )


class SecurityAuditTests(unittest.TestCase):
    def test_payload_contains_identity_but_never_bearer_token(self) -> None:
        payload = security_audit_payload(
            SecurityAuditEvent(
                tool="creative_write",
                decision="denied",
                application="photoshop",
                capability="creative.document.create",
                reason="deployment-profile-missing:creative:write",
            ),
            _token(),
            timestamp="2026-10-04T00:00:00Z",
        )
        encoded = json.dumps(payload, sort_keys=True)
        self.assertNotIn("DO-NOT-LOG-THIS-BEARER-TOKEN", encoded)
        self.assertEqual(payload["principal"]["subject"], "alice@example.test")
        self.assertEqual(payload["principal"]["client_id"], "chatgpt-client")
        self.assertEqual(payload["principal"]["scopes"], ["creative:access", "offline_access"])

    def test_jsonl_sink_never_serializes_token_value(self) -> None:
        stream = io.StringIO()
        sink = JsonLineSecurityAuditSink(stream)
        sink.emit(
            SecurityAuditEvent(tool="creative_read", decision="allowed", application="xd", capability="xd.health"),
            _token(),
        )
        line = stream.getvalue()
        self.assertNotIn("DO-NOT-LOG-THIS-BEARER-TOKEN", line)
        payload = json.loads(line)
        self.assertEqual(payload["event"], "mcp_adobe.security")
        self.assertEqual(payload["principal"]["subject"], "alice@example.test")

    def test_profile_denial_audits_principal_before_runtime(self) -> None:
        stream = io.StringIO()
        server = build_server(
            _NeverRuntime(),
            oauth_config=_config(),
            token_verifier=_NeverVerifier(),
            audit_sink=JsonLineSecurityAuditSink(stream),
        )

        async def scenario():
            async with Client(server) as client:
                return await client.call_tool(
                    "creative_write",
                    {
                        "application": "photoshop",
                        "capability": "creative.document.create",
                        "arguments": {"secret": "must-not-be-audited"},
                    },
                )

        with patch("mcp_adobe.server.get_access_token", return_value=_token()):
            result = asyncio.run(scenario())

        self.assertTrue(result.is_error)
        audit_lines = [line for line in stream.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(audit_lines), 1)
        payload = json.loads(audit_lines[0])
        self.assertEqual(payload["tool"], "creative_write")
        self.assertEqual(payload["decision"], "denied")
        self.assertEqual(payload["application"], "photoshop")
        self.assertEqual(payload["capability"], "creative.document.create")
        self.assertEqual(payload["principal"]["subject"], "alice@example.test")
        encoded = json.dumps(payload, sort_keys=True)
        self.assertNotIn("DO-NOT-LOG-THIS-BEARER-TOKEN", encoded)
        self.assertNotIn("must-not-be-audited", encoded)


if __name__ == "__main__":
    unittest.main()
