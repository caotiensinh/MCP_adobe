# MCP Adobe — trạng thái live và tích hợp ChatGPT / Claude / Gemini

Cập nhật: 2026-10-09. Tài liệu này phân biệt **đã kiểm chứng bằng log** và **hướng tích hợp chưa chạy E2E**.

## 1. Trạng thái đã kiểm chứng

- Illustrator: live canvas build qua CEP; checkpoint ghi nhận 13/13 bước, tương tác hiển thị thật.
- Adobe XD 57.1.12.2: official XD command/app.editDocument; 6 nodes được đọc lại với name/GUID, queue=0; exact-head `9bdcc6ab2e3c8f384877b15109cf807ddd27f6f9`, run `37924716084`.
- Photoshop 2023: Windows self-hosted run [37925763318](https://github.com/caotiensinh/MCP_adobe/actions/runs/37925763318), job `113804184601` SUCCESS; `creative.health` trả Photoshop connected; 900x600 RGB document, 5 text layers + background; X=96→136→96; opacity=100→60→100; app window interactive cuối run. `creative_live_build` trả 6/6, nhưng các bước riêng lẻ ghi `accepted_unverified`; bằng chứng đọc lại là `creative.layer.list` và `creative.context.get`, không đồng nhất hai loại bằng chứng.
- PR [#28](https://github.com/caotiensinh/MCP_adobe/pull/28) merged vào main tại `6ef20e710ffcd81978ff648af1f107c270009aa7`. Regression fixes PR [#29](https://github.com/caotiensinh/MCP_adobe/pull/29) merged tại `902d47d7a96250ff775d55cc188cafba932f921b`; Windows run `37926993303` 204/204 tests PASS.
- Photoshop 24 UXP compatibility PR #22 còn độc lập; KHÔNG đánh đồng Photoshop 2023 live PASS với Photoshop 24 PASS.
- **Chưa kiểm chứng:** direct natural-language E2E từ từng client ChatGPT, Claude và Gemini vào gateway trong môi trường account cụ thể; không được đánh dấu PASS chỉ vì gateway/test workflow chạy.

## 2. Kiến trúc triển khai

```text
Claude Desktop/Claude Code   Gemini CLI             ChatGPT custom MCP app
     local stdio/http         local HTTP/stdio             remote HTTPS
               \                 |                       /
                 --> MCP Adobe gateway (five tools) <----
                          | localhost Adobe bridges
                Photoshop / Illustrator / XD
```

Gateway trên máy Windows có Adobe: `http://127.0.0.1:8787/mcp` (loopback only). KHÔNG dùng URL 127.0.0.1 làm remote endpoint từ cloud. Tránh công khai cổng 8787, cổng Illustrator, XD WebSocket hoặc Photoshop bridge không xác thực. Remote cần HTTPS, authentication, host binding và access policy; đặt reverse proxy/tunnel có bảo vệ; giới hạn authorized clients. Đọc kỹ threat model trước khi expose write tools.

Five gateway tools: `creative_discover`, `creative_read`, `creative_write`, `creative_live_build`, `creative_authorized_write`. Ưu tiên `creative_live_build` cho nhiều bước có thể quan sát, `creative_read` cho read-back. Destructive/native-script không được tự ý chạy qua normal write.

## 3. Claude

### Claude Code / CLI

Claude Code hỗ trợ MCP qua stdio/HTTP. Với persistent local host đang chạy trên **cùng Windows desktop có Adobe**:

```powershell
claude mcp add --transport http adobe-creative http://127.0.0.1:8787/mcp
claude mcp list
```

Kiểm tra lệnh theo phiên bản CLI đang cài và đảm bảo client dùng được transport streamable HTTP. Nếu muốn local stdio thay cho persistent host, sử dụng installed `mcp-adobe` executable theo hướng dẫn README, cấu hình đường dẫn binary chính xác; không khởi động duplicate Adobe bridge một cách tùy tiện.

### Claude.ai / remote custom connector

Settings / Connectors / Add custom connector (tên menu có thể đổi); trỏ đến endpoint HTTPS có auth, không trỏ localhost. Claude cloud cần truy cập được endpoint từ hạ tầng Anthropic; localhost/private-only VPN không tự hoạt động. Thử tools/list, creative_discover rồi mới write; yêu cầu xác nhận trước mutation.

Docs: https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp

## 4. Gemini CLI

Gemini CLI chính thức hỗ trợ stdio, SSE, Streamable HTTP; dùng local HTTP endpoint trên chính máy Adobe:

```powershell
gemini mcp add -s user -t http adobe-creative http://127.0.0.1:8787/mcp
gemini mcp list
```

Hoặc chỉnh `~/.gemini/settings.json` (Windows: `%USERPROFILE%\.gemini\settings.json`):

```json
{
  "mcpServers": {
    "adobe-creative": {
      "httpUrl": "http://127.0.0.1:8787/mcp"
    }
  }
}
```

**Lưu ý:** xác thực key config `httpUrl` theo phiên bản Gemini CLI đang cài; lệnh `gemini mcp add` ưu tiên hơn cấu hình thủ công. Trong Gemini CLI dùng `/mcp` để xem discovery. Đừng coi hỗ trợ Gemini CLI là bằng chứng Gemini web app tự hỗ trợ custom MCP server.

Docs: https://geminicli.com/docs/tools/mcp-server/

## 5. ChatGPT

ChatGPT web tùy workspace/plan: custom MCP apps và write/modify thông qua Developer Mode đang rollout cho Business / Enterprise / Edu. Quyền dùng full MCP và menu quản lý phải kiểm tra trên account thực; **không giả định Plus được phép write MCP tùy chỉnh**. Pro có thể gặp read/fetch developer access, không đồng nghĩa full write.

Các bước khi workspace đủ điều kiện:

1. Đặt gateway sau một **HTTPS authenticated MCP endpoint** có khả năng kết nối từ ChatGPT cloud; tuyệt đối không trỏ `127.0.0.1`.
2. Admin/owner bật developer mode và quyền custom apps theo workspace.
3. Apps → Create; nhập URL, auth; Scan Tools.
4. Xác minh năm tool, select draft app trong chat; thử `creative_discover` → `creative_read` → yêu cầu dựng hình → `creative_live_build` → `creative.layer.list` + context read-back.
5. Lưu evidence client invocation ID, operation_id, Adobe document/layers, confirmation prompt và undo. Không claim E2E trước khi hoàn thành.

Docs: https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt

## 6. Acceptance chung cho mỗi client (chưa PASS)

- Client tự discovery được 5 tools và đọc capabilities thật, không mock.
- Lệnh tự nhiên “Create a Photoshop title card and show each step” thực sự gọi `creative_live_build` vào gateway đúng máy Adobe.
- Photoshop trước/sau thể hiện document 900x600, các layer cụ thể xuất hiện; read-back live từ Photoshop (document ID, layer names/bounds).
- Move +40px; opacity=60; undo opacity; undo move; đọc lại chính xác từng bước.
- Photoshop vẫn interactive, không treo/terminate; không làm hỏng Illustrator/XD hiện có.
- Test negative: khi Photoshop chưa chạy/bridge không có, phải báo lỗi thật; destructive/native-script cần separate authorization; wrong document must not be mutated.
- Capture CI log, screenshot hoặc video trực tiếp màn hình Adobe nếu cần chứng minh hiển thị; log-only không đủ khẳng định human-watched visual change.

## 7. An toàn và kiểm thử

- Runner chỉ test **exact HEAD** và phải đọc log của mọi step, không rerun mù.
- Windows desktop interactive: runner session phải truy cập cùng user/desktop session có Adobe. `MainWindowHandle`/port open chỉ là preflight, chưa phải acceptance.
- Bất kỳ private tunnel nào phải enforce TLS, OAuth/token, least privilege, localhost destination, no inbound access tới Adobe internal bridges, audit logs đã redacted.
- Không chia sẻ access tokens, Photoshop documents hoặc screenshot có dữ liệu cá nhân trong artifacts public.
- Documentation-only changes không tạo ra client E2E PASS. Merge tài liệu riêng và theo dõi implementation/tests trong các nhánh kế tiếp.

## 8. Các bước ưu tiên tiếp theo

1. Claude Code local HTTP smoke + tool discovery + real live E2E.
2. Gemini CLI local HTTP tương đương, cùng acceptance.
3. ChatGPT remote endpoint có authentication, quyền workspace phù hợp; remote smoke và live read-back sau khi được phép.
4. Tự động hóa test matrix theo từng client; lưu run_id, exact SHA, operation IDs; cập nhật trạng thái PASS theo bằng chứng.
