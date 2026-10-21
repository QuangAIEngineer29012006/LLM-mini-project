# AI Live Commerce Order Assistant

Website Streamlit, backend FastAPI, SQLite và trợ lý xem/tìm sản phẩm, hỏi giá/tồn kho, đặt đơn bằng Gemini **`gemini-3.5-flash-lite`**. Backend sử dụng lại các service trong `database/shop_db`; frontend lấy catalog, giỏ hàng, đơn và phản hồi chat qua HTTP API.

## Chạy project

Dùng Python 3.12 trở lên. Chạy các lệnh từ thư mục repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Trong `.env`, chọn một trong hai chế độ:

```dotenv
# Chạy Gemini thật: tự điền key local, không commit .env.
LLM_PROVIDER=gemini
LLM_MODEL_ID=gemini-3.5-flash-lite
GEMINI_API_KEY=
```

Hoặc đặt `LLM_PROVIDER=fake` để demo offline không cần key. `FakeLLMClient` là bộ tách câu bằng regex đơn giản, không phải mô hình ngôn ngữ. Khi chưa có `.env`, backend mặc định chạy fake để có thể thử ngay. Không tự chuyển từ Gemini sang fake khi Google báo lỗi.

Mở hai terminal đã activate cùng `.venv`:

```bash
# Terminal 1
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```bash
# Terminal 2
streamlit run app.py
```

Mở [website](http://localhost:8501), [Swagger API](http://127.0.0.1:8000/docs), hoặc [health](http://127.0.0.1:8000/api/health). Nếu cổng 8000 đã có ứng dụng khác, đổi `--port` và `API_BASE_URL` trong `.env` cùng nhau. Khởi động lại cả hai process sau khi đổi cấu hình.

Database tự migrate và seed khi chưa có catalog; khởi động lại giữ nguyên dữ liệu. Không chạy reset database khi API đang hoạt động. Có thể dùng `SHOP_DB_PATH` để tạo một DB demo mới mà không đụng DB hiện tại.

`FRONTEND_MOCK=0` là chế độ tích hợp API thật. `FRONTEND_MOCK=1` chạy frontend cũ độc lập bằng catalog mock riêng; chế độ này không kiểm chứng backend/SQLite. Catalog SQLite có 16 SKU đang bán ở 3 nhóm, cộng 1 SKU ngừng bán. Ví dụ “áo xanh” trong đề bài không khớp áo thun của seed hiện tại, vì chỉ có đen/trắng; hệ thống phải hỏi lại.

## Thử luồng chat

Bạn có thể bắt đầu bằng `Tôi muốn tham khảo sản phẩm, cửa hàng bạn bán những gì?`, `Cho xem áo thun đen size M` hoặc `Cho xem giày dưới 800k còn hàng`. Trợ lý đọc sản phẩm, mô tả, biến thể, giá và tồn từ SQLite. Khi đã xem rõ một sản phẩm/biến thể, có thể hỏi tiếp `Giá bao nhiêu?`, `Mẫu này còn hàng không?` hoặc `Chốt 2 cái`. Nếu đang xem nhiều sản phẩm thì cần chọn rõ sản phẩm trước khi đặt.

1. `Chốt 2 áo thun đen size M`
2. `Tên Khách Demo, SĐT 0912345678, giao về 12 Đường Mẫu, Phường Mẫu, Quận 7`
3. Mở Đơn hàng: đơn chờ xác nhận, tổng 300.000 VND.
4. `Đơn lúc nãy đổi thành 3 cái` chỉ sửa khi phiên có duy nhất một đơn nháp; nhiều đơn thì phải cung cấp mã `DHxxxxxx`.
5. `Áo thun đen size M giá bao nhiêu?` hoặc `Còn áo thun trắng size M không?`

Các thông tin trên chỉ là dữ liệu demo. Trong chế độ Gemini, nội dung tin nhắn và catalog được gửi đến Google để trích xuất; chỉ nhập dữ liệu giả/đã ẩn danh theo đề bài.

## Hoàn thiện evaluation và demo

- [Trạng thái bằng chứng hiện hành](sample_results/STATUS.md): phân biệt kết quả lịch sử, test mới và phần chưa nghiệm thu.
- [Mở form chấm 29 case offline](sample_results/rubric_review/review.html), [hướng dẫn rubric 0/1/2](docs/EVALUATION_REVIEW.md) và [nhận xét AI hỗ trợ](sample_results/rubric_review/assistant_review.md). Điểm do nhóm xác nhận chưa được điền thay.
- [Nghiệm thu trình duyệt thật](docs/BROWSER_ACCEPTANCE.md): 15 kịch bản, dùng sau khi UI mới tích hợp; không sửa frontend trong gói TV5.
- [Kịch bản demo 7 phút](docs/DEMO_RUNBOOK.md), gồm lỗi API, security và phương án chuyển fake minh bạch.

## Kiểm thử và evaluation

```bash
python scripts/test_all.py
python scripts/evaluate.py
python scripts/smoke_frontend.py
# Chỉ chạy khi đã cấu hình key, có sử dụng quota Google:
python scripts/evaluate.py --provider gemini --case-id H01
# Kiểm tra luồng dài hơn, chỉ chạy khi chủ động dành quota:
python scripts/live_catalog_smoke.py --allow-live
```

`test_all.py` chạy riêng bộ test database và bộ test tích hợp/frontend, tránh trùng package `tests`. Evaluation có 18 case trong [tests/test_cases.json](tests/test_cases.json), bổ sung 11 case bám câu ví dụ và cập nhật đơn tại [tests/spec_literal_cases.json](tests/spec_literal_cases.json); kết quả ghi vào `sample_results/evaluation_fake.*` hoặc `evaluation_gemini.*`. Kết quả fake chỉ chứng minh luồng rule/validation/DB trên bộ case này. Điểm rubric tự động 0/2 cần được người đọc chấm lại 0/1/2 trước khi báo cáo chất lượng Gemini.

Xem [kết quả offline](sample_results/evaluation_fake.md), [failure analysis](sample_results/failure_analysis.md), [kiến trúc](docs/architecture.md), [hợp đồng API](docs/API.md) và [database](database/docs/DATABASE.md).

## Phạm vi và giới hạn

- Sáu intent: `browse_catalog` bổ sung cho năm intent bắt buộc `create_order`, `check_stock`, `check_price`, `update_order`, `unknown_or_handoff`. Nhánh xem/tìm hàng chỉ đọc database; giá/tồn kho lấy lại từ DB, không dùng giá do model sinh.
- Đơn web/chat dừng ở `pending_confirmation`. API khách hàng không cung cấp thao tác confirm, trừ kho, thanh toán, hủy đơn hoặc quản trị catalog.
- `handoff` đánh dấu cần người xử lý và ghi audit; chưa có hàng đợi nhân viên hoặc tích hợp gửi tin bên ngoài.
- Bearer token demo tồn tại 24 giờ, chỉ lưu hash trong DB, có endpoint thu hồi. Mỗi phiên Streamlit mới có token mới; chưa có đăng nhập/khôi phục tài khoản. Dùng một process API cho demo; rate limit nằm trong bộ nhớ process. Không có hạn mức ngân sách tổng cho API Google.
- FakeLLM chỉ hỗ trợ mẫu câu đơn giản trong hướng dẫn; không thay thế khả năng hiểu tiếng Việt của Gemini. Mỗi lượt chat sửa một dòng đơn; trường hợp nhiều dòng cùng sản phẩm nên sửa qua web.
- Kiểm tra evidence/substrings và allowlist giảm bịa thông tin nhưng không chứng minh đầy đủ ngữ nghĩa. Regex chống injection chỉ là một lớp; quyền API, schema, catalog và transaction mới giới hạn thao tác cuối cùng.
- Prompt zero-shot `shop-assistant-v3`, context tối đa 6 sản phẩm và tên các sản phẩm vừa xem, message tối đa 500 ký tự, output tối đa 2048 token. Không fine-tune vì MVP có catalog nhỏ và business rule xác định được bằng code.
- Quota theo thông tin người dùng: Gemini 3.5 Flash-Lite dùng ngân sách ứng dụng 500 request/model/ngày; khi dùng lại Gemini 3.6 Flash phải đặt giới hạn tối đa 20. Mặc định `LLM_MAX_RETRIES=0` để một tin nhắn cần AI chỉ gọi một lần. Bộ đếm dùng SQLite riêng `database/data/llm_usage.db`, cộng từng HTTP attempt trước khi gửi, tồn tại qua restart và dùng chung giữa các phiên. Ngày tính theo Pacific Time theo [tài liệu Google](https://ai.google.dev/gemini-api/docs/rate-limits). Bộ đếm bắt đầu từ lúc thêm tính năng, không biết các lượt gọi trước đó hoặc từ ứng dụng khác; số sử dụng thực của project vẫn xem ở AI Studio.
- Các câu catalog rõ nghĩa như câu hỏi trong ảnh và câu hỏi tiếp `giá bao nhiêu`, `mẫu này còn hàng không` được xử lý trực tiếp bằng rule đọc SQLite, không tốn quota. `interpretation_source=local_catalog` phân biệt với lượt model thật `gemini`. Không lấy nội dung giá/tồn từ câu trả lời cache; luôn đọc lại DB. Những cách diễn đạt khác vẫn đi qua Gemini và cùng lớp business validation.
- HTTP timeout 12 giây/lần. Có thể cấu hình tối đa 2 retry hữu hạn nếu chủ động chấp nhận sử dụng thêm quota; mỗi retry vẫn được cộng vào giới hạn ngày. Tôn trọng `Retry-After`; nếu cần đợi trên 3 giây thì trả lỗi cho người dùng thử lại. Timeout frontend mặc định 55 giây.
- Kiểm tra live ngày 21/10: key hợp lệ, request tối giản gọi được Gemini 3.8 Flash; luồng JSON backend gặp 503/timeout kể cả probe 60 giây. Đây là kết quả lịch sử trước khi chuyển model; xem [báo cáo live](sample_results/gemini_live_test.md). Adapter dùng [API Google](https://ai.google.dev/api/generate-content), schema ở `generationConfig.responseFormat.text`.
- Cấu hình hiện tại là Gemini 3.5 Flash-Lite. Kết quả [catalog_live_smoke.json](sample_results/catalog_live_smoke.json) thuộc lần kiểm tra Gemini 3.6 Flash trước đó; không dùng kết quả này để đánh giá model mới. Xem bộ test theo đề Markdown của model hiện tại tại [báo cáo ngày 21/10](sample_results/md_cases_2026-10-21/REPORT.md).
