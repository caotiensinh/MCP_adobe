# Panda red XD native save and live MCP continuation checkpoint — 2026-10-12

Repository: caotiensinh/MCP_adobe
Branch: `feat/canvas-region-targeting`
PR: https://github.com/caotiensinh/MCP_adobe/pull/32 (OPEN at last read)

## Verified immutable native files

- Original source: `%USERPROFILE%\Documents\MCPAdobe\MCP_Mode1_Panda_XD_38136531800.xd`
- Original SHA-256: `3a10e1510abc41eccd4485d6f852ea6ced7acc2cf50109e7c1bd123353589ed1`
- New red poster draft: `%USERPROFILE%\Documents\MCPAdobe\MCP_KFP4_Red_XD_38205166138.xd`
- New SHA-256: `58966788cf369885c2395ce217d6e0443ed57bcd7f40bd550b2f3a24c2b5b831`
- New size: **41,279 bytes**, **12 ZIP entries**, verified by native archive readback.
- New draft was created via real XD Home custom preset **880 × 700** in run **38205166138**.
- Native Save + SHA/ZIP + artifact upload **PASS** in run **38207905699**.
- Native artifact ID: **11728340116**; https://github.com/caotiensinh/MCP_adobe/actions/runs/38207905699/artifacts/11728340116
- Run **38208035402**: native SHA and current UI window census **PASS**, subsequent live MCP readback **FAIL**. Its GitHub job log endpoint returned **BlobNotFound** at last check, so do NOT guess the failure.
- Follow-up staged read-only MCP diagnostic run **38208213719** was **QUEUED** at last read, had not been claimed by MRCAO. Inspect its latest job and artifact before acting.

## Critical real host routing and button findings

1. ApplicationFrameHost top-level HWND and XD.exe CoreWindow are different. `XD.exe.MainWindowHandle` can point to the **old** document even if new document is active.
2. Native `Untitled-1` CoreWindow HWND was **3805114** at one read; the old CoreWindow was **3999436**. These are historical and MUST NOT be reused as stable identifiers.
3. To identify a document, map the exact ApplicationFrameWindow title to its **owned** child `Windows.UI.Core.CoreWindow`, then read its `TitleText` UIA control. Do not rely on the root ApplicationFrameWindow descendants or a process's MainWindowHandle alone.
4. The Windows PickerHost Save As filename Edit HWND is `AutomationId=1001`; it may itself be class `Edit` without any child Edit. Cross-process `GetWindowText` returned empty even though `WM_GETTEXT` returned the exact 64-character destination path.
5. Native Win32 `SendMessage(BM_CLICK)` on the Save button blocked in an input-synchronous COM RPC; one exact modal was dismissed in run **38207830383**; replacing synchronous click with **asynchronous PostMessage** allowed genuine native Save and readback in run **38207905699**.
6. Avoid reserved PowerShell variable names `$HOME`, `$Host`, `$PID` including within functions; case-insensitive PowerShell treats them as automatic read-only variables.
7. Never replay an unknown Save/Apply/drawing operation. Read current file, queue receipt, UIA and document state first.

## Current acceptance

- [x] Original XD checkpoint preserved and hashed.
- [x] New 880 × 700 red poster **empty draft** created through real Adobe XD UI.
- [x] New draft persisted as valid editable native XD file with artifact and SHA-256 readback.
- [ ] Confirm live MCP bridge is bound to this new saved draft, not old 32-object bamboo garden.
- [ ] Confirm new scenegraph UUID, artboard bounds, and queue depth zero.
- [ ] Create red background and panda/bamboo/typography through sequential real MCP queue / UXP Apply / receipt / scenegraph readback.
- [ ] Save/export updated XD artwork, hash, compare visual result against reference.
- [ ] Recover Illustrator C014 without replaying unknown job `job_625f841b04cb` or changing already verified native Illustrator checkpoints.
- [ ] Run continuous Photoshop → Adobe XD → Illustrator live E2E and measure per-write p50/p95/p99.

**Do not claim full XD poster, AI poster, or PS–XD–AI E2E PASS from native-empty-document save or read-only MCP results.**

## Safe next operation

First inspect run **38208213719** and any newer concurrent commits/jobs. Confirm the original and new native SHA before any mutation. Read real `creative.health`, `creative.document.info`, `creative.scenegraph.list`; require bridge connected, queue pending count zero, active XD document distinct from the old UUID `98d6635b-3767-4254-b200-ec8442b69ad2`, and a fresh empty artboard of the intended dimensions. If any check fails or is unavailable, do not queue the first red background. Create one shape, persist exact queued operation ID, invoke one UXP Apply on the child CoreWindow of the **new** document, read the receipt, re-read scenegraph, then save/hash the native file again. Treat any timeout as UNKNOWN and reconcile, never resend blindly.

## Continuation verified after native save

- Branch HEAD verified: `4f0312cb19c6ba3df2aaa4b24f2dc5021db69b07`; PR #32 remained OPEN.
- `38206890547`: prior synchronous `SendMessage(BM_CLICK)` blocked and job was cancelled; its log proves exact 64-character filename was read before the blocked call, **not** that the save completed. Subsequent evidence in `38207905699` independently establishes the actual completed native save and artifact.
- `38208035402`: native checksum/UI census step PASS, live MCP read step FAILURE; GitHub raw job logs unavailable with `BlobNotFound`, so exact failure is unknown.
- `38208213719` / job `114676329079` remains **QUEUED, not claimed**, with no steps or artifacts at the latest GitHub read. Other GitHub-hosted unit workflows complete successfully. The exact reason MRCAO is not claiming the job is **not yet verified**; do not assume it is offline without runner diagnostics. Do not enqueue duplicate desktop actions.
- C014 fail-closed callback patch persisted across commits `c3d575f3`, `fb4a1085`, `888d64d7`, `4f0312cb`: the local upstream trace now restores `priorCompletionObserved` if a matching `complete` lacks an accepted upstream completion and an intact, correlated payload (C014 missing descriptor, C013 payload error, orphan completion, digest failure, or stale generation). No Illustrator UNKNOWN job was replayed and no fence was released.
- GitHub-hosted regression run [38209149111](https://github.com/caotiensinh/MCP_adobe/actions/runs/38209149111): **8 tests passed**; adapter unit run [38209149067](https://github.com/caotiensinh/MCP_adobe/actions/runs/38209149067): **SUCCESS**. These prove repository code and unit behavior only, **not** that the revised trace is loaded by MRCAO's Illustrator runtime.
- Deployment caution: the existing `illustrator-upstream-trace-activation.yml` installer prints `TRACE_ALREADY_INSTALLED` without replacing a previously installed `_mcp_adobe_trace.py`. Do not claim new trace is active merely because the repo's version passed CI. A controlled, version-checked deployment/readback requires available MRCAO and safe reconciliation of the current unknown Illustrator host job, with no restart over an unresolved fence.

**Next executable gate**: first claim/complete staged read-only XD MCP diagnostics on MRCAO and verify the new document ID, queue zero and 880x700 bounds. Only then issue one background rectangle with full operation ID -> Apply -> receipt -> scenegraph -> native save/hash. In parallel, only read/reconcile C014 diagnostics; avoid restart and writes while `job_625f841b04cb` remains UNKNOWN.
