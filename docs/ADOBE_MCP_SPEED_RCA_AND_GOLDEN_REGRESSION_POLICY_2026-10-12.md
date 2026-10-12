# Adobe MCP — Root-cause report: slow E2E orchestration versus fast connected MCP

Date: 2026-10-12 JST. Repository: `caotiensinh/MCP_adobe`, PR #32, MRCAO Windows Session 1.

## Verified causal breakdown

**Do not mistake GitHub job wall time for MCP request latency.**

| Boundary | Measured evidence | Conclusion |
|---|---|---|
| Already connected XD gateway and plugin, read-only | Run [38198624299](https://github.com/caotiensinh/MCP_adobe/actions/runs/38198624299): XD health 30 samples p50 17.95 ms / p95 23.57 ms; XD scenegraph p50 23.18 ms / p95 36.01 ms | MCP calls can be fast after the live plugin has connected. Does NOT measure rectangle creation, native Save or Photoshop/Illustrator |
| Illustrator non-probing health | Runs [38244152869](https://github.com/caotiensinh/MCP_adobe/actions/runs/38244152869), [38243541236](https://github.com/caotiensinh/MCP_adobe/actions/runs/38243541236), [38243036285](https://github.com/caotiensinh/MCP_adobe/actions/runs/38243036285): 95.84, 111.54, 188.94 ms | Backend/coordinator health can be quick; `probe=false` does not establish actual host JSX responsiveness |
| Job overhead BEFORE ANY MCP request | Run [38246160525](https://github.com/caotiensinh/MCP_adobe/actions/runs/38246160525): 5 s setup + 11 s checkout + 1 s process check = 17 s; target Illustrator absent; no MCP benchmark executed | Every independent Actions run pays CI setup and context-switching overhead |
| Illustrator cold start | Run [38243223390](https://github.com/caotiensinh/MCP_adobe/actions/runs/38243223390): readiness window not observed before the approximately 40.3 s deadline. Subsequent run [38243541236](https://github.com/caotiensinh/MCP_adobe/actions/runs/38243541236) sees one actual Illustrator GUI PID 3608/CEP established | Cold Adobe application startup is a distinct much slower phase, not the same as warm MCP request |
| XD volatile UI ownership | [38232069131](https://github.com/caotiensinh/MCP_adobe/actions/runs/38232069131): saved red draft and UXP connected/healthy. Later [38242475576](https://github.com/caotiensinh/MCP_adobe/actions/runs/38242475576): zero verifiable XD document window, so no click was sent | Process/localhost listener alone does not guarantee Adobe UI/document/session ownership |
| Illustrator false preflight block | [38243991188](https://github.com/caotiensinh/MCP_adobe/actions/runs/38243991188) stopped with `AI_RECT_FOREIGN_OR_UNSAVED_DOCUMENT_PRESENT` on `probe=false document.status=unknown`; [38244152869](https://github.com/caotiensinh/MCP_adobe/actions/runs/38244152869) later confirms unknown means the host hasn't been queried yet | Guard was premature. Corrected to check document absence **after** trusted probe. Dedicated regression tests added |
| Unstable Adobe lifespan | [38246160525](https://github.com/caotiensinh/MCP_adobe/actions/runs/38246160525) and [38246434559](https://github.com/caotiensinh/MCP_adobe/actions/runs/38246434559) show all three Adobe app processes absent while gateway ports are still listening. Event Log scan found zero matching crash events | Application disappears between runs; **cause of exit is NOT VERIFIED** (no evidence to choose runner cleanup, manual close, crash or other lifecycle mechanism) |
| Concurrent runner processes | [38246434559](https://github.com/caotiensinh/MCP_adobe/actions/runs/38246434559) shows one Runner.Listener in Session 1 plus three in Session 0 | May be legitimately distinct runners; NOT proof of a conflict without identifying registration/root/label |

**Current three-app serial rectangle E2E outcome: NOT ACCEPTED.**
No one-pass Illustrator → XD → Photoshop three-native-rectangle + readback timing exists. An E2E run that fails in setup cannot be called a slow **MCP** command or a successful draw.

## Changes delivered on branch

1. **Golden source integrity lock:** `contracts/adobe_connection_goldens.json` pins exact Git blob SHAs of eight reviewed integration surfaces (XD/PS/AI adapters, Illustrator CEP/trace, XD plugin JS/manifest, MCP gateway). `tests/test_adobe_connection_goldens.py` fails on silent source edits. Scope explicitly distinguishes historical live evidence and unit-only Illustrator trace.
2. **CI safeguard:** `.github/workflows/adobe-connection-golden-contract.yml` runs hosted source+contract tests on changes to protected code/manifest, **not** on MRCAO. Known run [38245591556](https://github.com/caotiensinh/MCP_adobe/actions/runs/38245591556) passed. Later test includes Illustrator guard contract and [38245880276](https://github.com/caotiensinh/MCP_adobe/actions/runs/38245880276) passed.
3. **Stop unrelated automatic CI churn:** `.github/workflows/interactive-surface-unit.yml` now has scoped `paths` filters. Previously its branch trigger ran on each small experimental commit, creating extra jobs.
4. **Mandatory review candidate:** `.github/CODEOWNERS` tags the locked surfaces. **IMPORTANT:** GitHub branch protection/rulesets requiring code-owner review and required status checks must be configured by the repository administrator. CODEOWNERS by itself does not prevent merges.
5. **Prevent repeat false preflights:** `scripts/adobe_ai_one_rectangle_measured_once.py` no longer interprets non-probed Illustrator document `unknown` as a foreign unsaved document; it retains all C014/panel busy guards and still needs trusted probe to prove `none_open`. `tests/test_adobe_ai_preflight.py` explicitly covers the transition, busy panel, unresolved job, foreign document and blocking fence.
6. **Warm no-restart measurement:** `scripts/adobe_mcp_warm_single_session_probe.py` uses one MCP Client and 12 read-only requests per capability. `.github/workflows/adobe-one-app-warm-mcp-measure.yml` can be dispatched for the *already-running* single app, never launches Adobe, never clears queues or mutates design. Record `client_connect_ms`, p50/p95, failure rates and an explicit `not_measured` field. The initial [38246160525](https://github.com/caotiensinh/MCP_adobe/actions/runs/38246160525) did **not** collect warm metrics because Illustrator had already exited; do not invent numbers.

## Non-regression rules for future upgrades

- Never change a pinned integration surface invisibly: review delta + update golden blob + unit tests + corresponding live host readback + same-environment speed comparison + rollback point.
- Before any E2E compare **installed host runtime** to approved repository source/version. Passing source SHA CI does **not** prove the corresponding plugin/CEP is installed in the desktop.
- **One Adobe app running at a time** for requested serial AI → XD → PS benchmark. When switching, verify all native saves and close cleanly; never kill or hide unresolved unsaved/UNKNOWN tasks.
- Within the lifetime of each app, reuse the same persistent gateway/client/host connection for successive reads/writes; do not start a new GitHub job or do `uv sync`, reinstallation, plugin deploy or Adobe restart per rectangle.
- One orchestrator should record independently: runner queue, checkout/setup, cold app boot, host bridge ready, MCP command ACK, host apply, scenegraph/object readback, native save/hash, graceful app close. Report p50/p95 warm per-command **separately** from full cold E2E duration.
- Respect XD UXP `insertionParent` (must be the actual target artboard); Illustrator C014 UNKNOWN/probe-fence must not be cleared or replayed without a correlated host receipt.

## Still unverified / next acceptance gate

1. Identify why Adobe processes disappear (runner child-process lifecycle vs normal close vs crash). An empty Windows crash-event scan is not proof of a normal shutdown; multiple Runner.Listener processes do not automatically mean duplicate runner registration.
2. Live-read installed plugin/adapter fingerprints, actual host version, UI document ownership and native backup hashes before modifying verified source.
3. Implement **one** persistent Session 1 controlled runner orchestration for the entire three-app rectangle sequence; avoid a GitHub workflow for each step. Acceptance requires actual host-created objects, scenegraph/layer readback, native saved files, hashes and all phase latency measurements.
4. Do not set a p95 full E2E SLO until the above test yields valid repeatable samples. Existing XD warm p95 values are historical read-only reference, **not E2E target measurements**.

The goal is to preserve the fast working connection, not remove necessary safety checks. No E2E PASS claim is authorized by this document.
