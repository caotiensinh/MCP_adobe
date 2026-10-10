# Canvas region targeting — khoanh vùng rồi yêu cầu AI sửa

## Mục tiêu
Người dùng nhìn thấy document Photoshop/Illustrator/XD, kéo chuột khoanh vùng, rồi chat ngắn như “đổi chữ này thành màu đỏ”. Hệ thống tự lấy vị trí, tìm đối tượng, nhận diện các layer liên quan, hỏi khi có nhiều lựa chọn, thực hiện thao tác reversible có sẵn trong MCP Adobe và read-back. Không đổi kết nối MCP, OAuth, transport hoặc năm tool hiện có.

## Luồng UX mục tiêu
1. **Chọn vùng:** preview trong companion overlay, người dùng kéo rectangle/lasso. Khung có tọa độ preview và ID/timestamp của document được đọc trước khi khoanh.
2. **Định vị:** lấy scale, offset, dimensions rồi đổi tọa độ viewport → document pixels. Không suy đoán tọa độ Windows màn hình bằng DPI; phải refresh nếu rotate/scroll/zoom metadata thiếu.
3. **Phân tích:** lấy layer bounds, visibility, lock state và order từ Adobe bridge; gọi read-only resolver tìm candidates bằng tỷ lệ phủ lên vùng chọn; preview highlight layer đúng.
4. **Thực hiện:** nếu không rõ chỉ một đối tượng hoặc nội dung raster không có layer riêng, không được edit “đoán mò”; hiện lựa chọn đối tượng/mask. User chat “to chữ này lên 20%” → tool-capability tương ứng, có context target ID và doc ID.
5. **Đọc lại:** gọi `creative_read` state/layer list/preview, so sánh trước/sau, hỗ trợ undo. Không coi acknowledgement là bằng chứng sửa đúng.

## Triển khai hiện tại trong PR này
- `src/mcp_adobe/region_targeting.py`: pure geometry and read-only layer resolver, bảo vệ document identity, reject bounds xấu/rotated preview/out-of-document, báo ambiguous/no_candidate.
- `tests/test_region_targeting.py`: các ca scale/offset, nhiều layer, locked/hidden/background, stale document và vùng rỗng.
- Không sửa core gateway, Photoshop adapter hay MCP transports.
- **Chưa có UI overlay thao tác chuột trên canvas thật, chưa có bridge đồng bộ viewport từ Photoshop/Illustrator/XD, chưa có region edit E2E.** Module này chỉ là nền tảng định vị hình học, không phải sản phẩm hoàn chỉnh.

## Các gate còn phải thực hiện
A. Companion annotation overlay tương tác thật (Windows) / extension Adobe panel; người dùng bôi vùng và nhìn thấy khung/highlight.
B. Per-app read-only bridge lấy document identity, zoom/pan/scroll, layer IDs và bounding boxes; đối chiếu canvas pixels với preview CSS pixels.
C. Tích hợp `annotation` với một request-scoped context tới model/client: prompt ngắn + rectangle + candidates; không chỉnh sửa tool transport.
D. Action executor cho sửa text/style/transform trên **layer ID xác minh**, policy/confirmation và compare-before-after.
E. Windows self-hosted live acceptance: khoanh đúng một target; hai target chồng nhau → hỏi; document đổi → fail; undo phục hồi đúng; bằng chứng log/ảnh/video.

## An toàn
- Không xóa/sửa ảnh gốc dựa trên pixel rectangle mơ hồ, không chạy arbitrary script, không tự gửi screenshot cá nhân đến dịch vụ bên ngoài.
- Tất cả edits qua policy hiện hữu, write reversible; high-risk giữ authorized-write.
- Khi image raster không thể tách đối tượng bằng layer, cần explicit mask/selection và xác nhận.


## Prototype UI trên branch — 2026-10-10
- `ui/region_annotation.html`: trang companion HTML độc lập; mở bằng trình duyệt. Người dùng tải preview từ file cục bộ, paste metadata đã kiểm chứng do Adobe cung cấp, kéo rectangle, chọn layer ứng viên, nhập lệnh ngắn, sao chép JSON `mcp-adobe-region-request/v1` cho agent.
- Không cần server riêng; không fetch/upload ảnh, không yêu cầu hoặc sửa cấu hình kết nối MCP, không thực hiện mutation tự động.
- JSON xuất gồm `document_identity`, `document_dimensions`, `selected_region` (document pixels), `selected_layer`, `user_instruction` và flags `requires_live_document_identity_check`, `requires_live_layer_readback`, `execute_automatically=false`.
- Chỉ dùng preview FULL document 1:1 hình học (có thể resize CSS); nếu preview cắt/rotate thì tọa độ sẽ sai — chưa nên dùng vào Adobe thật.
- Ví dụ metadata thử nghiệm: `{"application":"photoshop","document_identity":"doc-demo-1","width":900,"height":600,"layers":[{"id":123,"name":"Tiêu đề","bounds":{"left":80,"top":70,"right":550,"bottom":160},"visible":true}]}`.
- Test: [run 38024359335](https://github.com/caotiensinh/MCP_adobe/actions/runs/38024359335) PASS 10/10 và JavaScript `node --check` PASS. Đây là unit/static verification, **không phải Windows Photoshop live E2E**.
- Cần triển khai tiếp bridge tự điền metadata và preview từ Adobe, layer-ID resolution đảm bảo revision match, lớp phủ bên trong Adobe hoặc companion overlay xác định zoom/pan, rồi execution có confirm và read-back.


## 2026-10-10: Tự xuất metadata từ Photoshop
- Có thêm script read-only `scripts/export_region_metadata.py`. Trên máy Adobe, có thể chạy `uv run python scripts/export_region_metadata.py --output adobe_region_metadata.json`. Script dùng **MCP creative_read hiện có**, không cấu hình lại server.
- Nhập `adobe_region_metadata.json` trong giao diện `ui/region_annotation.html` bằng nút nhập metadata; không cần gõ JSON thủ công.
- Bảo vệ: nếu Adobe không trả `document.id`, kích thước hoặc layer ID/bounds, script **fail closed**; tuyệt đối không tự tính đoán layer.
- CI [run 38024541072](https://github.com/caotiensinh/MCP_adobe/actions/runs/38024541072) 14/14 unit/static tests PASS. Live Windows read-only probe [run 38024572699](https://github.com/caotiensinh/MCP_adobe/actions/runs/38024572699) chạy độc lập.
- Phần nhập preview ảnh vẫn cần thủ công; chưa thực hiện phát hiện layer bằng AI vision hay cập nhật Photoshop tự động; việc hoàn tất E2E chỉ đánh dấu khi có bằng chứng trên thiết bị thật.


## Live Windows checkpoint 2026-10-10
- [Run 38024572699](https://github.com/caotiensinh/MCP_adobe/actions/runs/38024572699): tests PASS; Windows live metadata failed on `creative.context.get` due to MCP tool error.
- [Run 38024708941](https://github.com/caotiensinh/MCP_adobe/actions/runs/38024708941): unit/static lane PASS; Windows live lane failed earlier at `creative.health` with `MCP read rejected; content_block_types=['TextContent']`. No layer metadata produced.
- **Không giả định bridge/Photoshop đang sẵn sàng**: các runs trước từng PASS health, nhưng health của phiên này FAIL. Cần xác nhận Photoshop UI mở, bridge đang connect, active document và đúng Windows user session; không rerun mù khi health chưa PASS.
- Cả hai Windows probes read-only: không sửa canvas, không đổi cấu hình transport/MCP.
- Tổng: 14/14 unit/static PASS, live Photoshop metadata vẫn BLOCKED. Agent edit E2E chưa PASS.


## Shared workflow for three Adobe applications — 2026-10-10
- Cả **Adobe Photoshop**, **Adobe Illustrator** và **Adobe XD** dùng chung giao diện `ui/region_annotation.html`, schema `mcp-adobe-region-request/v1`, engine vùng `src/mcp_adobe/region_targeting.py`.
- Exporter `scripts/export_region_metadata.py --application photoshop|illustrator|xd` chỉ dùng gateway `creative_read` hiện tại và **không sửa MCP transport/auth**.
- Photoshop: đọc `creative.context.get` + `creative.layer.list`. Illustrator: đọc `creative.context.get` + `creative.layer.list`. XD: `creative.context.get` + `creative.selection.get` (chỉ node đã chọn; XD bridge chưa có `creative.layer.list`). Mỗi app phải trả stable document ID, dimensions, target ID và bounds; thiếu thì fail closed.
- Đối với XD, chưa hỗ trợ tự phân tích *mọi node dưới điểm khoanh*: cần mở rộng UXP bridge để đọc scenegraph/hit-test read-only rồi mới coi selection-free region detection là PASS. Thao tác apply pending của XD vẫn theo cơ chế phê duyệt hiện hữu.
- Unity UI không đồng nghĩa ba app đã có live E2E. Photoshop runtime health từng FAIL trong [run 38024708941](https://github.com/caotiensinh/MCP_adobe/actions/runs/38024708941). Illustrator, XD metadata live chưa chứng minh.
- Workflow push chỉ chạy unit/static tests, job Windows live metadata hiện opt-in qua manual `workflow_dispatch`, tránh lặp test khi app desktop/bridge chưa sẵn sàng.
- [CI 38025228494](https://github.com/caotiensinh/MCP_adobe/actions/runs/38025228494): 18/18 tests PASS + JS syntax PASS; Windows live job SKIPPED intentionally.


## XD region targeting — scenegraph contract, 2026-10-10

Added pure read-only `src/mcp_adobe/xd_scenegraph_targeting.py` to normalize a **complete** XD document scenegraph, flatten nested groups (global document bounds), reject stale document IDs, duplicate/missing node IDs, malformed bounds, hidden/locked nodes and excessive node counts. Integrated `normalize_snapshot(..., application="xd")` to use this format when the bridge supplies a complete snapshot. Supports region hit testing without preselecting a node **at the geometry-engine layer**.

**Critical live gap:** The current XD MCP adapter exposes `creative.selection.get`, not a complete scenegraph capability. Therefore this commit **does not** make live Adobe XD support selection-free targeting. The XD UXP bridge must first produce `{document_id,complete:true,nodes:[...]}` via a safe read-only operation, with stable IDs and global document coordinates. Until then, XD remains selection-only / fail-closed. No new MCP transport, auth, or write capability has been added.

Unit and JS syntax tests: [run 38025448611](https://github.com/caotiensinh/MCP_adobe/actions/runs/38025448611), 28/28 PASS; Windows live probe intentionally skipped. No three-app live acceptance claimed.


## 2026-10-10 — XD UXP bridge scenegraph implementation (read-only)
- Implemented `xd.scenegraph.snapshot` in actual `adobe-xd-plugin/main.js`: traverses scenegraph root children and nested nodes, stable guid, globalBounds, visibility/lock flags, and a bounded node count. This method never calls editDocument or changes selection.
- Added read-only `creative.scenegraph.list` capability in `src/mcp_adobe/xd.py`, keeping existing five top-level MCP tools and WebSocket/authorization untouched.
- `scripts/export_region_metadata.py --application xd` now calls `creative.scenegraph.list` rather than relying on `creative.selection.get`.
- [Run 38027209235](https://github.com/caotiensinh/MCP_adobe/actions/runs/38027209235): Python unit tests **29/29 PASS** and a Node VM contract test invoking real UXP dispatch with a mocked scenegraph **PASS**. JS syntax PASS.
- Limitations: actual XD plugin installation/interactive desktop live read not yet tested; current XD document.info snapshot may not expose stable document dimensions, so metadata export can still correctly fail closed. Need define an artboard/preview coordinate frame with origin, document identity and synchronized preview before real region editing.
- No claim of Photoshop, Illustrator, or XD live region-edit E2E; PR must stay separate from main until acceptance.


## 2026-10-10 — XD artboard coordinate frame
- Implemented `xd.canvas.frame` read-only UXP dispatch; it computes the bounding union of root Artboards in global document coordinates, including negative offsets. It rejects an XD document without measurable artboards; never guesses Windows/screen pixels or writes to document.
- Added adapter `creative.canvas.frame` as an XD read-only capability through the five existing MCP tools, without changing MCP transport, OAuth or WebSocket connection.
- `scripts/export_region_metadata.py --application xd` now reads `creative.scenegraph.list` + `creative.canvas.frame`, confirms matching document ID and rebases node `globalBounds` to the artboard-union origin. Metadata includes `coordinate_frame`. **Preview must represent the same complete artboard-union frame**, or targeting is not safe.
- [Run 38027331897](https://github.com/caotiensinh/MCP_adobe/actions/runs/38027331897): 31/31 Python tests PASS, Node VM plugin-dispatch test PASS, no-network/no-write static checks PASS. Real XD live UXP acceptance still unproven.


## 2026-10-10 preview/frame safety gate
- Companion UI `ui/region_annotation.html` now checks full-preview image aspect ratio against exported document dimensions before calculating targets. Changing metadata or image resets the selected layer to avoid stale selections.
- XD `coordinate_frame.space=artboard_union` requires an explicit `preview_frame_verified=true` from a trusted preview source; without it, the UI refuses selection. This field is **not currently generated by the exporter** and must not be set just to bypass the safety gate. Actual Adobe preview acquisition and frame binding is pending.
- Outgoing handoff includes preview dimensions, coordinate frame, and `requires_preview_revision_check=true`. This is still a review payload, **not an automatic edit or proof of synchronized preview**.
- [CI run 38028757545](https://github.com/caotiensinh/MCP_adobe/actions/runs/38028757545): 33/33 Python tests PASS; XD UXP VM contract and JS syntax PASS. No live Adobe writes.


## 2026-10-10 — Direct raster preview acquisition phase
- `scripts/capture_region_preview.py --application photoshop --output path.png` calls **existing** `creative_read / creative.document.preview` and accepts only an actual MCP ImageContent PNG or JPEG block with matching binary signature and bounded size. It does not accept agent prose or an export acknowledgement as preview evidence. No MCP transport/auth changes.
- The returned image **is not yet bound** to document identity, revision, or preview coordinate frame. The script explicitly prints `PREVIEW_FRAME_BINDING=UNVERIFIED` and must **not** enable automatic region editing. Any mismatched/lacking image data fails closed.
- Illustrator currently has document export operations that are classified FILE_WRITE, but no audited read-only `creative.document.preview` capability; running exports would violate this read-only step. XD UXP scenegraph and frame readers do not produce raster preview yet. No fake previews for either application.
- [CI 38028982017](https://github.com/caotiensinh/MCP_adobe/actions/runs/38028982017): 38/38 unit tests PASS + XD UXP no-network contract PASS. A Photoshop live preview call and same-revision document pairing remain to be verified on Windows in an interactive session; Adobe apps are not yet live E2E PASS.
