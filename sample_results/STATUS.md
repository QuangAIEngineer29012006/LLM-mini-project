# Kết quả kiểm tra bản tổng hợp

Đặt hàng qua bot (22/10): luồng nhận balo xám 15inch → hỏi số lượng/giao nhận → tạo đơn đã kiểm tra bằng Gemini thật trên SQLite riêng. 180 test Python và 12 React đạt. Xem [báo cáo đặt hàng qua bot](chat_purchase_2026-10-22/REPORT.md).

Cập nhật 22/10/2026: đã rà soát React và chạy lại trên macOS; 169 test Python + 9 regression React đạt, npm ci/TypeScript/build đạt, live Gemini qua UI trả đúng giá/tồn. Xem [báo cáo frontend](frontend_review_2026-10-22/REPORT.md) cho phạm vi, ảnh và các giới hạn kiểm tra. Phần bên dưới là kết quả bàn giao ngày 21/10.

Kiểm tra ngày 21/10/2026 trên Windows, Python 3.12.14. UI chính: React/TypeScript/Vite. Prompt: `shop-assistant-v3`.

| Hạng mục | Kết quả | Bằng chứng / lệnh |
|---|---|---|
| Unit/integration backend, LLM và công cụ | 90/90 PASS | `python scripts/test_all.py` |
| Database | 79/79 PASS | Cùng lệnh trên |
| Tổng test | **169/169 PASS** | `current/verification.md` |
| Evaluation offline bộ chính | 18/18 PASS | `current/fake_main/evaluation_fake.md` |
| Evaluation offline bộ bổ sung | 11/11 PASS | `current/fake_literal/evaluation_fake.md` |
| TypeScript | PASS | `tsc -b` |
| Frontend production build | PASS | Vite 5.4.21, 31 module |
| Form rubric | 29 case, cấu trúc hợp lệ | `rubric_review/review.html` |
| Gemini đã lưu | 29/29 kiểm tra tự động | `md_cases_2026-10-21/REPORT.md` |

Evaluation offline mới sử dụng FakeLLM; báo cáo Gemini được giữ nguyên từ lần chạy đã lưu. Điểm rubric 0/1/2 nhập trong form riêng; các ô hiện để trống. Checklist kiểm tra trình duyệt nằm tại `../docs/BROWSER_ACCEPTANCE.md` và chưa ghi nhận kết quả cho UI React trong lần đóng gói này.

## Đọc nhanh

1. `current/`: kết quả kiểm tra bản tổng hợp.
2. `md_cases_2026-10-21/`: bằng chứng Gemini trước/sau cải tiến.
3. `rubric_review/`: form chấm theo rubric.
4. `failure_analysis.md`: hai ví dụ quan sát và cải tiến.
