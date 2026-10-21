# Sửa chat catalog và giới hạn quota ngày 21/10/2026

## Nguyên nhân câu trả lời trong ảnh

Audit của request cũ có `model_id=gemini-3.6-flash`, prompt `order-extraction-v1`, schema hợp lệ, intent `unknown_or_handoff`. Prompt cũ chỉ có 5 intent cho đặt hàng/giá/tồn/sửa đơn và handoff, nên chưa có nhánh trả lời câu hỏi xem catalog.

## Bản sửa

- Thêm `browse_catalog`, prompt `shop-assistant-v2`, đọc tên/mô tả/biến thể/giá/tồn từ SQLite đang dùng cho trang Sản phẩm.
- Lọc nhóm hàng, màu/size, khoảng giá và hàng còn tồn; câu hỏi chưa xác định SKU vẫn xem được giá các biến thể.
- Lưu ID/SKU vừa hiển thị ở context; hỏi tiếp giá/tồn hoặc đặt hàng không chọn đại một sản phẩm khi còn nhiều lựa chọn.
- Xem sản phẩm là thao tác đọc; chỉ yêu cầu mua rõ ràng, xác định SKU, đủ giao nhận mới tạo đơn nháp.
- Các mẫu catalog rõ nghĩa và câu hỏi tiếp rõ nghĩa đọc thẳng DB, gắn `interpretation_source=local_catalog`; không gọi FakeLLM trong chế độ Gemini, không cache giá/tồn cũ.

## Bằng chứng

| Kiểm tra | Kết quả |
|---|---|
| Câu hỏi đúng như ảnh bằng Gemini thật | HTTP 200, modelVersion `gemini-3.6-flash`, intent `browse_catalog`, trả 6 sản phẩm; xem `catalog_live_probe.json` |
| Live smoke trước khi dừng theo quota | 4 lượt kiểm tra đã hoàn tất và đạt: catalog, chi tiết, hỏi tiếp giá, hỏi tiếp tồn; `catalog_live_smoke.json` ghi 9 attempt đã hoàn tất gồm lỗi 503/timeout và retry |
| Phạm vi live smoke | Đã dừng process sau khi người dùng thông báo 20 RPD; có thể có một attempt đang chờ/gửi bị ngắt. Không có số tổng chính xác của mọi lượt trước đó; không tuyên bố đủ 8 case hoặc full Gemini evaluation |
| Test offline mới và cũ | 68 test frontend/backend/LLM/quota + 79 test database = 147 PASS |
| Evaluation fake | 18/18 case PASS, không dùng làm điểm model Gemini |
| UI integration | 10 bước qua 6 màn hình, HTTP backend + SQLite tạm, PASS |
| UI đang chạy | Câu hỏi trong ảnh hiển thị catalog thay cho handoff; `catalog_chat_ui.png`. Audit mới: `model_id=local-catalog`, `route=catalog_shown`, token null |
| Database vận hành | SHA-256 nội dung products/product_variants/inventory/product_aliases không đổi: `357a1ce32d5672a3e8256053861fbbd6d96288cc74766f74e83e91a7793c64e2` |

## Quota 20 RPD

Đã dừng các lượt gọi thật còn lại. `.env` và mặc định source đặt `LLM_MAX_RETRIES=0`, `LLM_DAILY_REQUEST_LIMIT=20`. `src/quota.py` dùng SQLite riêng, cộng từng HTTP attempt trước khi gửi và chặn sau 20 attempt/model/ngày Pacific, giữ qua restart và áp dụng giữa các phiên. Mỗi retry nếu bật lại cũng bị tính ngân sách. Các test quota dùng mock/DB tạm và không gọi Google.

Bộ đếm chỉ biết các lượt sau khi triển khai, không đồng bộ usage cũ hoặc từ công cụ khác. Cần xem AI Studio để biết quota thực còn lại hôm nay. Sau khi dừng live smoke, lượt kiểm tra UI dùng local catalog; bộ đếm mới vẫn bằng 0, không phát sinh thêm Google generation request.

Lệnh live smoke yêu cầu `--allow-live`; evaluation Gemini yêu cầu chọn `--case-id`, không mặc định chạy toàn bộ 18 case. Backend đã restart tại cổng 8000 với Gemini 3.6 Flash; website tại cổng 8502.
