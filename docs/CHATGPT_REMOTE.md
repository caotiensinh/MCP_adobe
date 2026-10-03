# ChatGPT / Remote MCP Deployment

This document covers the remote MCP boundary only. It does not change the Adobe desktop E2E requirement: Photoshop, Illustrator, and XD still need a real interactive desktop session before desktop automation can be claimed as PASS.

## Deployment model

Keep the Adobe gateway local and put the public network boundary outside it:

```text
ChatGPT / remote MCP client
          |
     HTTPS + OAuth
          |
Secure MCP Tunnel or TLS reverse proxy
          |
   127.0.0.1:8787/mcp
          |
 MCP Adobe Creative Gateway
          |
 Photoshop / Illustrator / XD adapters
```

The recommended gateway process remains loopback-bound:

```powershell
uv run mcp-adobe --transport streamable-http --host 127.0.0.1 --port 8787 --path /mcp
```

Direct non-loopback binding is fail-closed unless both `--allow-non-loopback` and a complete OAuth resource-server configuration are present. Even then, prefer a secure tunnel or TLS reverse proxy instead of exposing the Python process directly.

## OAuth model

`mcp-adobe` is an OAuth resource server. It does not implement a login page, consent screen, authorization endpoint, token endpoint, or client registration service.

Use an existing OAuth/OIDC authorization server such as an enterprise identity provider. The gateway validates bearer tokens with RFC 7662 token introspection and uses the MCP SDK's native `TokenVerifier` + `AuthSettings` support.

Required gateway environment variables:

```text
MCP_ADOBE_OAUTH_ISSUER_URL=https://auth.example.com
MCP_ADOBE_OAUTH_RESOURCE_URL=https://creative.example.com/mcp
MCP_ADOBE_OAUTH_INTROSPECTION_ENDPOINT=https://auth.example.com/oauth/introspect
MCP_ADOBE_OAUTH_REQUIRED_SCOPES=creative:access
```

Optional introspection client credentials:

```text
MCP_ADOBE_OAUTH_CLIENT_ID=mcp-adobe-resource-server
MCP_ADOBE_OAUTH_CLIENT_SECRET=<set outside the repository>
```

Never commit a real client secret.

`MCP_ADOBE_OAUTH_RESOURCE_URL` must be the canonical URL that the remote MCP client uses. For an internet-facing deployment it must be HTTPS.

## Provider compatibility preflight

Run the provider preflight before exposing the endpoint:

```powershell
uv run mcp-adobe-oauth-preflight
```

Machine-readable output:

```powershell
uv run mcp-adobe-oauth-preflight --json
```

The preflight checks the authorization-server discovery metadata for:

- exact issuer match;
- secure authorization endpoint;
- secure token endpoint;
- PKCE `S256` support;
- compatible token endpoint authentication methods;
- CIMD or Dynamic Client Registration availability, otherwise it warns that a predefined OAuth client may be required;
- the gateway's required scope(s);
- `offline_access` availability for refresh-token-capable sessions;
- authorization-response issuer support;
- consistency with the configured introspection endpoint.

Any hard incompatibility returns a non-zero exit code. Warnings do not fail the command.

## What the MCP endpoint publishes

When OAuth is configured, the MCP SDK publishes Protected Resource Metadata at:

```text
/.well-known/oauth-protected-resource/mcp
```

An unauthenticated MCP request is rejected with HTTP 401 and a `WWW-Authenticate` challenge that points to that metadata. A valid bearer token must pass token introspection, required-scope checks, and resource/audience validation before a tool executes.

The repository regression suite verifies this sequence with real HTTP processes:

```text
GET  /.well-known/oauth-protected-resource/mcp -> 200
POST /mcp without bearer token                 -> 401
POST /mcp with active audience-bound token     -> 200 + MCP tools/list
```

## ChatGPT connection checklist

1. Configure an OAuth/OIDC provider for the MCP resource and its public HTTPS resource URL.
2. Make sure the provider supports authorization code + PKCE with `S256` and a compatible client-registration mode.
3. Prefer refresh-token support (`offline_access`) for a persistent connection.
4. Set the `MCP_ADOBE_OAUTH_*` environment variables on the gateway host.
5. Run `mcp-adobe-oauth-preflight`; do not continue if it reports a FAIL.
6. Start `mcp-adobe` on loopback with Streamable HTTP.
7. Expose the loopback MCP URL through Secure MCP Tunnel or a TLS reverse proxy so the remote client sees the exact HTTPS `MCP_ADOBE_OAUTH_RESOURCE_URL`.
8. Add that HTTPS MCP URL in the supported ChatGPT MCP/custom-app flow and complete OAuth authorization.
9. Inspect the discovered tool list before enabling any write-capable workflow.
10. Keep `creative_authorized_write` subject to explicit high-risk flags; remote OAuth authentication does not bypass gateway write policy.

## Local Claude / Codex / Cursor use

OAuth is an HTTP boundary. Local stdio clients should continue to launch:

```powershell
uv run mcp-adobe --transport stdio
```

The stdio process boundary and the local OS user are the security boundary for that mode. The OAuth token verifier is not used over stdio.

## Verification boundary

Software verification proves the MCP transport, OAuth challenge, protected-resource metadata, token introspection path, audience/scope enforcement, and provider-metadata preflight.

It does not prove a specific ChatGPT account/workspace connection or a real Adobe desktop write. Those require the actual external account/provider and an interactive Adobe desktop session respectively.
