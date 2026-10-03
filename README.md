# MCP Adobe Creative Gateway

A client-neutral MCP gateway for Adobe creative applications. The project is designed to expose one normalized control plane to MCP-capable clients while reusing existing Adobe integrations wherever they are mature enough.

## Project goals

- One MCP-facing gateway for multiple Adobe desktop applications.
- Reuse proven community implementations instead of rewriting mature integrations.
- Normalize common creative operations while preserving application-specific capabilities.
- Keep risky write operations observable, policy-gated, and reversible where the host application exposes a verified undo primitive.
- Support Windows first, with macOS compatibility where adopted upstream adapters provide it.
- Require real application evidence before claiming desktop E2E PASS.

## Initial application scope

1. Adobe Photoshop
2. Adobe Illustrator
3. Adobe XD live read plus approval-gated write control through a local UXP bridge
4. Premiere Pro, After Effects, and InDesign after the first three desktop applications are stable

## Reuse baseline

The audited upstream snapshots are:

- `mikechambers/adb-mcp@afe5d09cdbdd4cc60434dce6b3f46fdafe15a21c` — multi-application architecture reference.
- `alisaitteke/photoshop-mcp@ecd502c666f0e5b3889d3ef7bc42e5b3eb1119c2` — primary Photoshop implementation.
- `ie3jp/illustrator-mcp-server@57c5c101a5192c61535493f39b653e6f92b8eb29` — primary Illustrator implementation.
- `stephenszpak/xd-mcp@895613f0af9b14fb1c004913ad227fbbf18e4055` — XD parser reference only.
- `dekdee/adobe-xd-mcp@fb2c767bf8a46b6a503fce90eca47fceca0a474e` — XD parser/code-generation reference only.
- `AdobeXD/plugin-docs@c1abde873604a1606a5fdd5a578fba4502a7bdfc` — authoritative XD UXP API/lifecycle reference used for the live bridge.

No audited community XD repository provided the live desktop-write bridge needed by this project, so only that missing layer is implemented locally.

The gateway does not reimplement MCP framing for adopted upstream servers. It reuses the official MCP Python SDK for stdio subprocess lifecycle, initialization, tool discovery, and tool calls.

Pinned runtime launchers currently use:

```text
Photoshop   -> npx -y @alisaitteke/photoshop-mcp@1.7.32
Illustrator -> npx -y illustrator-mcp-server@1.10.3
```

See `docs/UPSTREAM_AUDIT.md` and `docs/ADOPTION_PLAN.md` for audit evidence and adoption decisions.

## Architecture

```text
MCP-capable client
       |
       v
Adobe Creative MCP Gateway
       |
       +----------------------+----------------------+
       |                      |                      |
       v                      v                      v
 Photoshop adapter      Illustrator adapter       XD adapter
       |                      |                      |
 official MCP SDK       official MCP SDK      local WebSocket
       |                      |                127.0.0.1:8765
       v                      v                      |
 Photoshop MCP          Illustrator MCP             v
       |                      |              XD UXP panel plugin
       v                      v                      |
  Photoshop              Illustrator                v
                                                   XD
```

The XD bridge binds to loopback only. It is not exposed on the LAN.

## Current implemented surface

### Photoshop

Common mappings include health, capabilities, document state/preview, create, open, save, export, and undo. Arbitrary native script remains default-deny.

### Illustrator

Common mappings include document info/structure, selection, create, open, save, export, PDF export, and undo.

### Adobe XD

The implemented XD UXP bridge provides live read operations:

- `xd.health`
- `xd.document.info`
- `xd.selection.get`
- `xd.queue.status`

and approval-queued mutations:

- `xd.queue.rectangle_create`
- `xd.queue.text_create`
- `xd.queue.selection_resize`
- `xd.queue.selection_fill`

Adobe XD only permits `application.editDocument()` to begin from an explicit plugin UI action. Therefore an MCP/network callback never edits the document directly. A requested mutation is queued, the panel shows the pending count, and the user clicks **Apply pending**. The plugin then applies the queued batch inside one XD edit operation. If that edit throws, XD atomically rolls back the batch.

No documented programmatic XD undo primitive was found in the audited API surface, so the gateway deliberately reports `undo_supported=false` for XD instead of inventing rollback support.

## Common safety / reliability rules

- application bridges stay local by default;
- inspect state/capabilities before mutation;
- arbitrary native script execution is default-deny;
- save/export never overwrites an existing file implicitly;
- timeout of a mutating call is UNKNOWN, not automatically safe to retry;
- transport success is not PASS until postconditions are verified where possible;
- undo/rollback capability is explicit metadata, not assumed;
- every adopted adapter records its upstream repository and pinned snapshot;
- normal push CI never writes into a real Adobe desktop application.

## Development

Python 3.11+ is supported. Windows CI currently uses `uv 0.12.17` with CPython 3.12.

```powershell
uv sync --python 3.12
uv run python -m unittest discover -s tests -v
```

The latest verified Windows baseline contains 47 passing tests, including:

- gateway policy/regression coverage;
- Photoshop and Illustrator adapter/transport tests;
- XD adapter tests;
- a real loopback WebSocket handshake/request/response test;
- PowerShell parser validation for every `scripts/*.ps1` helper;
- XD `manifest v4` and `main.js` static validation in CI.

## Windows CI versus real Adobe E2E

`.github/workflows/adobe-windows-e2e.yml` intentionally separates safe CI from real desktop automation.

A normal push performs toolchain setup, unit/regression tests, inventory, and XD plugin static validation. It never creates or edits a Photoshop, Illustrator, or XD document.

Manual `workflow_dispatch` supports these inputs:

- `run_adobe_live=true` — allow live Photoshop/Illustrator E2E on an interactive desktop runner;
- `xd_live=true` — additionally run live XD bridge read E2E;
- `xd_write=true` — additionally queue an XD test rectangle and require an **Apply pending** click before PASS.

## Prepare the MRCAO Windows machine for live E2E

The repository-scoped runner is installed at `D:\actions-runner-adobe`. Normal CI currently runs it as `NT AUTHORITY\NETWORK SERVICE`, which is suitable for software tests but not for desktop Adobe GUI/COM automation.

From an elevated PowerShell in the logged-in Windows desktop session, run:

```powershell
powershell -ExecutionPolicy Bypass -File "D:\actions-runner-adobe\_work\MCP_adobe\MCP_adobe\scripts\prepare_adobe_live_e2e.ps1"
```

This helper:

1. checks Photoshop, Illustrator, and Adobe XD from the logged-in user context;
2. installs/updates only the `MCPAdobeBridge` XD development plugin;
3. stops/disables only the `MCP_adobe` service listener under `D:\actions-runner-adobe`;
4. launches that same registered GitHub runner interactively;
5. attempts to launch Adobe XD.

It does not modify the separate AWS Simulator or WorkSpace runners on the same machine.

Keep the new runner console open. In Adobe XD:

1. open or create a test document;
2. if XD was already open, use `Plugins > Development > Reload Plugins` or `Ctrl+Shift+R`;
3. open `Plugins > MCP Adobe Bridge` and keep the panel visible.

The XD development plugin source is under `adobe-xd-plugin/`. The installer uses the current user's XD `develop` folder and replaces only its own `MCPAdobeBridge` directory.

## Direct smoke commands

Photoshop and Illustrator read-only smoke probes:

```powershell
uv run python scripts/real_e2e.py photoshop
uv run python scripts/real_e2e.py illustrator
```

Explicit write verification:

```powershell
uv run python scripts/real_e2e.py photoshop --write --output-dir C:\Temp\mcp_adobe_photoshop
uv run python scripts/real_e2e.py illustrator --write --output-dir C:\Temp\mcp_adobe_illustrator
```

XD live read probe after the bridge panel is open:

```powershell
uv run python scripts/xd_real_e2e.py
```

XD approval-gated write probe:

```powershell
uv run python scripts/xd_real_e2e.py --write --approval-timeout 90
```

The write probe queues a small rectangle named `MCP_ADOBE_E2E_RECT`. It only reports write PASS after the user clicks **Apply pending** in the XD panel and the bridge reports the operation as applied. A timeout is reported as BLOCKED, not PASS.

## Current verification boundary

Implemented and software-verified:

- Photoshop gateway adapter and pinned upstream launcher;
- Illustrator gateway adapter and pinned upstream launcher;
- Adobe XD local UXP/WebSocket bridge with approval-gated writes;
- Windows self-hosted CI on the MRCAO runner;
- 47/47 current Windows tests passing;
- XD plugin manifest/JavaScript static validation passing.

Not yet claimed:

- real Photoshop desktop E2E PASS from the target interactive Windows user session;
- real Illustrator desktop E2E PASS from the target interactive Windows user session;
- real Adobe XD UXP bridge live read/write E2E PASS on the target interactive session;
- production E2E from specific Claude and OpenAI client products.

A real desktop PASS requires the corresponding Adobe application to be visible and controllable from the interactive runner account. Service-mode CI evidence is not substituted for that result.
