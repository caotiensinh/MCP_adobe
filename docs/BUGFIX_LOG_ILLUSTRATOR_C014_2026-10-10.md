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
