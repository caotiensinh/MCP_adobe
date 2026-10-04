# Verified checkpoint

Last updated: 2026-10-04 JST

## Exact verified software head

- GitHub Actions run: `#63` (`37177808470`)
- Exact code head: `a21c09b1030fcec57c4b300cbd36208c20a03e6f`
- Windows self-hosted runner: `windows` on `MRCAO`
- Unit/regression result: **122/122 PASS**
- Claude Desktop MCPB validate/pack: **PASS**
- Packaged MCP `tools/list`: **PASS**
- Packaged Photoshop/Illustrator/XD adapter discovery: **PASS**
- MCPB packaged runtime smoke: **PASS**
- MCPB artifact upload: **PASS**
- MCPB artifact ID: `11293849010`
- Uploaded artifact SHA-256: `36c97030b94499b41e0265c3cab8ac9005d2fbe14a8662b7c2fb763ce5b632f9`
- Adobe XD manifest/main.js static validation: **PASS**

## Reliability boundaries now enforced

### 1. Transport connection is not application readiness

`AdapterInfo.connected` remains a transport-level compatibility field. It only means the downstream MCP/WebSocket transport is alive.

Client-facing `creative_discover` makes that contract explicit without probing Adobe applications:

- `connected` — retained for backward compatibility;
- `transport_connected` — explicit transport-level state;
- `connection_semantics="transport_only"`;
- `readiness_probe` — the adapter's declared application-level probe;
- `readiness_status="not_probed"` when a probe exists but discovery has not called it;
- `readiness_status="not_declared"` when no probe is declared;
- top-level `connection_contract.discovery_probes_application=false`.

This prevents a client from treating `connected=true` as evidence that Photoshop, Illustrator, or XD itself is ready.

Before a non-read capability is allowed, the built-in adapters reuse an application-level health primitive:

- Photoshop: upstream `photoshop_ping`;
- Illustrator: upstream `list_fonts(limit=1)`, which does not require an open document;
- Adobe XD: local UXP bridge `xd.health`.

Successful readiness is cached briefly to avoid probing the Adobe app on every mutation. Mutating timeout invalidates the cache.

### 2. Packaged Claude Desktop discovery enforces the same contract

`scripts/smoke_mcpb.py` fails the packaged runtime smoke if any built-in adapter regresses from the discovery contract.

The `.mcpb` artifact must expose:

- top-level `connection_contract` with `connected_means="transport_connected"`;
- `connection_semantics="transport_only"` for Photoshop, Illustrator, and XD;
- `transport_connected == connected` for backward compatibility;
- `readiness_probe="creative.health"` for all built-in adapters;
- `readiness_status="not_probed"` during discovery.

Run #63 proved this contract again against the actual packed Claude Desktop artifact. The packaged smoke reported:

```text
Photoshop:   transport_connected=true  readiness_status=not_probed
Illustrator: transport_connected=true  readiness_status=not_probed
XD:          transport_connected=false readiness_status=not_probed
```

Those transport values are not desktop-readiness claims.

### 3. Application readiness is not operation completion

Mutation results keep the backward-compatible `ok`/`result` fields and additionally report explicit outcome/verification metadata.

- `verified` — an observable postcondition was verified;
- `accepted_unverified` — the downstream call returned but deterministic completion was not observed;
- `pending_user_approval` — XD mutation is queued until **Apply pending** is clicked;
- mutating timeout remains `UNKNOWN` and must be inspected before retry.

Therefore:

```text
transport connected != application ready
application ready != operation verified
```

## One-command interactive Adobe live E2E

The verified main now includes two guarded Windows helpers:

- `scripts/dispatch_adobe_live_e2e.ps1`
- `scripts/run_adobe_live_e2e.ps1`

The one-command launcher intentionally performs GitHub authentication preflight **before** changing the dedicated MCP_adobe runner service. It then reuses the existing preparation helper to install/update the XD bridge, move only `D:\actions-runner-adobe` into the logged-in interactive desktop session, and dispatch the existing workflow with explicit live inputs.

Safety/approval behavior:

- no live workflow dispatch occurs if GitHub CLI preflight fails;
- `-XdWrite` is rejected together with `-NoXdLive`;
- default dispatch sets `run_adobe_live=true` and `xd_live=true`;
- `-XdWrite` sets `xd_write=true`, but XD mutation still cannot PASS until the user clicks **Apply pending** in the MCP Adobe Bridge panel;
- the helper does not treat service-session transport connectivity as desktop readiness.

Fresh converge evidence before merge:

- targeted run `37177709041` on MRCAO;
- `tests.test_windows_helpers`: **5/5 PASS**;
- all PowerShell helpers parse;
- guarded dispatch arguments verified with a fake `gh` executable;
- invalid XD flag combination fails closed;
- wrapper proves GitHub preflight happens before the non-interactive/runner-service guard;
- modern `Adobe.XD_*` sandbox installation test still passes.

## Adobe XD Windows package compatibility

The live-E2E preparation path supports the current Windows XD package identity observed on MRCAO as well as the legacy identity:

- current package sandboxes matching `Adobe.XD_*`;
- legacy package sandboxes matching `Adobe.CC.XD_*`;
- the actual logged-in user's XD `PackageFamilyName` is preferred when available;
- the old documented package path remains a compatibility fallback.

`prepare_adobe_live_e2e.ps1` launches XD before automatic bridge installation so a freshly installed package can create its per-user `LocalState` sandbox. The installer then resolves that sandbox and installs the local MCP Adobe Bridge into `LocalState\develop`.

## Evidence from run #63

The full exact-head log reported:

```text
Ran 122 tests in 61.822s
OK
```

The packaged runtime smoke passed against `mcp-adobe-creative-gateway.mcpb`, including the transport/readiness contract gate. The artifact was uploaded with SHA-256 `36c97030b94499b41e0265c3cab8ac9005d2fbe14a8662b7c2fb763ce5b632f9`.

The packaged runtime can launch and discover the pinned Photoshop and Illustrator downstream MCP servers, but that does **not** claim the desktop applications themselves are ready. The same run inventory reported:

```text
User=NT AUTHORITY\NETWORK SERVICE
UserInteractive=False
Photoshop=<not visible in service session>
Illustrator=<not visible in service session>
Adobe XD=57.1.12.2 installed
```

Push CI intentionally skipped all real desktop-write steps.

## Still not claimed

- real Photoshop desktop E2E from the logged-in interactive Windows session;
- real Illustrator desktop E2E from the logged-in interactive Windows session;
- real XD UXP live read/write E2E from that interactive session;
- production ChatGPT + external OAuth provider E2E;
- production Claude client + real Adobe desktop E2E.

The first three are now blocked only by running the verified one-command launcher from the logged-in MRCAO desktop session; they remain explicit blockers rather than simulated PASS results.
