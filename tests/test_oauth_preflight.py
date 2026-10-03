from __future__ import annotations

import unittest

from mcp_adobe.auth import OAuthResourceConfig
from mcp_adobe.oauth_preflight import discovery_urls, evaluate_provider_metadata, preflight_summary


class OAuthPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = OAuthResourceConfig(
            issuer_url="https://auth.example.com/tenant",
            resource_url="https://creative.example.com/mcp",
            introspection_endpoint="https://auth.example.com/tenant/introspect",
        )

    def test_discovery_urls_support_path_issuers(self) -> None:
        self.assertEqual(
            discovery_urls("https://auth.example.com/tenant"),
            (
                "https://auth.example.com/tenant/.well-known/openid-configuration",
                "https://auth.example.com/.well-known/oauth-authorization-server/tenant",
            ),
        )

    def test_compatible_provider_passes_required_checks(self) -> None:
        metadata = {
            "issuer": "https://auth.example.com/tenant",
            "authorization_endpoint": "https://auth.example.com/tenant/authorize",
            "token_endpoint": "https://auth.example.com/tenant/token",
            "introspection_endpoint": "https://auth.example.com/tenant/introspect",
            "authorization_response_iss_parameter_supported": True,
            "client_id_metadata_document_supported": True,
            "token_endpoint_auth_methods_supported": ["none", "private_key_jwt"],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": ["creative:access", "offline_access", "openid", "email"],
        }
        findings = evaluate_provider_metadata(
            self.config,
            metadata,
            source_url="https://auth.example.com/tenant/.well-known/openid-configuration",
        )
        summary = preflight_summary(findings)
        self.assertEqual(summary["fail"], 0)
        self.assertEqual(summary["warn"], 0)
        self.assertGreater(summary["pass"], 0)

    def test_missing_s256_scope_and_issuer_mismatch_fail(self) -> None:
        metadata = {
            "issuer": "https://wrong.example.com",
            "authorization_endpoint": "https://auth.example.com/authorize",
            "token_endpoint": "https://auth.example.com/token",
            "registration_endpoint": "https://auth.example.com/register",
            "token_endpoint_auth_methods_supported": ["client_secret_basic"],
            "code_challenge_methods_supported": ["plain"],
            "scopes_supported": ["offline_access"],
        }
        findings = evaluate_provider_metadata(self.config, metadata, source_url="metadata")
        failed = {item.check for item in findings if item.status == "FAIL"}
        self.assertIn("issuer", failed)
        self.assertIn("pkce_s256", failed)
        self.assertIn("required_scopes", failed)

    def test_no_cimd_or_dcr_and_no_offline_access_are_warnings(self) -> None:
        metadata = {
            "issuer": "https://auth.example.com/tenant",
            "authorization_endpoint": "https://auth.example.com/authorize",
            "token_endpoint": "https://auth.example.com/token",
            "token_endpoint_auth_methods_supported": ["none"],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": ["creative:access"],
        }
        findings = evaluate_provider_metadata(self.config, metadata, source_url="metadata")
        warned = {item.check for item in findings if item.status == "WARN"}
        self.assertIn("client_registration", warned)
        self.assertIn("refresh_access", warned)
        self.assertIn("authorization_response_iss", warned)


if __name__ == "__main__":
    unittest.main()
