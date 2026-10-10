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
