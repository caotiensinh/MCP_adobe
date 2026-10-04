# Verified checkpoint

Last updated: 2026-10-04 JST

## Exact verified software head

- GitHub Actions run: `#65` (`37179530076`)
- Exact code head: `e83d172d0cc87840ec03b92651cb4919d665838c`
- Windows self-hosted runner: `windows` on `MRCAO`
- Unit/regression result: **125/125 PASS**
- Claude Desktop MCPB validate/pack: **PASS**
- Packaged MCP `tools/list`: **PASS**
- Packaged Photoshop/Illustrator/XD adapter discovery: **PASS**
- MCPB packaged runtime smoke: **PASS**
- MCPB artifact upload: **PASS**
- MCPB artifact ID: `11300147127`
- Uploaded artifact SHA-256: `793bf44546f34321097e77bf9c59b94d0a59dc3832cd87c56cbb51f15ae9161d`
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
- `connection_semantics="transport_only"` for Photoshop/Illustrator/XD;
- `transport_connected == connected` for backward compatibility;
- `readiness_probe="creative.health"` for all built-in adapters;
- `readiness_status="not_probed"` during discovery.

Run #65 proved this contract again against the actual packed Claude Desktop artifact. The packaged smoke reported:

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

The verified main includes two guarded Windows helpers:

- `scripts/dispatch_adobe_live_e2e.ps1`
- `scripts/run_adobe_live_e2e.ps1`

The launcher performs GitHub authentication preflight **before** changing the dedicated MCP_adobe runner service. It then reuses the preparation helper to install/update the XD bridge, move only `D:\actions-runner-adobe` into the logged-in interactive desktop session, and dispatch the existing workflow with explicit live inputs.

### Portable GitHub CLI bootstrap

The exact MRCAO blocker where both `gh` and `winget` were missing is fixed on main.

Fallback order now keeps explicit/local installs first and can bootstrap GitHub CLI directly from the official `cli/cli` release:

```text
MCP_ADOBE_GH_PATH
→ PATH
→ Program Files
→ WinGet links
→ existing MCPAdobe portable cache
→ winget install when available
→ official portable GitHub CLI ZIP
```

The portable path:

- downloads the official Windows AMD64 ZIP;
- validates the GitHub release URL;
- verifies the release-provided SHA-256 digest when present;
- fails closed on digest mismatch;
- extracts `gh.exe` into the dedicated MCPAdobe tools directory;
- probes `gh --version` before use;
- uses the resolved absolute executable path;
- never changes the runner service before GitHub authentication succeeds.

Fresh evidence before merge included:

- MRCAO targeted run `37178920755`: real no-gh/no-winget path downloaded `gh_2.102.0_windows_amd64.zip`, verified SHA-256 `ae64e556ecc240b200f7eba60d550e4bb60d78e860e69dd88c449405b86067f4`, extracted and executed `gh.exe`;
- hosted Windows run `37179397968`: forced portable mode completed official download → SHA verification → extraction → `gh --version`;
- regression proving installer diagnostic output cannot contaminate the resolved executable path.

Safety/approval behavior remains:

- no live workflow dispatch if GitHub CLI/auth preflight fails;
- `-XdWrite` is rejected together with `-NoXdLive`;
- default dispatch sets `run_adobe_live=true` and `xd_live=true`;
- `-XdWrite` sets `xd_write=true`, but XD mutation still cannot PASS until the user clicks **Apply pending** in the MCP Adobe Bridge panel;
- the helper does not treat service-session transport connectivity as desktop readiness.

## Adobe XD Windows package compatibility

The live-E2E preparation path supports the current Windows XD package identity observed on MRCAO as well as the legacy identity:

- current package sandboxes matching `Adobe.XD_*`;
- legacy package sandboxes matching `Adobe.CC.XD_*`;
- the actual logged-in user's XD `PackageFamilyName` is preferred when available;
- the old documented package path remains a compatibility fallback.

`prepare_adobe_live_e2e.ps1` launches XD before automatic bridge installation so a freshly installed package can create its per-user `LocalState` sandbox. The installer then resolves that sandbox and installs the local MCP Adobe Bridge into `LocalState\develop`.

## Evidence from run #65

The full exact-head log reported:

```text
Ran 125 tests in 61.346s
OK
```

The packaged MCPB was validated and packed successfully. Packaged runtime smoke passed with the transport/readiness contract intact, and artifact `11300147127` was uploaded with SHA-256 `793bf44546f34321097e77bf9c59b94d0a59dc3832cd87c56cbb51f15ae9161d`.

The same exact-head run still showed the service-session boundary clearly:

```text
User=nt authority\network service
UserInteractive=False
Photoshop=<not visible in service session>
Illustrator=<not visible in service session>
Adobe XD=57.1.12.2 installed
LIVE_E2E=SKIPPED: push CI never writes to Adobe applications.
```

Therefore run #65 verifies the gateway, packaging, bootstrap regression and static bridge contract, but does not claim real Adobe desktop application readiness.

## Still not claimed

- real Photoshop desktop E2E from the logged-in interactive Windows session;
- real Illustrator desktop E2E from the logged-in interactive Windows session;
- real XD UXP live read/write E2E from that interactive session;
- production ChatGPT + external OAuth provider E2E;
- production Claude client + real Adobe desktop E2E.

The first three now require only the verified one-command launcher to be executed from the logged-in MRCAO desktop session. They remain explicit blockers rather than simulated PASS results.
