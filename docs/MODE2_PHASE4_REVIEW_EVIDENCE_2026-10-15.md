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
