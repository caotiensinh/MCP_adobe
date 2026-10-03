# MCP Adobe Creative Gateway

A client-neutral MCP gateway for Adobe creative applications. The project reuses mature existing Adobe integrations where possible and implements only the missing normalization, policy, transport, XD bridge, and remote-auth layers.

## Current scope

1. Adobe Photoshop
2. Adobe Illustrator
3. Adobe XD
4. Premiere Pro, After Effects, and InDesign after the first three desktop applications are stable

The current gateway is designed for both:

- local MCP clients over `stdio`;
- remote MCP clients over Streamable HTTP with an OAuth-protected deployment boundary.

## Reuse baseline

Audited upstream snapshots include:

- `mikechambers/adb-mcp@afe5d09cdbdd4cc60434dce6b3f46fdafe15a21c` — multi-application architecture reference;
- `alisaitteke/photoshop-mcp@ecd502c666f0e5b3889d3ef7bc42e5b3eb1119c2` — primary Photoshop implementation;
- `ie3jp/illustrator-mcp-server@57c5c101a5192c61535493f39b653e6f92b8eb29` — primary Illustrator implementation;
- `stephenszpak/xd-mcp@895613f0af9b14fb1c004913ad227fbbf18e4055` and `dekdee/adobe-xd-mcp@fb2c767bf8a46b6a503fce90eca47fceca0a474e` — XD parser/code-generation references;
- `AdobeXD/plugin-docs@c1abde873604a1606a5fdd5a578fba4502a7bdfc` — authoritative XD UXP lifecycle/API reference used by the live bridge.

Pinned runtime launchers:

```text
Photoshop   -> npx -y @alisaitteke/photoshop-mcp@1.7.32
Illustrator -> npx -y illustrator-mcp-server@1.10.3
```

No audited community XD project supplied the required live desktop-write bridge, so that missing layer is implemented locally.

See `docs/UPSTREAM_AUDIT.md` and `docs/ADOPTION_PLAN.md` for the reuse decisions.

## Architecture

```text
Claude / Codex / Cursor                  ChatGPT / remote MCP client
        |                                           |
      stdio                                  HTTPS + OAuth
        |                                           |
        +-------------------+-----------------------+
                            |
                            v
                 Adobe Creative MCP Gateway
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
   Photoshop adapter  Illustrator adapter   XD adapter
          |                 |                 |
   official MCP SDK    official MCP SDK   local WebSocket
          |                 |           127.0.0.1:8765
          v                 v                 |
   Photoshop MCP      Illustrator MCP         v
          |                 |          XD UXP panel plugin
          v                 v                 |
      Photoshop         Illustrator           v
                                              XD
```

The Adobe application bridges remain local. The top-level HTTP gateway defaults to loopback.

## Unified MCP server

Installed command:

```text
mcp-adobe
```

The top-level surface intentionally exposes only four policy-separated tools:

- `creative_discover` — read-only application/capability/risk discovery;
- `creative_read` — read-class capabilities only;
- `creative_write` — reversible/file writes only, with overwrite opt-in;
- `creative_authorized_write` — separate path for destructive, native-script, external-AI, and other explicitly authorized high-risk actions.

A normal write cannot silently become a native-script or destructive operation.

### Local stdio

```powershell
uv run mcp-adobe --transport stdio
```

### Local Streamable HTTP

```powershell
uv run mcp-adobe --transport streamable-http --host 127.0.0.1 --port 8787 --path /mcp
```

Local endpoint:

```text
http://127.0.0.1:8787/mcp
```

## OAuth-protected remote MCP

The gateway implements the MCP resource-server side using the official MCP Python SDK's `TokenVerifier` and `AuthSettings` support.

It does **not** implement its own login page or token issuer. Use an existing OAuth/OIDC authorization server and configure RFC 7662 token introspection.

Required environment variables:

```text
MCP_ADOBE_OAUTH_ISSUER_URL=https://auth.example.com
MCP_ADOBE_OAUTH_RESOURCE_URL=https://creative.example.com/mcp
MCP_ADOBE_OAUTH_INTROSPECTION_ENDPOINT=https://auth.example.com/oauth/introspect
MCP_ADOBE_OAUTH_REQUIRED_SCOPES=creative:access
```

Optional introspection credentials:

```text
MCP_ADOBE_OAUTH_CLIENT_ID=mcp-adobe-resource-server
MCP_ADOBE_OAUTH_CLIENT_SECRET=<store outside Git>
```

A placeholder-only example is available at `examples/oauth.env.example`.

### Remote OAuth permission profiles

Remote permissions are configured as an explicit deployment profile so the scopes advertised in MCP Protected Resource Metadata match the scopes that clients must request:

```text
read-only remote:
creative:access

normal remote writes:
creative:access creative:write

full high-risk remote surface:
creative:access creative:write creative:high-risk
```

`creative:access` is the recommended default. A read-only profile blocks both write tools before the Adobe runtime is invoked. The normal-write profile enables `creative_write` while keeping `creative_authorized_write` disabled. The full profile enables the high-risk route, but destructive/native-script/external-AI operations still require their existing explicit operation flags.

A token missing any scope required by the deployed profile is rejected by the MCP HTTP bearer middleware with `403 insufficient_scope` before tool execution.

When OAuth is enabled, the MCP SDK publishes Protected Resource Metadata and rejects unauthenticated MCP requests before any tool executes.

Direct non-loopback HTTP is fail-closed unless OAuth is configured. The preferred deployment remains:

```text
remote client
    -> HTTPS/OAuth
    -> Secure MCP Tunnel or TLS reverse proxy
    -> 127.0.0.1:8787/mcp
```

See `docs/CHATGPT_REMOTE.md` for the complete remote deployment checklist.

## OAuth provider preflight

Installed command:

```powershell
uv run mcp-adobe-oauth-preflight
```

Machine-readable mode:

```powershell
uv run mcp-adobe-oauth-preflight --json
```

The preflight validates provider discovery metadata before deployment, including:

- exact issuer matching;
- authorization/token endpoints;
- PKCE `S256`;
- token-endpoint authentication methods;
- required MCP scopes;
- CIMD/Dynamic Client Registration availability or predefined-client warning;
- `offline_access` availability;
- authorization-response issuer support;
- configured introspection endpoint consistency.

Hard incompatibilities exit non-zero. Warnings are reported without pretending they are failures.

## Adobe XD bridge

The local XD UXP/WebSocket bridge supports live reads:

- `xd.health`
- `xd.document.info`
- `xd.selection.get`
- `xd.queue.status`

Approval-queued mutations include:

- `xd.queue.rectangle_create`
- `xd.queue.text_create`
- `xd.queue.selection_resize`
- `xd.queue.selection_fill`

XD requires `application.editDocument()` to start from an explicit plugin UI action. Therefore MCP/network callbacks queue mutations and the user applies them from the XD panel with **Apply pending**. The queued batch is applied inside one edit operation.

No documented programmatic XD undo primitive was found in the audited API surface, so the gateway reports `undo_supported=false` for XD instead of inventing rollback support.

## Safety and reliability rules

- application bridges stay local by default;
- remote HTTP is OAuth-protected before non-loopback exposure;
- remote permissions use explicit read/write/high-risk deployment profiles;
- inspect state/capabilities before mutation;
- arbitrary native script execution is default-deny;
- save/export never overwrites implicitly;
- mutating timeout is `UNKNOWN`, not automatically safe to retry;
- transport success is not operation PASS until postconditions are verified where possible;
- undo/rollback capability is explicit metadata;
- high-risk actions use a separate top-level tool and explicit authorization flags;
- normal push CI never writes into a real Adobe desktop application.

## Development and verification

Python 3.11+ is supported. Windows CI currently uses `uv 0.12.17` with CPython 3.12.

```powershell
uv sync --python 3.12
uv run python -m unittest discover -s tests -v
```

Latest verified software baseline:

```text
GitHub Actions run #36
code head: 42e50743ad05d3c974f04a23b49a825d90a07f08
76/76 tests PASS
XD manifest/main.js static validation PASS
```

Coverage includes:

- gateway policy/risk regression tests;
- Photoshop and Illustrator adapter/transport tests;
- top-level MCP contract and annotations through the official MCP client;
- real subprocess stdio handshake and `tools/list`;
- real subprocess Streamable HTTP handshake and `tools/list`;
- OAuth Protected Resource Metadata HTTP `200`;
- anonymous protected MCP request HTTP `401`;
- active audience-bound bearer token -> HTTP `200` + MCP `tools/list`;
- full-profile metadata advertising `creative:access creative:write creative:high-risk`;
- insufficient-scope token -> HTTP `403 insufficient_scope`;
- full-scope token -> HTTP `200` + MCP `tools/list`;
- read-only / normal-write / full high-risk server profile gates;
- fail-closed non-loopback HTTP without OAuth;
- RFC 7662 introspection behavior;
- OAuth/OIDC provider compatibility preflight;
- installed `mcp-adobe-oauth-preflight` console entrypoint on Windows;
- XD loopback WebSocket handshake/request/response;
- PowerShell helper syntax validation;
- XD plugin static validation.

## Real Adobe desktop E2E

`.github/workflows/adobe-windows-e2e.yml` separates safe push CI from real desktop automation.

Manual `workflow_dispatch` supports:

- `run_adobe_live=true` — live Photoshop/Illustrator E2E;
- `xd_live=true` — live XD bridge read E2E;
- `xd_write=true` — queue an XD test mutation and require **Apply pending** before write PASS.

The repository-scoped runner is installed at:

```text
D:\actions-runner-adobe
```

Current inventory still shows the MCP Adobe runner as `NT AUTHORITY\NETWORK SERVICE` with `UserInteractive=False`. In that service session Photoshop and Illustrator are not visible, while Adobe XD is installed. Therefore no real Photoshop/Illustrator/XD desktop PASS is claimed from push CI.

To prepare only the MCP Adobe runner for interactive desktop E2E, from an elevated PowerShell in the logged-in Windows desktop session run:

```powershell
powershell -ExecutionPolicy Bypass -File "D:\actions-runner-adobe\_work\MCP_adobe\MCP_adobe\scripts\prepare_adobe_live_e2e.ps1"
```

The helper does not modify the separate AWS Simulator or WorkSpace runners on the same machine.

### Direct Adobe probes

```powershell
uv run python scripts/real_e2e.py photoshop
uv run python scripts/real_e2e.py illustrator

uv run python scripts/real_e2e.py photoshop --write --output-dir C:\Temp\mcp_adobe_photoshop
uv run python scripts/real_e2e.py illustrator --write --output-dir C:\Temp\mcp_adobe_illustrator

uv run python scripts/xd_real_e2e.py
uv run python scripts/xd_real_e2e.py --write --approval-timeout 90
```

The XD write probe reports PASS only after the queued operation is explicitly applied and the bridge confirms it. Timeout is BLOCKED, not PASS.

## Verification boundary

Software-verified now:

- unified MCP gateway;
- stdio and Streamable HTTP transports;
- OAuth resource-server protection and token introspection;
- remote OAuth permission profiles with HTTP scope enforcement;
- remote-provider compatibility preflight;
- Photoshop and Illustrator adapters over pinned upstream MCPs;
- XD local UXP/WebSocket bridge;
- **76/76 Windows tests passing**.

Still not claimed:

- real Photoshop desktop E2E from an interactive Windows user session;
- real Illustrator desktop E2E from an interactive Windows user session;
- real XD UXP live read/write E2E from the target interactive session;
- production E2E using a specific external OAuth provider and ChatGPT account/workspace;
- production E2E from a specific Claude client product.

Those boundaries are intentional: software simulation, transport tests, and mocked token introspection are not substituted for real external-account or desktop evidence.
