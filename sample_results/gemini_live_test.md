# Kiểm tra Gemini thật ngày 21/10/2026

Model cấu hình và model trả về trong probe tối giản: `gemini-3.8-flash`. Tất cả luồng backend dùng SQLite tạm; không sử dụng database vận hành để tạo/sửa đơn.

## Kết quả

| Kiểm tra | Kết quả quan sát |
|---|---|
| Key và quyền truy cập model | `GET /v1beta/models/gemini-3.8-flash` trả HTTP 200; model có `generateContent` |
| Request sinh text tối giản | HTTP 200, text `OK`, mất 17,59 giây; giới hạn output 64 token khiến finish reason là `MAX_TOKENS`, nên đây chỉ là probe kết nối |
| Chat backend với cấu hình hiện tại | Có response Google HTTP 503 `UNAVAILABLE`, thông báo model đang có nhu cầu cao; backend trả route `failed_validation`, error `llm_unavailable` |
| Chat backend, timeout 30 giây, không retry | `ReadTimeout` sau 30,09 giây; route `failed_validation/llm_timeout`, không trả order |
| Thử cấu hình thinking `MINIMAL` | Google trả HTTP 400: model không hỗ trợ mức này ở endpoint/tài khoản hiện tại. Không đưa cấu hình này vào source |
| Thử cấu hình thinking `LOW`, timeout 30 giây, không retry | `ReadTimeout` sau 30,11 giây. Chỉ là thử nghiệm trong process, không thay source |
| Chat backend nguyên payload, timeout 60 giây, không retry | `ReadTimeout` sau 60,11 giây; route `failed_validation/llm_timeout`, không trả order |
| Unit/integration tests không phụ thuộc Google | 51 test frontend/backend/LLM + 79 test database đạt trong lượt kiểm tra trước khi chuyển key |

File chi tiết: `gemini_minimal_probe.json`, `gemini_backend_probe.json` (thử MINIMAL), `gemini_backend_probe_low.json`, `gemini_backend_probe_60s.json`.

## Kết luận và giới hạn

Key hợp lệ và đã có bằng chứng gọi được model thật. Chưa có lượt extraction JSON của backend hoàn thành thành công trong các probe này. Chưa chạy toàn bộ evaluation 18 case với Google vì request backend liên tiếp gặp 503/timeout; không báo cáo các kết quả fake như chất lượng Gemini.

HTTP 503 nêu rõ tình trạng quá tải ở một lần gọi; các lần timeout không đủ bằng chứng để quy toàn bộ lỗi cho quá tải hoặc kết luận payload/backend đúng hoàn toàn. Request đơn giản thành công cũng không chứng minh luồng tạo đơn đã hoạt động.

Các thay đổi thử nghiệm timeout/thinking chỉ áp dụng cho process kiểm tra. Model và cấu hình source được giữ nguyên. `.env` local đã bật `LLM_PROVIDER=gemini`; cần chạy lại phép thử backend và evaluation khi dịch vụ phản hồi ổn định để kiểm chứng đầy đủ. Không tự chuyển model hoặc fallback sang fake.

## Key và cấu hình local

Key được người dùng lưu ban đầu trong `.env.example`. Đã chuyển sang `.env`, quyền file `0600`, xác nhận `.env` được `.gitignore` bỏ qua, và để trống key trong `.env.example`. Không chép key vào báo cáo/log. Không yêu cầu người dùng gửi key qua chat.

Tham chiếu khi thử thinking: [tài liệu Google](https://ai.google.dev/gemini-api/docs/generate-content/thinking). Kết quả HTTP trực tiếp được ưu tiên khi tài liệu và endpoint thực tế không trùng nhau.
