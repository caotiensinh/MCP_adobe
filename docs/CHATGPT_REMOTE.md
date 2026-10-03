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

## Remote permission profiles

The current MCP Python SDK publishes the resource server's `required_scopes` as the Protected Resource Metadata `scopes_supported`. The gateway therefore uses explicit **deployment profiles** instead of hidden per-tool optional scopes that a remote client may not know to request.

Choose one scope set for the deployed endpoint:

### Read-only remote profile — recommended default

```text
MCP_ADOBE_OAUTH_REQUIRED_SCOPES=creative:access
```

Remote clients can authenticate, discover the gateway, and use read-class operations. `creative_write` and `creative_authorized_write` fail before the Adobe runtime is invoked.

### Normal-write remote profile

```text
MCP_ADOBE_OAUTH_REQUIRED_SCOPES=creative:access creative:write
```

This enables `creative_write` for reversible/file-write capabilities. `creative_authorized_write` remains disabled.

### Full high-risk remote profile

```text
MCP_ADOBE_OAUTH_REQUIRED_SCOPES=creative:access creative:write creative:high-risk
```

This enables the high-risk top-level route, but it does **not** bypass operation-level policy. Destructive/native-script/external-AI operations still require the corresponding explicit flags such as `allow_native_script=true`.

Profiles are hierarchical: do not configure `creative:high-risk` without `creative:write`.

The configured list is advertised by Protected Resource Metadata and is enforced by the MCP SDK's HTTP bearer middleware. A token missing any globally required scope is rejected with HTTP `403 insufficient_scope` before tool execution.

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

## Safe deployed-endpoint probe

After the HTTPS/tunnel/reverse-proxy boundary exists, verify it before attempting any Adobe operation:

```powershell
uv run mcp-adobe-remote-probe --url https://creative.example.com/mcp
```

Boundary-only mode verifies:

1. an anonymous MCP POST is rejected with HTTP `401`;
2. `WWW-Authenticate` contains a Protected Resource Metadata pointer;
3. the metadata pointer stays on the same MCP resource origin;
4. Protected Resource Metadata returns HTTP `200`;
5. metadata `resource` matches the probed MCP URL;
6. authorization-server and scope metadata are present.

The probe does **not** execute `creative_read`, `creative_write`, or `creative_authorized_write`.

To additionally verify authenticated MCP `tools/list`, provide a temporary bearer token through an environment variable rather than a command-line argument:

```powershell
$env:MCP_ADOBE_PROBE_TOKEN = "<temporary bearer token>"
uv run mcp-adobe-remote-probe --url https://creative.example.com/mcp --require-token
```

Machine-readable mode:

```powershell
uv run mcp-adobe-remote-probe --url https://creative.example.com/mcp --require-token --json
```

The token is never printed or returned in probe output. A cross-origin `resource_metadata` pointer is rejected before it is fetched.

For local test-only verification:

```powershell
uv run mcp-adobe-remote-probe --url http://127.0.0.1:8787/mcp --allow-loopback-http
```

Non-loopback plain HTTP is rejected.

## Remote security audit

OAuth-protected Streamable HTTP automatically enables the JSONL security audit sink. Local stdio and unauthenticated loopback development use the null sink.

Each audit event records only the security decision context:

- tool name;
- decision (`allowed` or `denied`);
- application and capability when present;
- a bounded reason code for profile denials;
- OAuth subject, client ID, and scopes when an authenticated principal exists.

The raw bearer token and tool arguments are intentionally not accepted by the audit payload builder, so they cannot be serialized accidentally. Regression tests explicitly use sentinel bearer-token and secret argument values and verify that neither appears in emitted JSONL.

`decision=allowed` means the gateway/profile policy allowed the request to proceed. It is **not** a claim that the downstream Adobe operation completed successfully; runtime/postcondition verification remains the source of operation outcome.

For write paths, the security decision is emitted before invoking the Adobe runtime. This keeps audit availability on the pre-side-effect boundary instead of creating a situation where an Adobe mutation succeeds but a later audit-write failure makes the client believe the operation failed and retry it.

### Persistent rotating audit files

By default, the OAuth security audit is emitted to process `stderr`, which works well with service managers, container logging, and centralized log collectors.

For a standalone Windows/service deployment, set a persistent path:

```text
MCP_ADOBE_AUDIT_PATH=C:\ProgramData\MCPAdobe\security-audit.jsonl
MCP_ADOBE_AUDIT_MAX_BYTES=10485760
MCP_ADOBE_AUDIT_BACKUP_COUNT=5
```

`MCP_ADOBE_AUDIT_MAX_BYTES` defaults to `10485760` bytes (10 MiB) and `MCP_ADOBE_AUDIT_BACKUP_COUNT` defaults to `5`. Parent directories are created as needed. When the active JSONL file would exceed the configured bound, the sink rotates it to `.1`, shifts older backups upward, and deletes the oldest file beyond the configured backup count.

The rotating file path does not change the audit payload: bearer-token values and tool arguments remain excluded. The file sink is thread-safe and flushes each audit line after writing so a long-running service does not depend on process shutdown to persist the security decision.

Choose the audit directory and retention values according to the host's access-control, backup, and privacy requirements. Do not place the audit file inside a public web root or a source checkout that is routinely committed/uploaded.

## What the MCP endpoint publishes

When OAuth is configured, the MCP SDK publishes Protected Resource Metadata at:

```text
/.well-known/oauth-protected-resource/mcp
```

An unauthenticated MCP request is rejected with HTTP 401 and a `WWW-Authenticate` challenge that points to that metadata. A bearer token must pass token introspection, configured required-scope checks, and resource/audience validation before a tool executes.

The repository regression suite verifies this sequence with real HTTP processes:

```text
GET  /.well-known/oauth-protected-resource/mcp -> 200
POST /mcp without bearer token                 -> 401
POST /mcp with active audience-bound token     -> 200 + MCP tools/list
```

The full-profile regression additionally verifies:

```text
metadata scopes -> creative:access creative:write creative:high-risk
access-only token against full-profile endpoint -> 403 insufficient_scope
full-scope token                                -> 200 + MCP tools/list
```

## ChatGPT connection checklist

1. Decide the minimum remote permission profile; start with `creative:access` unless writes are actually required.
2. Configure an OAuth/OIDC provider for the MCP resource and its public HTTPS resource URL.
3. Make sure the provider supports authorization code + PKCE with `S256` and a compatible client-registration mode.
4. Prefer refresh-token support (`offline_access`) for a persistent connection.
5. Set the `MCP_ADOBE_OAUTH_*` environment variables on the gateway host.
6. Configure `MCP_ADOBE_AUDIT_PATH` when local persistent security logs are required; otherwise collect process `stderr` with the service/logging platform.
7. Run `mcp-adobe-oauth-preflight`; do not continue if it reports a FAIL.
8. Start `mcp-adobe` on loopback with Streamable HTTP.
9. Expose the loopback MCP URL through Secure MCP Tunnel or a TLS reverse proxy so the remote client sees the exact HTTPS `MCP_ADOBE_OAUTH_RESOURCE_URL`.
10. Run `mcp-adobe-remote-probe` against the public URL; when a temporary token is available, require authenticated `tools/list` before a production client is enabled.
11. Add that HTTPS MCP URL in the supported ChatGPT MCP/custom-app flow and complete OAuth authorization.
12. Inspect `creative_discover.oauth_policy` and the discovered tool list before enabling any write-capable workflow.
13. Keep `creative_authorized_write` subject to explicit high-risk flags; remote OAuth authentication does not bypass gateway write policy.

## Local Claude / Codex / Cursor use

OAuth is an HTTP boundary. Local stdio clients should continue to launch:

```powershell
uv run mcp-adobe --transport stdio
```

The stdio process boundary and the local OS user are the security boundary for that mode. OAuth deployment-profile gates do not restrict the local no-OAuth stdio workflow; the existing gateway risk policy still applies.

## Verification boundary

GitHub Actions run `#51` on code head `5442e3da78e834fa6f78e4718c39c68aa8d7e3e5` completed the Windows test suite with **84/84 tests PASS**. The same exact-head run also passed MCPB manifest validation/packaging, packaged MCP runtime `tools/list`, packaged adapter discovery, artifact upload, and XD static validation.

Software verification now covers MCP transports, OAuth challenge and Protected Resource Metadata, RFC 7662 introspection, audience/resource validation, deployment-profile scopes, `403 insufficient_scope`, provider preflight, the safe remote deployment probe, redacted authenticated security-decision auditing, bounded rotating audit persistence, and packaged Claude Desktop MCP runtime smoke verification.

It does not prove a specific ChatGPT account/workspace connection or a real Adobe desktop write. Those require the actual external account/provider and an interactive Adobe desktop session respectively.
