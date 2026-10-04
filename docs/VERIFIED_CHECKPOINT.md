# Verified checkpoint

Last updated: 2026-10-04 JST

## Exact verified software head

- GitHub Actions run: `#59` (`37172949455`)
- Exact code head: `3efe15ec96871462eaf53da29c9007e3ade8f678`
- Windows self-hosted runner: `windows` on `MRCAO`
- Unit/regression result: **111/111 PASS**
- Claude Desktop MCPB validate/pack: **PASS**
- Packaged MCP `tools/list`: **PASS**
- Packaged Photoshop/Illustrator/XD adapter discovery: **PASS**
- MCPB artifact upload: **PASS**
- Adobe XD manifest/main.js static validation: **PASS**

## Reliability boundaries now enforced

### 1. Transport connection is not application readiness

`AdapterInfo.connected` remains a transport-level compatibility field. It only means the downstream MCP/WebSocket transport is alive.

Before a non-read capability is allowed, the built-in adapters now reuse an application-level health primitive:

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

## Evidence from run #59

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
