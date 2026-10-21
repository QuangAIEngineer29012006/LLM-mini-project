# Trạng thái bằng chứng hiện hành

Trang này là điểm vào đọc kết quả. Các báo cáo cũ giữ nguyên để truy vết; số liệu bên dưới lấy từ artifact đã commit tại `5dc9e67`, không phải tuyên bố vừa chạy lại Gemini.

| Hạng mục | Bằng chứng | Cách diễn giải |
|---|---|---|
| Prompt hiện tại | `src/prompts.py`: shop-assistant-v3 | Zero-shot; không phải order-extraction-v1 trong ghi chú lịch sử |
| Model trong lần chạy cuối đã lưu | `md_cases_2026-10-21/final/evaluation_gemini.json` và `literal_final/evaluation_gemini.json` | gemini-3.5-flash-lite; metadata của lần chạy, không xác nhận availability hiện tại của provider |
| Evaluation sau cải tiến | Hai file trên, 18 + 11 case | 29/29 đạt proxy tự động; 27 generation request được ghi trong vòng cuối |
| Cải tiến trước/sau | `md_cases_2026-10-21/REPORT.md` | Baseline 27/29 → final 29/29 trên cùng bộ case đã dùng để sửa; không phải held-out accuracy |
| Lỗi mô phỏng | F01–F04; S01 policy trước model | Không tính là model thật vượt lỗi network hoặc tự chống injection |
| Full test cũ | REPORT.md ghi 150/150 | 71 backend/frontend/LLM/quota + 79 database; lịch sử, không phải kết quả test bản TV5 |
| UI integration cũ | `frontend_smoke.json` | 10 bước AppTest trên 6 trang, HTTP + SQLite; không phải kiểm tra layout trình duyệt |
| Rubric nhóm | `rubric_review/review.html`, `review.json` | 29 case chuẩn bị chấm; các điểm người chấm còn trống cho đến khi nhóm xác nhận |
| Nhận xét hỗ trợ | `rubric_review/assistant_review.md` | Đánh giá AI trên output đã lưu, không giả danh chấm bởi con người |
| UI đang thiết kế lại | `browser_acceptance.json` | 15 case NOT RUN ban đầu; nghiệm thu sau tích hợp UI mới |
| Demo | `../docs/DEMO_RUNBOOK.md` | Kịch bản 7 phút và phương án xử lý lỗi |
| Kiểm chứng phần TV5 | `tv5_verification/REPORT.md` | 169 test PASS; fake 18/18 + 11/11 sau sửa; không gọi Gemini mới |

`verification.md`, `failure_analysis.md`, `gemini_live_test.md`, catalog smoke/probe cũ là lịch sử của từng đợt/model. Các câu “chưa có key” trong lịch sử không mô tả trạng thái sau lần kiểm thử 21/10. Không gộp số request hay điểm của các model khác nhau.

Đề bài không được commit trong repository nên không dùng liên kết tới file nằm ngoài repo. Nguồn yêu cầu là tài liệu mini-project do nhóm/giảng viên cung cấp; người nộp kiểm tra lại bản đề chính thức. Bản TV5 chỉ thêm công cụ đánh giá, QA và tài liệu; không thiết kế lại UI hay thay logic bán hàng.
