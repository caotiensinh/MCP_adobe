# Adobe MCP — Verified MRCAO session checkpoint (2026-10-12 JST)

Scope: `feat/canvas-region-targeting`, PR #32, MRCAO Session 1. All status claims in this report are backed by the linked GitHub Actions run and logs, not simulated Adobe controls. This document records **a partial deliverable**, not a full three-app E2E PASS.

## Original creative checkpoints — preserve

- Photoshop: previously verified **60/60 native design components**, with editable KUNG FU / PANDA / 4 type layers, polished PSD/PNG. [run 38151836136](https://github.com/caotiensinh/MCP_adobe/actions/runs/38151836136); PSD SHA-256 `1fdbfe35a0057a3f5b4f7d11428126439b6245fc758ec5a11163513eaee13128`. Photoshop host was absent on the new session's initial census; Photoshop *live runtime* has not been reopened/verified in this session.
- Adobe XD: original native `MCP_Mode1_Panda_XD_38136531800.xd`, SHA-256 `3a10e1510abc41eccd4485d6f852ea6ced7acc2cf50109e7c1bd123353589ed1`, document ID `98d6635b-3767-4254-b200-ec8442b69ad2`. 32 valid scenegraph objects are the saved 32-object design checkpoint, **not a finished Kung Fu Panda red poster**.
- Illustrator: backup `rect2_before_uia_save_38194275753/source_before.ai` SHA-256 `25d46aaacc766759d11c920872d9ee1cc26861a145826143161698e97ca14b77`; target `MCP_KFP4_Red_AI_Fresh_38157628243_5shapes.ai` SHA-256 `ec6d2239b3547845c16c80997ca716f50fb8e5f4f5f3f8d57e85079581fa89a2`. [run 38194704829](https://github.com/caotiensinh/MCP_adobe/actions/runs/38194704829) verifies one additional filled 880×700 red-orange vector through native PDF-compatible geometry. **2/60 independently persisted geometries**, NOT 2/60 verified live pageItems. Artifact 11722669173.

## Newly verified MRCAO operations

| Outcome | Real run | Persisted code SHA | Result and acceptance boundary |
|---|---|---|---|
| XD old restore failure classified | [38156574488](https://github.com/caotiensinh/MCP_adobe/actions/runs/38156574488) | Earlier SHA `ae41b3ac...` | FAILURE: XD Home observed but script wrapper tested stale PowerShell `$LASTEXITCODE`; current branch already fixes it |
| MRCAO live census | [38196702275](https://github.com/caotiensinh/MCP_adobe/actions/runs/38196702275) | `da75ceb3d0bdc7085c7a96b22688e3bf779b7801` | PASS, Session 1, gateway listeners 8787/8765/8081. Initially all three Adobe hosts absent; native XD and both Illustrator checkpoint checksums MATCH |
| XD home safe restore | [38196806498](https://github.com/caotiensinh/MCP_adobe/actions/runs/38196806498) | `5a26defaa005548e2820cd85c2b6b450b3bb9e58` | PASS, XD Home UIA observed; SHA unchanged; no duplicate launch |
| XD native document open | [38196980934](https://github.com/caotiensinh/MCP_adobe/actions/runs/38196980934) | `c74a2d7235b1e1f693a435e9a5f4632748a9453a` | PASS, uniquely visible verified XD document; guarded against active PickerHost |
| XD reconnect with Git checkout | [38197090618](https://github.com/caotiensinh/MCP_adobe/actions/runs/38197090618) | `d77b6503f3d74bf4d853a1d42f44c6ba3aadfe59` | CANCELLED: Connect PASS, readback cancelled after slow checkout consumed almost all job timeout; **no scenegraph PASS from this run** |
| XD real MCP readback without checkout | [38197405602](https://github.com/caotiensinh/MCP_adobe/actions/runs/38197405602) | `d1d59988bb11ed1dfd54201bc59d7e692c302cec` | PASS, connected UXP, pending=0, 32/32 valid live nodes, correct document ID & native SHA |
| Illustrator only GUI restore | [38197798137](https://github.com/caotiensinh/MCP_adobe/actions/runs/38197798137) | `a63b688c5c7d57fe0b99bfbc80c58a2b20a63a3e` | PASS, one Illustrator Session1 GUI launched, CEP 8081 connected; both native checkpoints MATCH after launch; no document mutation |
| Illustrator live health | [38198006743](https://github.com/caotiensinh/MCP_adobe/actions/runs/38198006743) | `ddf9e1473020fba702f0424cb76d50938c2d39c3` | PASS for passive health only; `blockedAt=unresolved_job`, ready=false, unresolved job `job_625f841b04cb` |
| Exact C014 job inspection | [38198172780](https://github.com/caotiensinh/MCP_adobe/actions/runs/38198172780) | `b87fac0ec11b689cd643a5c152bb4ae85985360c` | PASS for diagnostic status; job UNKNOWN, `[C014] missing_descriptor`, source `python_timeout` |
| Exact journal evidence | [38198290433](https://github.com/caotiensinh/MCP_adobe/actions/runs/38198290433) | `38067b47c0e2e409ac3a720f1593169fa3db674b` | PASS for diagnostic journal. Job `awaitingHost=true`, journal record `readOnly=false`, effects incomplete/untracked; **fence MUST remain** |
| 30-round XD live warm read-only latency benchmark | [38198624299](https://github.com/caotiensinh/MCP_adobe/actions/runs/38198624299) | `963bbda6258c3a0e156d52e043de19e4695a0daa` | PASS, 60 real calls in one persistent MCP session; sample artifact [11724199107](https://github.com/caotiensinh/MCP_adobe/actions/runs/38198624299/artifacts/11724199107) |

## C014 current blocker — do NOT bypass

Actual job `job_625f841b04cb`:
- `label=illustrator_document`, `status=unknown`, `awaitingHost=true`, `durationMs=30031`, `outcomeSource=python_timeout`, `requestConnectionGeneration=0`.
- Journal host call is `execute_script`, `readOnly=false`, `documentId=null`, `execution=unknown`, `integrity.status=failed`, `integrity.reason=missing_descriptor`, `effects.complete=false`, `coverage=untracked`. Empty created/modified lists **do not prove zero effects**.
- Source analysis: upstream `illustrator_mcp/bridge/payload.py` `PayloadReceiver.finish()` returns C014 when `self.descriptor is None`; `websocket_bridge.py` expects matching descriptor → chunks → complete, then coordinator settles the request. A late `complete` without a matching descriptor does not prove host completion. Existing traces include late `complete` callbacks after 10–30 s timeouts. Root producer/correlation failure is **not independently established**.
- **No new Illustrator canvas write, unknown-job replay, unverified fence release, or unscoped gateway reset until original host effect/receipt has been reconciled.** Do not infer read-only status from the tool label: journal says `readOnly=false`.

## XD measured latency (only 30 rounds read-only)

Single persistent client, 30 `creative.health` plus 30 `creative.scenegraph.list`, original XD SHA unchanged:
- MCP connection open: 831.26 ms.
- Warm excluding first, `creative.health`: p50 **17.95 ms**, p95 **23.57 ms**, p99 **25.36 ms** (n=29).
- Warm excluding first, `creative.scenegraph.list`: p50 **23.18 ms**, p95 **36.01 ms**, p99 **41.33 ms** (n=29).
- Python benchmark process wall time: **7409 ms** (not CI scheduling latency).
- Cold-vs-warm and write→Apply→receipt→save→native readback p50/p95/p99 are **not yet fully measured**. Do not advertise this as full drawing E2E.

## Next safe execution gates

1. Diagnose C014 at producer/receiver with exact per-request token, generation, descriptor/send/ACK and effect receipt; test a protocol fix offline before touching Illustrator, preserve current UNKNOWN fence until evidenced reconciliation.
2. Illustrator 2/60 geometry checkpoint remains immutable; independent live pageItem readback and shape 003 require restored safe coordinator.
3. Finish actual red poster XD and Illustrator with one write per checkpoint, correct document/queue guards, native save and readback; then continuous real **Photoshop → XD → Illustrator** acceptance.
4. Restore Photoshop only with original PSD SHA and no user-data overwrite. Measure cold/warm, queue, write, Apply, save/export and end-to-end throughput, including p50/p95/p99 with artifacts.
5. Avoid slow full checkout in MRCAO interactive workflows; use warm persistent MCP client and bounded jobs, preserving independent CI units.

## Progress discipline

- **HOÀN THÀNH**: Photoshop previously 60/60 layered PSD; XD saved 32/32 geometry readback; Illustrator 2/60 persisted vector geometries; restored XD native document/bridge and Illustrator GUI/CEP; verified checkpoints and 60-call XD warm benchmark.
- **CÒN LẠI**: Illustrator 58/60 vector geometries, true live scenegraph count, C014 fence fix, complete red poster XD, Photoshop current-host validation, continuous tri-app visual and save/export E2E, actual write-path latency validation.
- **TIẾN ĐỘ CẢI THIỆN PHIÊN VỪA RỒI**: **+0/60 new Illustrator geometries** in this session. New verified operating gates and benchmark evidence count separately; no total E2E PASS claimed.
