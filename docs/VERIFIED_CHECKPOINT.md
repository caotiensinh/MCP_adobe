# Verified checkpoint

Last updated: 2026-10-04 JST

## Exact verified software head

- GitHub Actions run: `#60` (`37174780754`)
- Exact code head: `2113d03176478db118ee315273bade007f94fddb`
- Windows self-hosted runner: `windows` on `MRCAO`
- Unit/regression result: **113/113 PASS**
- Claude Desktop MCPB validate/pack: **PASS**
- Packaged MCP `tools/list`: **PASS**
- Packaged Photoshop/Illustrator/XD adapter discovery: **PASS**
- MCPB packaged runtime smoke: **PASS**
- MCPB artifact upload: **PASS**
- MCPB artifact ID: `11292309730`
- Uploaded artifact SHA-256: `42cce94b53dd7c3c25a5762ae2a7157e0790d341c594490afd0a751b23af2c1b`
- Adobe XD manifest/main.js static validation: **PASS**

## Reliability boundaries now enforced

### 1. Transport connection is not application readiness

`AdapterInfo.connected` remains a transport-level compatibility field. It only means the downstream MCP/WebSocket transport is alive.

Client-facing `creative_discover` now makes that contract explicit without probing Adobe applications:

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

### 2. Application readiness is not operation completion

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

## Evidence from run #60

The two discovery-readiness contract tests were included in the full suite; the final log reported:

```text
Ran 113 tests in 79.635s
OK
```

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
