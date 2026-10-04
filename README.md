# MCP Adobe Creative Gateway

A client-neutral MCP gateway for Adobe creative applications. The project reuses mature existing Adobe integrations where possible and implements only the missing normalization, policy, transport, XD bridge, verification, and remote-auth layers.

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

## Operation outcome contract

Adapter results remain backward compatible: the existing `ok` and `result` fields are preserved. Mutation results now additionally report an explicit `outcome` and `verification` object.

```text
read
  -> read operation; write verification is not applicable

verified
  -> an observable postcondition was verified

accepted_unverified
  -> downstream call returned, but no deterministic postcondition was observed

pending_user_approval
  -> Adobe XD queued the mutation and still requires Apply pending in the XD panel
```

`ok=true` means the downstream call returned successfully. It does **not** by itself mean that the requested state change was verified.

For Photoshop and Illustrator file writes, the gateway snapshots the target file before the call and only reports `verified` when it observes a new file or a changed existing file afterwards. A missing output or unchanged pre-existing file remains `accepted_unverified` instead of being promoted to PASS.

Reversible/non-file writes currently report `accepted_unverified` unless a deterministic postcondition exists. Mutating transport timeouts remain `UNKNOWN` exceptions and must be inspected before retrying.

XD network callbacks only queue mutations; queued writes report `pending_user_approval` until the user explicitly applies the batch in the panel.

## Claude Desktop MCPB package

The repository can produce a self-contained Claude Desktop MCPB bundle containing the gateway source/runtime metadata while continuing to resolve the pinned Photoshop and Illustrator upstream MCP packages at runtime.

Build and validate the bundle:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_mcpb.ps1
```

Expected output:

```text
dist\mcp-adobe-creative-gateway.mcpb
```

Exercise the packaged runtime without claiming real Adobe desktop E2E:

```powershell
uv run python scripts/smoke_mcpb.py dist/mcp-adobe-creative-gateway.mcpb --exercise-adapters
```

The smoke test validates archive contents, starts the gateway from the extracted package, verifies the four-tool MCP surface, and discovers Photoshop/Illustrator/XD adapter metadata. Adapter `connected` state is reported as evidence but is not treated as a desktop-E2E PASS unless `--require-connected <application>` is explicitly requested. The complete packaged runtime exercise is bounded by a timeout so an upstream process cannot hang CI indefinitely.

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

## Safe remote deployment probe

Installed command:

```powershell
uv run mcp-adobe-remote-probe --url https://creative.example.com/mcp
```

It verifies the public OAuth/MCP boundary without executing any Adobe tool: anonymous `401`, same-origin Protected Resource Metadata, metadata `200`, resource binding, authorization-server metadata, and scopes. With a temporary token supplied through `MCP_ADOBE_PROBE_TOKEN`, it can additionally verify authenticated MCP `tools/list`.

The probe rejects cross-origin metadata pointers before fetching them, never prints the bearer token, and rejects non-loopback plain HTTP. See `docs/CHATGPT_REMOTE.md` for the authenticated and JSON-mode commands.

## Remote security audit

OAuth-protected Streamable HTTP uses a redacted JSONL security-decision audit sink. It records the tool, allow/deny decision, application/capability, bounded denial reason, and OAuth subject/client/scopes when available.

Raw bearer tokens and tool arguments are deliberately outside the audit payload API and regression-tested not to appear in emitted JSONL. `decision=allowed` means policy allowed the request to proceed; it is not a claim that the downstream Adobe operation completed successfully.

The default audit destination is process `stderr`. Persistent bounded rotation can be enabled without changing the payload:

```text
MCP_ADOBE_AUDIT_PATH=C:\ProgramData\MCPAdobe\security-audit.jsonl
MCP_ADOBE_AUDIT_MAX_BYTES=10485760
MCP_ADOBE_AUDIT_BACKUP_COUNT=5
```

The file sink creates parent directories as needed, rotates to numbered backups, caps the number of retained backups, flushes every line, and remains token/argument-redacted. Invalid audit size/count values or filesystem setup failures stop OAuth HTTP startup with a concise `Invalid MCP Adobe audit configuration` error instead of an unhandled traceback. See `docs/CHATGPT_REMOTE.md` for deployment guidance.

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
- `ok=true` is not treated as verified operation completion;
- mutating timeout is `UNKNOWN`, not automatically safe to retry;
- transport success is not operation PASS until postconditions are verified where possible;
- undo/rollback capability is explicit metadata;
- high-risk actions use a separate top-level tool and explicit authorization flags;
- remote security audit never serializes bearer tokens or tool arguments;
- invalid audit persistence configuration fails closed before the remote MCP server starts;
- packaged smoke does not substitute package bootstrap for live Adobe desktop connectivity;
- normal push CI never writes into a real Adobe desktop application.

## Development and verification

Python 3.11+ is supported. Windows CI currently uses `uv 0.12.17` with CPython 3.12. The workflow uses current Node-24-based official GitHub actions while continuing to provision application Node 20 for the pinned Adobe upstream MCPs.

```powershell
uv sync --python 3.12
uv run python -m unittest discover -s tests -v
```

Latest verified software baseline:

```text
GitHub Actions run #55
code head: fc767fd37ec67dbe07f165c45e4860b16913dbc1
95/95 tests PASS
Claude Desktop MCPB validate/pack PASS
packaged MCP tools/list PASS
packaged Photoshop/Illustrator/XD adapter discovery PASS
MCPB artifact upload PASS
XD manifest/main.js static validation PASS
official GitHub Actions v7 runtime migration PASS
```

Coverage includes:

- gateway policy/risk regression tests;
- Photoshop and Illustrator adapter/transport tests;
- operation outcome/postcondition tests for verified file creation, unchanged/missing outputs, reversible writes, reads, and XD approval-pending state;
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
- OAuth/OIDC provider compatibility preflight and installed console entrypoint;
- safe remote endpoint probe, deterministic same-origin metadata enforcement, installed probe command, and token non-leak checks;
- authenticated security audit redaction, persistent JSONL rotation, bounded backup checks, and clean fail-closed startup for invalid audit configuration/filesystem failures;
- Windows bootstrap/config generation tests;
- Claude Desktop MCPB manifest validation, package creation, packaged runtime smoke, adapter discovery, and artifact upload;
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
- safe deployed-endpoint boundary probe;
- redacted OAuth security-decision audit with optional bounded rotating persistence and fail-closed configuration validation;
- backward-compatible operation outcome/postcondition envelope;
- Claude Desktop MCPB package validation and packaged runtime smoke;
- Photoshop and Illustrator adapters over pinned upstream MCPs;
- XD local UXP/WebSocket bridge;
- **95/95 Windows tests passing on run #55**.

Still not claimed:

- real Photoshop desktop E2E from an interactive Windows user session;
- real Illustrator desktop E2E from an interactive Windows user session;
- real XD UXP live read/write E2E from the target interactive session;
- production E2E using a specific external OAuth provider and ChatGPT account/workspace;
- production E2E from a specific Claude client product.

Those boundaries are intentional: software simulation, transport tests, package bootstrap, and local/mock OAuth evidence are not substituted for real external-account or desktop evidence.
