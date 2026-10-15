# MCP_ADOBE — Mode 2 Phase 4 acceptance & PR #32 review (2026-10-15)

## Evidence verified with MRCAO (real Adobe XD)

- One disposable native XD file: `C:\Users\caodu\Documents\MCPAdobe\mode2-disposable-native\Mode2_Undo_E2E_38584984023.xd`.
- Baseline SHA-256 for the original, Panda working copy, and disposable test before edits: `3A10E1510ABC41ECCD4485D6F852EA6CED7ACC2CF50109E7C1BD123353589ED1`.
- [GitHub Actions run 38592253921](https://github.com/caotiensinh/MCP_adobe/actions/runs/38592253921): `MODE2_RECT_QUEUED_ONCE=xd-1791992883402-1`, `MODE2_DISPOSABLE_APPLY_INVOKED_ONCE`, `MODE2_RECT_APPLIED_READBACK=PASS`, new GUID `29e85d07-75aa-4f8f-9a04-60de4d09477d`.
- [Run 38592737629](https://github.com/caotiensinh/MCP_adobe/actions/runs/38592737629): matching pre-Undo node present; native Edit > Undo invoked once; `MODE2_NATIVE_UNDO_READBACK=PASS nodes=33`; original file hash unchanged.
- [Run 38593302094](https://github.com/caotiensinh/MCP_adobe/actions/runs/38593302094): disposable file hash equals pre-mutation baseline; ZIP entries=12; bytes=188571; native File > Save control exists but **disabled** after Undo. No Save invocation was performed, and none should be claimed.
- [Run 38734348877](https://github.com/caotiensinh/MCP_adobe/actions/runs/38734348877): at start `MODE2_PRE_REOPEN_XD=0` (XD not open), then reopen requested once; `XD=1 TEST=1 BRIDGE=1`, `MODE2_NATIVE_REOPEN_SCENEGRAPH=PASS nodes=33`; post-reopen SHA guard passed. This demonstrates persisted reopening; it **does not** demonstrate that a Close menu command was executed within this same run.

**Verified scope:** disposable-only real XD queue > Apply > readback > native Undo > readback > disk hash and archive verification > reopen > readback. These are not mock results.

## Production gaps that this evidence does not close

1. `src/mcp_adobe/mode2_xd_transaction.py` accepts an **injected gateway**, but this PR has no demonstrated production implementation wiring its eight required host methods to an actual XD UXP session with independent native-path ownership. Unit tests use a mock `MockXD`.
2. `src/mcp_adobe/xd.py` still advertises `undo_supported=False`; do **not** change this to `True` based only on the discrete disposable UI Automation experiment.
3. The PR description explicitly states the Photoshop region preview double-read does not provide atomic revision or trusted frame provenance: `atomic_revision_verified=false`, `preview_frame_verified=false`. Automated region editing must remain disabled.
4. No fully demonstrated user journey yet for circle/region selection > unique live layer resolution > explicit user approval > edit > undo > saved/reopened verification across Photoshop, Illustrator and XD.
5. PR #32 encompasses **440 changed files** (+37,624/-13 at review), including 309 workflows; many are exploratory live-desktop diagnostics. A focused, independent review (and ideally smaller scoped changes) is required before merging.
6. There were no submitted PR reviews or review threads as checked 2026-10-15; `mergeable_state=clean` reports technical mergeability, not approval or product acceptance.

## Release decision

- **PASS**: XD disposable native Create/Apply/Undo/Reopen evidence.
- **PASS**: focused automated safety/unit contracts when the separate scoped CI gate is green.
- **NOT VERIFIED**: cross-application Mode 2 production flow and actual native gateway provenance.
- **NO MERGE** for PR #32 until the production acceptance gates and scope review are resolved.

Do not repeat any one-shot native mutation workflow merely to collect duplicate evidence: previously queued/applied operations have durable receipts; inspect live state and original SHA before any further action.

## Experimental Mode 2 transport integration (2026-10-15)

- **Protected XD production adapter restored**: `src/mcp_adobe/xd.py` was returned to pinned blob `d2bc0dcd53a6c954381f5b196f993d254d5549ee`. Subsequent golden-source CI is PASS. Production `adobe-xd-plugin/main.js` was not modified.
- **Explicit experimental adapter**: `src/mcp_adobe/xd_mode2_experimental.py` subclasses `XdAdapter` and is not registered by the production server by default. It exposes guarded read-only `xd.mode2.node.inspect` and approval-queued `xd.queue.mode2_fill` only when registered independently. Before requests, it demands a distinct live `xd.health.bridge_build` and for writes an empty queue; validation refuses invalid bounds, mismatched required keys, disabled writes and unconfirmed copies. Timeouts after a write send are outcome-unknown, never blindly retried. This is **not native origin-path attestation**.
- **Executable contracts**: [Mode 2 run 38741186061](https://github.com/caotiensinh/MCP_adobe/actions/runs/38741186061) confirms **56 Python tests PASS** plus executable experimental UXP runtime and isolated distribution contracts. Python tests include `CapabilityRegistry` routing, host-build mismatch, queue preflight and stale-selection rejection. Mock/simulated tests do not establish production E2E.
- **Separate UXP distribution**: plugin ID `MCPADM2E`, port `ws://127.0.0.1:8766`, build `xd-mode2-guarded-experimental-v1`, with no collision with production `MCPADB01` on port `8765`. [Stage run 38740060093](https://github.com/caotiensinh/MCP_adobe/actions/runs/38740060093) PASS on MRCAO: added dedicated files under `...\\LocalState\\develop\\MCPAdobeMode2Experiment`; native Panda baseline hashes and production plugin files preserved; **NO XD reload occurred**.
- **Real host identity before activation**: [run 38739422835](https://github.com/caotiensinh/MCP_adobe/actions/runs/38739422835) observed the production XD build `xd-ellipse-radius-geometry-v4`. [Read-only reload/menu discovery 38740390108](https://github.com/caotiensinh/MCP_adobe/actions/runs/38740390108) identified `Plugins > Development > Reload Plugins (Legacy)` (`PluginsMenu_Development_Reload`) and confirmed separate listener `8766` had **no experimental connection**, without invoking Reload.
- **Ready for a controlled live readback after plugin activation**: `scripts/mode2_xd_experimental_readback.py` is read-only and bounded; [workflow `mode2-xd-experimental-live-readonly.yml`](https://github.com/caotiensinh/MCP_adobe/actions/workflows/mode2-xd-experimental-live-readonly.yml) is manual-dispatch, requires the single disposable document, starts listener on `8766`, confirms distinct UXP hello, 33-node scenegraph, frame ID, optional selected-node inspection, and protected hashes. It **has not run against an activated Mode 2 plugin yet**.

### Next acceptance gate

Activate the separate dev plugin through the Adobe XD *Development > Reload Plugins (Legacy)* UI while the disposable document is clean. Keep production bridge `8765` intact and establish experimental listener `8766`; run the manual read-only acceptance workflow. Do not queue real `xd.queue.mode2_fill` until independent native document ownership/provenance and Undo controls are proven and the exact edit target is uniquely confirmed.

**PR #32: OPEN / DO NOT MERGE**. The above narrows the concrete activation blocker; it does not prove circle-to-edit production flows for XD, Photoshop, or Illustrator.
