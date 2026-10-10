# Nhật ký sửa lỗi — Illustrator MCP C014 / readback / live draw
Ngày: 2026-10-10 (JST). Repo: caotiensinh/MCP_adobe; nhánh feat/canvas-region-targeting.

## Triệu chứng và vị trí
- Adobe Illustrator 2023 chạy từ `D:\Ilustrator\Adobe Illustrator 2023\Support Files\Contents\Windows\Illustrator.exe`, CEP WebSocket Python lắng nghe 8081, gateway lắng nghe 8787.
- `creative.document.info` trả MCP tool error; `creative_live_build` không được chạy an toàn.
- Upstream `jinkeda/Illustrator_MCP`: `illustrator_mcp/websocket_bridge.py` (payload_descriptor / completion correlation), `illustrator_mcp/execution/coordinator.py` (`assert_host_available`), `illustrator_mcp/tools/task_execution.py` (`illustrator_job_status`), `illustrator_mcp/host_session.py` (host ledger).
- Adapter dự án: `src/mcp_adobe/illustrator_cep.py` chuyển `creative.document.info` -> `illustrator_get_document` và `creative.shape.rectangle` -> `illustrator_execute_task`.
- Job lỗi `job_bb227cf2e04a`: `status=unknown`, `awaitingHost=true`, `[C014] missing_descriptor`, pha `annotate_collect`; journal có 1 created ID `mcp_884589d3-e58a-4cb0-8cbc-b57faee2f152` nhưng effects toàn job `complete=false`.
- `illustrator_job_status` không đối chiếu được ledger bởi `host_request_unresolved`. Điều này tạo vòng khóa: unknown job chặn host calls, kể cả readback. C014 có thể là lỗi giao thức descriptor ở bước cuối; chưa xác minh độc lập được nguyên nhân sâu nhất của mất descriptor. Không gán nhãn “đã sửa triệt để upstream”.

## Chẩn đoán/khắc phục thực tế
1. Sửa đường dẫn mở Illustrator theo D: thay vì giả định C:, run 38047342518: EXE FOUND, Illustrator PID xuất hiện, nhưng readback vẫn FAIL.
2. Xác nhận CEP socket 8081 là kết nối `python.exe` ↔ `CEPHtmlEngine.exe`, run 38047811632.
3. Thu health và journal cấu trúc trong run 38047958631 / 38048340625: `blockedAt=unresolved_job`, activeJob null, panel idle, requestToken của `annotate_collect` tồn đọng.
4. Thêm `src/mcp_adobe/illustrator_recovery.py` và `tests/test_illustrator_recovery.py` để chặn mọi lệnh khi trạng thái host chưa xác minh. Unit run 38048862364 PASS; đây là fail-closed guard, không tự giải phóng unknown job.
5. Khôi phục có kiểm soát bằng workflow `.github/workflows/illustrator-scoped-gateway-recovery.yml`: lưu preflight và journal artifact, kiểm tra CEP idle/queue trống, **chỉ** khởi động lại gateway listener 8787 qua supervisor; không tắt Illustrator và không replay job. Run 38049044975: gateway PID 17604→21584, Illustrator PID 7752 giữ nguyên; `unresolvedJobs=[]`, `probe=true` trả Illustrator 27.4.0. Đọc document lúc đó FAIL vì `documentCount=0` — không còn do job khóa.
6. Tạo tài liệu mới riêng `MCPAdobe Readback Acceptance`, kích thước 900×600, run 38049197245: `creative.document.create` PASS, `creative.document.info` PASS, document name/size/layer/ artboard đọc lại từ host.
7. Vẽ 1 rectangle qua MCP với run 38049761683: `creative.shape.rectangle` SUCCESS, host `createdIds=[mcp_9a7836aa-b1c8-435e-a0e2-6a9afc904b83]`, `verification=passed`, layer `itemCount` 0→1 và đọc lại item tên `MCPAdobe Live Rectangle 001`, vị trí [180,-160], bounds 480×260. Artifact `illustrator-visible-rectangle-evidence` đã được upload; screenshot chưa được xác minh nội dung thủ công tại thời điểm log này.

## Điều kiện chốt nghiệm thu và phòng tái phát
- Không đánh dấu PASS chỉ vì Illustrator process/CEP socket/HTTP 200 hay `creative_write` ACK.
- Document readback: tạo hoặc mở document thử nghiệm, sau đó host read xác nhận name, size, layer.
- Vẽ live: tạo từng đối tượng qua `creative_live_build` / nhiều write tuần tự và theo dõi thay đổi itemCount, created IDs, final screenshot. Giữ Illustrator visible foreground.
- Bắt buộc bảo toàn chứng cứ trước khi restart. Chỉ restart owned gateway khi `panel.busy=false`, không activeJob/waiting. Không reset tài liệu, không replay job unknown, không xóa khóa bằng tay.
- C014 có thể quay lại: nếu `unknown`, dừng vẽ mới, chụp journal, đối chiếu host ledger; không rerun mù.
- Workflow dùng `RUNNER_TRACKING_ID` hợp lý để tránh GitHub job cleanup đóng Illustrator.
- Lưu ý: `COM_CONNECT_FAIL` là đường kiểm thử ActiveX riêng, không chứng minh MCP hỏng; dùng upstream CEP/WebSocket MCP.

## Evidence
- Recovery: https://github.com/caotiensinh/MCP_adobe/actions/runs/38049044975
- Document readback: https://github.com/caotiensinh/MCP_adobe/actions/runs/38049197245
- Rectangle direct MCP: https://github.com/caotiensinh/MCP_adobe/actions/runs/38049761683


## Tái kiểm tra ngôi nhà 2 tầng mái ngói đỏ (cùng ngày)
- Commit `190942c1235dc393b8bc58dc1831aa4f2310deae`, run https://github.com/caotiensinh/MCP_adobe/actions/runs/38050269830: workflow yêu cầu 38 bước theo thứ tự (tạo document mới, tường 2 tầng, các dải ngói đỏ, cửa sổ, cửa chính), `step_delay_ms=900` qua `creative_live_build`. Foreground preflight PASS, `creative.health` trả `ready=true`, `unresolved=[]`, Illustrator 27.4.0.
- Khoảng 40 giây sau `LIVE_BUILD_BEGIN`, `creative_live_build` trả MCP tool error; bước vẽ FAIL. Workflow có screenshot `HOUSE_VISUAL_CAPTURE=PASS`, nhưng không xác minh nội dung hình ảnh và không thể suy ra nhà đã hoàn tất.
- Run read-only https://github.com/caotiensinh/MCP_adobe/actions/runs/38050421486 theo commit `e7c4fa0957e19189757d253ee4df0c43f9057761` xác định job mới `job_4f06800a73dc` đã `unknown / awaitingHost=true`, `blockedAt=unresolved_job`. Vì bị quarantine, document readback vẫn không trả được. Đây là **lỗi tái phát khi vẽ dài**, không được tính PASS dù rectangle một bước PASS.
- Không được rerun 38 bước, không reset document mù. Cần lưu journal chi tiết của job mới, xem host effects, rồi xử lý khôi phục có kiểm soát và nghiệm thu incremental có checkpoint từng nét, tránh một `creative_live_build` kéo dài nuốt mất evidence và làm kẹt job.
- Trạng thái: nhật ký đã ghi lỗi, demo house **FAIL**, visual step-by-step **CHƯA NGHIỆM THU**.

## User visual rejection / corrected roof geometry
- Người dùng cung cấp ảnh Illustrator và xác nhận hình không giống nhà 2 tầng mái ngói đỏ. Lỗi thiết kế: workflow `illustrator-two-story-house-live.yml` vẽ mái bằng dải **rectangle ngang**, không tạo hai mặt mái dốc; kết quả không đạt tiêu chí hình học dù tool có thể ghi nhận một số element.
- Commit `744d39ae2f7d856c003bb488fa0fd81990aa1658`: workflow `illustrator-house-stroke-by-stroke.yml` thay mái bằng polygon tam giác với điểm [[136,291],[445,87],[754,291]], có 2 nét mái dốc, đường ngói, cửa sổ 2 tầng và cửa chính; gọi riêng `creative_write` cho từng nét và đọc `creative.document.info` sau mỗi nét, chống batch opaque.
- Run https://github.com/caotiensinh/MCP_adobe/actions/runs/38050696567: **FAIL TRƯỚC KHI VẼ**, tại `creative_read` preflight; host không trả tool result hợp lệ. Không có chứng cứ workflow mới đã tạo polygon mái. Không tự động replay job trước đó.
- Run scoped recovery house https://github.com/caotiensinh/MCP_adobe/actions/runs/38050519070: gateway PID 21584→24456, Illustrator PID 7752 giữ nguyên, nhưng POST_HEALTH và POST_DOC đều null. Cần chẩn đoán gateway/CEP sau restart trước khi thử lại; không đánh dấu PASS và không diễn đạt rằng có hình live thành công.


## 2026-10-10 21:08–21:14 JST — visual evidence and incremental retry
- User screenshot shows only green baseline and one brown vertical wall edge, NOT a finished two-story tiled-roof house. This matches failure during early sequential strokes. Do not report house PASS.
- House recovery run 38050519070: preflight recorded `job_4f06800a73dc` unknown, gateway PID 21584→24456, Illustrator PID 7752 preserved. Post-restart `creative.health` and `creative.document.info` returned MCP tool errors rather than usable responses.
- Run 38050899573 confirms read-only creative.health and creative.document.info errors. Run 38050983552 confirmed 8787 PID 24456 and 8081 PID 18540 both LISTEN, CEP connection established. Ownership lineage run 38051029729 proved 8081 PID 18540 is a **descendant of 8787 gateway PID 24456**; orphan upstream hypothesis rejected.
- New checkpoint-first workflow `.github/workflows/illustrator-house-incremental-checkpointed.yml` commit 08a87fe95f4ea9a8e4dd46e529d140164279344a changes from one 38-step `creative_live_build` to separate `creative_write` per shape with `creative.document.info` readback, object count/name checks, and 1300ms visual interval.
- Run 38051122665 FAILED SAFELY before any write: `creative.health` MCP tool error; no HOUSE_STEP_START logged, no new strokes sent. Screenshot captured, not reviewed visually.
- Remaining root blocker: intermittent upstream MCP tool errors after controlled restart, not TCP connectivity. Must diagnose subprocess SDK error and host reachability with unredacted local structured exception logs (secrets redacted), before retrying incremental E2E. No blind replay over existing artwork.


## 2026-10-10 21:17 JST — deep MCP probe fence evidence
- Run https://github.com/caotiensinh/MCP_adobe/actions/runs/38051396487, commit `1381eb2a7890118b647e08d33dc1594e14f57752` queried the gateway through the real MCP client; `creative.health probe=false` returned structured response (not transport-down), but `blockedAt=probe_fence`.
- Blocking record `job_ef3827b100ff`, `trustedProbe=true`, `priorCompletionObserved=true`, `probeFenceRequired=true`. This is a stale readiness fence that coordinator did not retire simply because prior completion had been observed.
- Subsequent `creative.health probe=true` failed to establish readiness: `PROBE_FENCE_UNSUPPORTED: predecessor completion is unproven`. A newer trusted probe `host_330bf6bcfce64d448dfa1a6a26ffadeb` showed `priorCompletionObserved=false` and `panelBusy=true`, so attempting more drawing would risk overlapping in-flight host work.
- `creative.document.info` returned `is_error=true`, no structured content. `creative.job.status` for the previous house job returned no retained record after the restart, and host ledger `host_unavailable`. Neither this nor a missing job record is proof the old edits did not apply.
- Specific upstream components requiring durable correction: `illustrator_mcp/execution/trusted_probe.py` (`blocking/readiness`), `illustrator_mcp/websocket_bridge.py` (`execute_script_async` priorCompletion/fence) and `illustrator_mcp/execution/coordinator.py` (`probe_fence` retention). Preserve late completion correlation and require observed panel idle before lifting fence. Do **not** bypass the guard unconditionally.
- Drawing is HALTED, not successful. House canvas remains partial per user screenshot; no safe authorized mutations until fence is reconciled with host.


## 2026-10-10 21:20–21:23 JST — bounded diagnostic and retained fence status
- Added read-only non-probing health workflow `illustrator-bounded-recovery-assessment.yml` commit `ae017d548d2f684e483badc47f3af02eb14c1908`, run 38051569989: `blockedAt=probe_fence`, `unresolvedJobs=[]`, `activeJob=null`, `panelBusy=false`, `activeRequestId=null`, blocking fence `host_330bf6bcfce64d448dfa1a6a26ffadeb` with `priorCompletionObserved=true`. This proves no ordinary mutation is authorized despite idle panel; it does **not** prove target host call completion.
- Exact status inspection workflow `illustrator-fence-job-inspection.yml` commit `b141bf9fd110110158738191f550a6de5923232b`, run 38051678978: `creative.job.status` returned `is_error=true`, `structured=null` after ~40 sec. This did NOT reconcile the fence. Do not clear fence by heuristic and do not replay the unfinished house.
- Current E2E house acceptance remains FAIL. Next fix must instrument and test upstream `illustrator_job_status` / trusted-probe fence with host completion evidence and strict timeout/response handling, then rerun document reads before any draw command.


## 2026-10-10 21:27 JST — one-shot fence recovery probe
- Added workflow `.github/workflows/illustrator-single-fence-recovery-probe.yml` commit `764ad5f366bc7257cf337c1128556288eba17ddc`, run https://github.com/caotiensinh/MCP_adobe/actions/runs/38051914775.
- Preflight: panel `busy=false`, `activeRequestId=null`, no queued or unresolved jobs; fence `job_ec8196ab78c4`, `priorCompletionObserved=true`, `blockedAt=probe_fence`.
- Exactly one `creative.health(probe=true, timeout=7)` returned MCP tool error after ~7s, no structured response. Because recovery outcome wasn't established, no document read or write occurred.
- This falsifies the assumption that panel-idle + priorCompletionObserved alone is sufficient for live fence recovery. The upstream current code requires a **valid JSX probe response** and current connection generation before releasing the fence; it is not receiving a valid response reliably.
- Next engineering priority: instrument CEP `evalScript` and bridge command result/ACK for a single bounded probe (requestId, requestToken, generation), then fix missing/late callback rather than clearing fences or using unbounded restart/retry.


## 2026-10-10 21:47 JST — installed upstream source locations
- Run https://github.com/caotiensinh/MCP_adobe/actions/runs/38053265852 (commit `15aaa4f7f96b2551134a15b2d352b6b825e6460a`) resolved exact MRCAO site-packages locations:
  - `C:\Users\caodu\AppData\Local\MCPAdobe\illustrator-mcp\venv\Lib\site-packages\illustrator_mcp\execution\coordinator.py`
  - `C:\Users\caodu\AppData\Local\MCPAdobe\illustrator-mcp\venv\Lib\site-packages\illustrator_mcp\websocket_bridge.py`
- `local-host.log` had last write timestamp 2026-10-10 21:13:59 JST while diagnostic ran later; recent log scan did not yield actionable callback exception lines. Next action should add **bounded diagnostic instrumentation to installed upstream from a reviewed, pinned patch**; test with a read-only probe and exact correlation IDs before any house drawing.
- The installed upstream, not the project's unit-test-only `illustrator_recovery.py`, is responsible for retaining `probe_fence`. Avoid claiming project-side fail-closed unit PASS means upstream is fixed.


## 2026-10-10 21:53–22:00 JST — upstream instrumentation activated
- `.github/workflows/illustrator-upstream-trace-deployment.yml` run 38053577873 verified instrumentation compatibility in installed upstream process without affecting active session.
- `.github/workflows/illustrator-upstream-trace-activation.yml` run https://github.com/caotiensinh/MCP_adobe/actions/runs/38053679377, commit `cd380975e0b8568f66ce207809603b889912076f`: copied tracer into upstream site-packages and appended guarded activation to `websocket_bridge.py`; original saved to `websocket_bridge.py.mcp-adobe-original.bak`. Syntax validation PASS, gateway PID 24456→17796, Illustrator PID 7752 preserved.
- First non-probing health after restart: `is_error=false`, `blockedAt=document`, `blocking=null`, panel `busy=false`, indicating prior Python-side probe fence no longer blocks that immediate request. This is **not** proof of document availability or of a durable fence bug fix.
- Document reconciliation `.github/workflows/illustrator-house-document-reconcile-after-trace.yml` run https://github.com/caotiensinh/MCP_adobe/actions/runs/38053909573, commit `d34787a0d0f45753fc511ed4fb42bed05924bb26` completed workflow successfully but its internal `creative.health(probe=true)` and `creative.document.info` both returned MCP tool errors and null structured content. Workflow itself has no assert for result.is_error, therefore job SUCCESS is diagnostic only.
- **Actual acceptance: document readback FAIL, visible two-story house incomplete.** Next trace must capture host exception / callback and distinguish an absent document from a new trusted-probe fence. Do not replay the previous partially built house.


## 2026-10-10 22:09–22:10 JST — installed tracer verification
- Existing deployment run 38053679377 already copied a backed-up diagnostic wrapper into the Windows upstream site-packages and restarted only gateway; this is confirmed in its logs. Tracer wrapper is instrument-only, not a probe-fence repair.
- New run https://github.com/caotiensinh/MCP_adobe/actions/runs/38054646823 (commit `518d021c114b435b6f7a5c90aa1a816587c82d01`): `INSTALLED_TRACE_EXISTS=True`, `BRIDGE_TRACE_FOOTER=True`, gateway PID 17796 at 8787, upstream Python PID 3276 at 8081; no `HOST_TRACE` lines found in last 500 local-host log lines. Lack of matching lines does not prove wrapper absent or host healthy.
- New run https://github.com/caotiensinh/MCP_adobe/actions/runs/38054705565 (commit `0dfa44f12fb809c1463b9c03aa5e3bff5987132b`): fresh upstream package import confirms `WebSocketBridge.execute_script_async._mcp_adobe_trace=True` and method defined in `illustrator_mcp._mcp_adobe_trace`. `FENCE_INIT=None` reflects a **separate newly imported Python process**, not the live gateway/upstream state; do NOT use it to clear the live fence.
- Next: instrument actual gateway/upstream logging sink or run a gated read-only production trace. Preserve host callback evidence and never use unproven reset to replay old shapes.


## 2026-10-10 22:27 JST — real upstream callback-trace acceptance (task 01)
- Tracer update commits `6e7ff55cae7c10fe4702d22433729f3e87c5b583`, `8a56906c143eda5af6cb957c2b1ebfd24623afd3`: dedicated `%LOCALAPPDATA%\MCPAdobe\illustrator-mcp\callback_trace.log` records only safe metadata, including CEP inbound envelope kind/requestId/token match, wrapper return/error and fence state.
- Workflow `.github/workflows/illustrator-callback-trace-live-acceptance.yml`, corrected safety condition commit `6cb499cd3323081c66a918547e50fa8f3c95fe59`; run https://github.com/caotiensinh/MCP_adobe/actions/runs/38055560577 **SUCCESS for log instrumentation, not for probe/readback**.
- Installation/backup PASS, gateway restarted (old PID 14516 → new 2012), Illustrator preserved. Preflight `blockedAt=document`, `panelBusy=false`, `activeRequest=null`, `unresolved=[]`.
- Exact observed upstream logs:
  - `2026-10-10 22:27:26,199 HOST_TRACE start fence=False priorCompletion=None generation=0 command_type=CommandMetadata`
  - `2026-10-10 22:27:31,207 HOST_TRACE result type=dict error=[R005] Client wait timed out after 5.0s [connection_probe]; host outcome unknown fence=True priorCompletion=False generation=0`
  - `CALLBACK_TRACE_EVENT_COUNT=2`, `CALLBACK_LOG_ACCEPTANCE=PASS`.
- **No CEP_CALLBACK event was received for the 5-second probe**. This is positive evidence that outbound host wait timed out but is not yet evidence whether CEP received the request, ran `evalScript`, or sent a late completion. A single timeout does NOT prove missing callback permanently.
- `READ_ONLY_PROBE_RESULT={error:true,structured:null}`. After probe, trusted fence may exist. Do not send mutation or blind retry.
- Task 01 scope: real upstream request-and-timeout instrumentation PASS. End-to-end callback receipt/ACK correlation is still unproven and remains a prerequisite for task 02. Task 02 (probe_fence recovery) and live house remain FAIL.


## 2026-10-10 22:30–22:44 JST — Mục 02: late-callback fix vs host evalScript timeout
- Read-only GUI assessment run https://github.com/caotiensinh/MCP_adobe/actions/runs/38055946974: Illustrator process PID 7752 reports Responding=True and IsHungAppWindow=False, window title `MCPAdobe LIVE Two-Story Red Tile House*`; 8081 established. This does **not** prove ExtendScript evaluation is working.
- Instrumented upstream callback shows probe timeout after 5 s and completion ~30 s after dispatch, with pending=False. Commit `4d82e43a279edabdf4d97cd1c13d9871924d4ed0` adds exact requestId+requestToken late completion correlation *after* native handler; does not clear probe_fence. Test commit `3c0a101998e8a4f86ccc2caeb39a76ac53d9a25a` validates incorrect token, incorrect ID, and progress cannot clear; unit test run 38056027934 SUCCESS.
- Runner 38056079085: `CEP_LATE_FENCE_COMPLETION requestId=1`, `LATE_CALLBACK_CORRELATED=PASS`; later 45s probe invalid due upstream ConnectionStatusInput le=30; documented and corrected 30s run 38056434687. At 30.0 s, `[R005]` and completion arrive on timeout boundary; fence not cleared.
- Workflow `illustrator-trusted-probe-race-recovery.yml` commit `f8b6d15a2a5cbb66b5311462885afa61e759d2cd` extended *read-only* probe timeout schema le=30 -> le=60 with backup `connection.py.mcp-adobe-timeout-original.bak`; retry at 45 s on run https://github.com/caotiensinh/MCP_adobe/actions/runs/38056649509 still FAILED: correlation PASS, requestId=2 callback pending=True tokenMatch=True after 30 s, but the callback result is `Error: Illustrator evalScript timeout`. This shows the 30-second host/CEP evalScript watchdog, not Python-only request timeout, is the current decisive blocker.
- Do not increase Python timeout further or clear fence without a clean JSX probe; probe execution itself is timing out inside the host path. Investigate CEP evalScript execution and Illustrator host script dispatch/watchdog (and possible hidden dialog), rather than recreating the entire 38-step document. **Mục 02 overall FAIL** despite passing late-completion correlation subtask.


## 2026-10-10 23:15 JST — focused investigations of 30s race, trusted probe, fence
- Focused code scans run https://github.com/caotiensinh/MCP_adobe/actions/runs/38058550686 and https://github.com/caotiensinh/MCP_adobe/actions/runs/38058852849 find deployed CEP bundle at `%APPDATA%\Adobe\CEP\extensions\com.illustrator.mcp.panel\dist\assets\index.js` (160786 bytes), containing `CSInterface.evalScript` and a distinct **15s payload-read** timer. Neither the bundle nor upstream Python scan revealed a literal `Illustrator evalScript timeout` or 30-second JS watchdog. Do not attribute the 30s error to a verified CEP JavaScript timer without further evidence; Adobe/CEP native evalScript callback timeout remains suspected but not located.
- Win32 visible-window assessment https://github.com/caotiensinh/MCP_adobe/actions/runs/38058909690 shows Illustrator GUI PID **7244** (changed from earlier 7752), Responding=True, normal `illustrator` class title `Adobe Illustrator 2023` and no visible separate titled modal dialog in same PID. This is not proof absence of hidden modal or successful ExtendScript evaluation.
- The process identity/session has changed. Do not assume prior `MCPAdobe LIVE Two-Story Red Tile House*` document or outstanding fences survived; inspect fresh passive `creative.health(probe=False)` before any new call. Avoid replaying artwork.
- Current acceptance: 30s race **FAIL**, trusted probe **FAIL**, probe_fence release **FAIL**. Host callback correlation previously PASS but `Error: Illustrator evalScript timeout` still reproduced even with 45s Python-level timeout.


## 2026-10-10 23:18 JST — passive live fence read after GUI PID change
- Workflow https://github.com/caotiensinh/MCP_adobe/actions/runs/38058981035 completed successfully as a **passive observation**, not host recovery.
- `creative.health(probe=false)` returned structured data, `ready=false`, `blockedAt=probe_fence`, blocking trusted probe `job_2dde26fa6ff9`, `requestId=1`, `connectionGeneration=0`, `priorCompletionObserved=true`; `panel.busy=false`, `activeRequestId=null`, heartbeat healthy. Document status `unknown`, no last-known document name.
- Confirms state after GUI PID transition is STILL FENCED. Do not dispatch ordinary host calls or assert Illustrator readback PASS. The 3 requested acceptance criteria remain **FAIL**: verified 30s timeout resolution, valid trusted host probe, and safe probe_fence release. No artwork writes attempted.
- Narrow subsequent work to the actual `CSInterface.evalScript` completion/host execution path. The installed CEP bundle contains no literal 30s watchdog; native CEP/ExtendScript host behavior is still unproven. A fresh safe probe should only be attempted after establishing an actionable host-side change, not as another blind timeout rerun.

## 2026-10-10 23:35 JST — trusted-probe CEP bundle prepared; MRCAO host absent
- Source: src/mcp_adobe/illustrator_trusted_cep_probe.py; tests/test_illustrator_trusted_cep_probe.py. Unit workflow 38059431326 SUCCESS for restricted dispatch; no host acceptance claimed.
- Windows workflow 38059969258: RESTRICTED_PROBE_DEPLOY_FILE=PASS, CEP_RELOAD_VERIFIED=NO, TRUSTED_HOST_ACCEPTANCE=NOT_YET_PROVEN; original bundle retained as index.js.before-mcp-trusted-probe.bak.
- Windows preflight 38060192173 proved RUNNER_HOST=MRCAO and RUNNER_NAME=windows, CEP_PROCESS_COUNT=0 and no Illustrator.exe processes returned. This currently prevents activating new CEP JS and testing actual trusted probe or safe probe_fence release.
- Acceptance: trusted probe FAIL/UNPROVEN; probe_fence release FAIL/UNPROVEN. No host writes and no unsafe fence reset. Open Illustrator 2023 and MCP CEP panel on MRCAO before continuing runtime acceptance.
