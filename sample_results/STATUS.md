# Kết quả kiểm tra bản tổng hợp

Đặt hàng qua bot (22/10): luồng nhận balo xám 15inch → hỏi số lượng/giao nhận → tạo đơn đã kiểm tra bằng Gemini thật trên SQLite riêng. Báo cáo lịch sử ghi 180 test Python và 12 React đạt. Lần chạy hiện tại đạt 223 test Python và 15 React.

Cập nhật 22/10/2026: đã rà soát React và chạy lại trên macOS; 169 test Python + 9 regression React đạt, npm ci/TypeScript/build đạt, live Gemini qua UI trả đúng giá/tồn. Xem [báo cáo frontend](frontend_review_2026-10-22/REPORT.md) cho phạm vi, ảnh và các giới hạn kiểm tra. Phần bên dưới là kết quả bàn giao ngày 21/10.

Kiểm tra ngày 21/10/2026 trên Windows, Python 3.12.14. UI chính: React/TypeScript/Vite. Prompt: `shop-assistant-v3`.

| Hạng mục | Kết quả | Bằng chứng / lệnh |
|---|---|---|
| Unit/integration backend, LLM và công cụ | 111/111 PASS | `python scripts/test_all.py` |
| Database | 112/112 PASS | Cùng lệnh trên |
| Tổng test | **223/223 PASS** | `current/verification.md` |
| Evaluation offline bộ chính | 18/18 PASS | `current/fake_main/evaluation_fake.md` |
| Evaluation offline bộ bổ sung | 11/11 PASS | `current/fake_literal/evaluation_fake.md` |
| Evaluation RAG test fake | Contract 13/17; strict relevance 11/17; Hit@3 0,700; Recall@5 0,683; MRR 0,650 | `artifacts/evaluation_results_test_fake_current-test-fake.json` |
| TypeScript | PASS | `tsc -b` |
| Frontend production build | PASS | Vite 5.4.21, 31 module |
| Form rubric | 29 case, cấu trúc hợp lệ | `rubric_review/review.html` |
| Gemini đã lưu | 29/29 kiểm tra tự động | `md_cases_2026-10-21/REPORT.md` |

Evaluation offline mới sử dụng FakeLLM; báo cáo Gemini được giữ nguyên từ lần chạy đã lưu. RAG fake được chạy lại sau khi rebuild index để manifest và `chunks.jsonl` khớp SHA-256. Điểm rubric 0/1/2 nhập trong form riêng; các ô hiện để trống. Checklist kiểm tra trình duyệt nằm tại `../docs/BROWSER_ACCEPTANCE.md` và chưa ghi nhận kết quả cho UI React trong lần đóng gói này.

## Đọc nhanh

1. `current/`: kết quả kiểm tra bản tổng hợp.
2. `md_cases_2026-10-21/`: bằng chứng Gemini trước/sau cải tiến.
3. `rubric_review/`: form chấm theo rubric.
4. `failure_analysis.md`: hai ví dụ quan sát và cải tiến.
