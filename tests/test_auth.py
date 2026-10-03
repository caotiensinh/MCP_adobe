from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from mcp_adobe.auth import IntrospectionTokenVerifier, OAuthResourceConfig


class _Response:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _AsyncClient:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.posts: list[tuple[str, dict[str, object]]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url: str, **kwargs):
        self.posts.append((url, dict(kwargs)))
        return self.response


class OAuthResourceTests(unittest.TestCase):
    def test_from_env_returns_none_when_oauth_is_not_configured(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(OAuthResourceConfig.from_env())

    def test_from_env_rejects_partial_configuration(self) -> None:
        with patch.dict(
            os.environ,
            {"MCP_ADOBE_OAUTH_ISSUER_URL": "https://auth.example.com"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "incomplete OAuth configuration"):
                OAuthResourceConfig.from_env()

    def test_from_env_parses_scopes_and_client_credentials(self) -> None:
        env = {
            "MCP_ADOBE_OAUTH_ISSUER_URL": "https://auth.example.com",
            "MCP_ADOBE_OAUTH_RESOURCE_URL": "https://creative.example.com/mcp",
            "MCP_ADOBE_OAUTH_INTROSPECTION_ENDPOINT": "https://auth.example.com/introspect",
            "MCP_ADOBE_OAUTH_REQUIRED_SCOPES": "creative:access,offline_access creative:access",
            "MCP_ADOBE_OAUTH_CLIENT_ID": "mcp-adobe",
            "MCP_ADOBE_OAUTH_CLIENT_SECRET": "secret",
        }
        with patch.dict(os.environ, env, clear=True):
            config = OAuthResourceConfig.from_env()
        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.required_scopes, ("creative:access", "offline_access"))
        self.assertEqual(config.client_id, "mcp-adobe")
        self.assertEqual(config.client_secret, "secret")
        settings = config.auth_settings()
        self.assertEqual(settings.required_scopes, ["creative:access", "offline_access"])
        self.assertTrue(settings.validate_token_resource)

    def test_config_rejects_insecure_remote_urls(self) -> None:
        with self.assertRaisesRegex(ValueError, "must use https"):
            OAuthResourceConfig(
                issuer_url="http://auth.example.com",
                resource_url="https://creative.example.com/mcp",
                introspection_endpoint="https://auth.example.com/introspect",
            )

    def test_introspection_maps_active_token_and_basic_auth(self) -> None:
        config = OAuthResourceConfig(
            issuer_url="https://auth.example.com",
            resource_url="https://creative.example.com/mcp",
            introspection_endpoint="https://auth.example.com/introspect",
            client_id="mcp-adobe",
            client_secret="secret",
        )
        fake = _AsyncClient(
            _Response(
                200,
                {
                    "active": True,
                    "client_id": "chatgpt-client",
                    "scope": "creative:access offline_access",
                    "aud": ["other", "https://creative.example.com/mcp"],
                    "sub": "user-123",
                    "exp": "1900000000",
                },
            )
        )
        with patch("httpx2.AsyncClient", return_value=fake):
            token = asyncio.run(IntrospectionTokenVerifier(config).verify_token("opaque-token"))
        self.assertIsNotNone(token)
        assert token is not None
        self.assertEqual(token.client_id, "chatgpt-client")
        self.assertEqual(token.scopes, ["creative:access", "offline_access"])
        self.assertEqual(token.resource, "https://creative.example.com/mcp")
        self.assertEqual(token.subject, "user-123")
        self.assertEqual(token.expires_at, 1900000000)
        self.assertEqual(fake.posts[0][0], "https://auth.example.com/introspect")
        self.assertEqual(fake.posts[0][1]["data"], {"token": "opaque-token"})
        self.assertEqual(fake.posts[0][1]["auth"], ("mcp-adobe", "secret"))

    def test_introspection_rejects_inactive_or_bad_response(self) -> None:
        config = OAuthResourceConfig(
            issuer_url="https://auth.example.com",
            resource_url="https://creative.example.com/mcp",
            introspection_endpoint="https://auth.example.com/introspect",
        )
        inactive = _AsyncClient(_Response(200, {"active": False}))
        with patch("httpx2.AsyncClient", return_value=inactive):
            self.assertIsNone(asyncio.run(IntrospectionTokenVerifier(config).verify_token("dead")))

        failing = _AsyncClient(_Response(500, {}))
        with patch("httpx2.AsyncClient", return_value=failing):
            self.assertIsNone(asyncio.run(IntrospectionTokenVerifier(config).verify_token("bad")))


if __name__ == "__main__":
    unittest.main()
