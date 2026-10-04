# Verified checkpoint

Last updated: 2026-10-04 JST

## Exact verified software head

- GitHub Actions run: `#62` (`37177148764`)
- Exact code head: `943ab0300369d27de1ddf195ddd382ffed5f9d9c`
- Windows self-hosted runner: `windows` on `MRCAO`
- Unit/regression result: **119/119 PASS**
- Claude Desktop MCPB validate/pack: **PASS**
- Packaged MCP `tools/list`: **PASS**
- Packaged Photoshop/Illustrator/XD adapter discovery: **PASS**
- MCPB packaged runtime smoke: **PASS**
- MCPB artifact upload: **PASS**
- MCPB artifact ID: `11293438904`
- Uploaded artifact SHA-256: `17a0b1ca08e2bab03d9152e920647681ad154f53377b236b9ad870d8da63eead`
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

`scripts/smoke_mcpb.py` now fails the packaged runtime smoke if any built-in adapter regresses from the discovery contract.

The `.mcpb` artifact must expose:

- top-level `connection_contract` with `connected_means="transport_connected"`;
- `connection_semantics="transport_only"` for Photoshop, Illustrator, and XD;
- `transport_connected == connected` for backward compatibility;
- `readiness_probe="creative.health"` for all built-in adapters;
- `readiness_status="not_probed"` during discovery.

Run #62 proved this contract against the actual packed Claude Desktop artifact. The packaged smoke reported:

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

## Adobe XD Windows package compatibility

The live-E2E preparation path supports the current Windows XD package identity observed on MRCAO as well as the legacy identity:

- current package sandboxes matching `Adobe.XD_*`;
- legacy package sandboxes matching `Adobe.CC.XD_*`;
- the actual logged-in user's XD `PackageFamilyName` is preferred when available;
- the old documented package path remains a compatibility fallback.

`prepare_adobe_live_e2e.ps1` launches XD before automatic bridge installation so a freshly installed package can create its per-user `LocalState` sandbox. The installer then resolves that sandbox and installs the local MCP Adobe Bridge into `LocalState\develop`.

Targeted Windows evidence before merge:

- run `37175271407` on MRCAO;
- PowerShell helper parse test: **PASS**;
- real installer against a fake modern `Adobe.XD_*` LocalState sandbox: **PASS**.

## Evidence from run #62

The full exact-head log reported:

```text
Ran 119 tests in 84.209s
OK
```

The packaged runtime smoke passed against `mcp-adobe-creative-gateway.mcpb`, including the new transport/readiness contract gate. The artifact was uploaded with SHA-256 `17a0b1ca08e2bab03d9152e920647681ad154f53377b236b9ad870d8da63eead`.

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

These remain explicit blockers rather than simulated PASS results.
