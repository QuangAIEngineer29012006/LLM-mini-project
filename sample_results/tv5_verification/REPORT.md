# Kiểm chứng phần TV5 ngày 21 tháng 10 năm 2026

Nền code: main tại `5dc9e67`. Phần bổ sung nằm trên nhánh `feat/evaluation-demo`, không sửa `app.py`, `frontend/`, `views/` hoặc CSS. Không gọi Gemini mới trong đợt này.

| Kiểm tra thực hiện | Kết quả |
|---|---|
| Backend/frontend logic/LLM/quota và test công cụ mới | 90/90 PASS |
| Database | 79/79 PASS |
| Tổng unit/integration tests | 169/169 PASS |
| Fake evaluation bộ chính | 18/18 PASS |
| Fake evaluation bộ bổ sung sau sửa | 11/11 PASS |
| Bộ bổ sung với FakeLLM cũ trước sửa | 9/11, L03 và U02 không đạt |
| Form rubric | 29 case, 145 ô điểm người chấm còn trống; không giả chữ ký hoặc điểm thủ công |
| Browser acceptance | 15 NOT RUN; chờ UI mới tích hợp |

Môi trường kiểm chứng: Windows, Python 3.12.14. Các test HTTP dùng FastAPI TestClient và SQLite tạm. Runtime này nạp các dependency Python từ môi trường dự án đã có; đây không phải bằng chứng cài mới từ requirements. Có cảnh báo deprecation Starlette/httpx; không làm test thất bại. Không chạy lại kiểm tra cài đặt/demo vì người dùng xác nhận đã chạy được.

## Các lỗi tìm thấy và đã sửa

1. **Quota SQLite trên Windows:** `with sqlite3.connect(...)` chỉ quản lý transaction, không đảm bảo đóng connection. Bốn test quota lỗi `WinError 32` khi dọn DB tạm. Dùng `contextlib.closing` cùng transaction; 90 test root chạy lại đạt, gồm các case quota đồng thời và vượt hạn mức. Không đổi giới hạn/ngày reset.
2. **Evaluation tiếng Việt trên Windows:** `Path.read_text/write_text` không chỉ định encoding dùng cp1252 và gây UnicodeDecodeError. Đọc UTF-8/BOM, ghi UTF-8 cho evaluation và report AppTest. Chạy evaluation tiếng Việt sau sửa đạt các kết quả trên.
3. **FakeLLM L03:** “Cho chị 3 hộp loại 500g…” trước đây thành unknown/handoff. Thêm dạng yêu cầu mua có đại từ + số lượng; vẫn để backend hỏi sản phẩm khi không map catalog, không tạo SKU giả.
4. **FakeLLM U02:** “số lượng 2” chưa được trích, nên đổi size nhưng giữ số lượng 1. Thêm nhãn số lượng, không nhầm mã DH hay size thành quantity. Ba test regression mới kiểm tra cách diễn đạt khác và bảo đảm câu “cho chị xem” vẫn là browse.

Baseline hai lỗi fake được tái lập offline bằng class FakeLLMClient từ commit nền, chạy cùng case/DB/parser/service và quota đã đóng kết nối. Giữ tại `baseline_fake_literal/`; kết quả sau sửa tại `fake_literal/`. Đây là cải tiến rule của fake, không phải cải tiến chất lượng Gemini. Không thay expected behavior để làm test đạt.

## Lệnh tái kiểm tra trong môi trường dự án

```powershell
python scripts/test_all.py
python scripts/evaluate.py --provider fake --output sample_results/tv5_verification/fake_main
python scripts/evaluate.py --provider fake --case-file tests/spec_literal_cases.json --output sample_results/tv5_verification/fake_literal
python scripts/review_evaluation.py validate sample_results/rubric_review/review.json
python scripts/browser_acceptance.py report sample_results/browser_acceptance.json
```

Các lệnh evaluate sẽ tạo timestamp mới và ghi đè báo cáo trong thư mục output đã chọn; đổi output nếu muốn giữ lịch sử. Bản chấm của người dùng nên lưu ở file completed riêng. Chỉ dùng `--complete` khi chấm/nghiệm thu thực sự xong.
