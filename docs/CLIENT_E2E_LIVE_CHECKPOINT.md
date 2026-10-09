# Client-to-Adobe real E2E — checkpoint 2026-10-09

## Mục tiêu
Lệnh ngôn ngữ tự nhiên từ **Claude Code**, **Gemini CLI** hoặc **ChatGPT custom MCP** phải tạo document/layer qua MCP Adobe trên Windows Photoshop thật. PASS chỉ sau khi một verifier độc lập gọi gateway `creative.layer.list` và `creative.context.get` và tìm thấy marker theo run/attempt.

## Phần đã triển khai (PR #31)
- `scripts/verify_client_adobe_e2e.py`: đọc 5 tools, Photoshop health, layer list chứa marker duy nhất, context từ upstream. Không tin câu trả lời model.
- `.github/workflows/client-adobe-e2e.yml`: Windows self-hosted, test Photoshop thật, Gemini CLI cài trong RUNNER_TEMP, không cài global; kiểm soát job concurrency, không chạy Claude khi credit chưa được bật lại.
- `GEMINI_API_KEY` được đọc từ GitHub Actions secret, không hardcode/print; không có secret thì FAIL với marker rõ. Không đưa key vào GitHub issues/PR/log.
- Claude sẽ chỉ được đưa vào matrix khi repository variable `CLAUDE_CREDIT_READY=true` và user đã khôi phục credit hoặc có CLI auth hợp lệ.

## Live logs đã kiểm chứng
- Run [37930295595](https://github.com/caotiensinh/MCP_adobe/actions/runs/37930295595): Gemini CLI not installed; Claude CLI present, gateway port 8787 LISTEN, CLI trả **Credit balance is too low**.
- Run [37930459265](https://github.com/caotiensinh/MCP_adobe/actions/runs/37930459265): Gemini bootstrap npx `@google/gemini-cli@0.10.0` fail (`could not determine executable to run`).
- Run [37930707212](https://github.com/caotiensinh/MCP_adobe/actions/runs/37930707212): npm exec wrapper fail; `Unknown command: "pm"`.
- Run [37930878362](https://github.com/caotiensinh/MCP_adobe/actions/runs/37930878362): Gemini CLI scoped install succeeded; invoking PowerShell shim failed `node.exe` absent in next-step PATH.
- Run [37931433478](https://github.com/caotiensinh/MCP_adobe/actions/runs/37931433478): Gemini CLI installation and readiness PASS, real client launched; Gemini requires auth, exit 41: `Please set an Auth method ... GEMINI_API_KEY, GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_GENAI_USE_GCA`. `CLIENT_TO_ADOBE_E2E` is still **NOT PASS**.

## Nguyên tắc để tiếp tục
1. Trên GitHub repository Settings → Secrets and variables → Actions → New repository secret, cung cấp `GEMINI_API_KEY` (không nhập vào chat). Tất cả thông tin auth phải ở secret store.
2. Chạy exact-head Gemini workflow mới và poll từng step cho tới khi Photoshop read-back PASS hoặc báo lỗi mới cụ thể. Không rerun mù.
3. Claude: cần khôi phục credit sau đó bật variable `CLAUDE_CREDIT_READY=true`; thực hiện acceptance giống Gemini. Không tính skipped/success job khi test chưa chạy.
4. ChatGPT custom MCP: phải có remote HTTPS OAuth endpoint và quyền custom MCP write trong workspace. Chưa có authenticated endpoint/permission nên **BLOCKED**, không dùng URL loopback giả làm remote.
5. Không merge nhánh/PR #31 khi chưa đạt E2E đúng; giữ draft, không ảnh hưởng `main`, Illustrator, XD hoặc Photoshop live baseline.

## Trạng thái
- Photoshop local MCP live interaction: PASS (run 37925763318).
- Claude → Photoshop từ Claude CLI: BLOCKED (insufficient credit).
- Gemini CLI → Photoshop: BLOCKED (missing CLI auth), code bootstrap PASS.
- ChatGPT → Photoshop: BLOCKED (remote HTTPS/permissions not established).
