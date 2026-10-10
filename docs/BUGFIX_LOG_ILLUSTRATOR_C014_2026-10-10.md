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
