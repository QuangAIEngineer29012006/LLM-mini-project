# Evaluation và rubric 0/1/2

Bộ đánh giá gồm 18 case chính và 11 case bổ sung. Năm tiêu chí: intent, extraction/groundedness, format/validation, action routing và customer response.

| Điểm | Ý nghĩa |
|---|---|
| 0 | Sai hoặc không đáp ứng tiêu chí |
| 1 | Đáp ứng một phần, còn lỗi nhỏ hoặc cần làm rõ |
| 2 | Đáp ứng đúng và có căn cứ từ input/nghiệp vụ |

## Xem và chấm

Mở `sample_results/rubric_review/review.html` trong trình duyệt. Mỗi case có input, expected behavior, output và metadata. Nhập người chấm, điểm 0/1/2 và nhận xét cho từng tiêu chí; tải JSON để lưu. Nạp JSON để tiếp tục lần sau. Ô trống thể hiện chưa chấm.

Lưu bản hoàn tất thành `sample_results/rubric_review/review.completed.json`, rồi chạy:

```powershell
python scripts/review_evaluation.py validate sample_results/rubric_review/review.completed.json --complete
python scripts/review_evaluation.py render sample_results/rubric_review/review.completed.json --output sample_results/rubric_review/final_review.md
```

Điểm tự động 0/2 trong các báo cáo là kiểm tra điều kiện của từng case. Form rubric hỗ trợ nhận xét nội dung với thang 0/1/2 riêng. Các case F01–F04 chèn lỗi có chủ đích để kiểm tra workflow.

## Chạy lại

```powershell
python scripts/evaluate.py --provider fake --output sample_results/current/fake_main
python scripts/evaluate.py --provider fake --case-file tests/spec_literal_cases.json --output sample_results/current/fake_literal
```

Để chạy một case với Gemini đã cấu hình, dùng `--provider gemini --case-id H01 --output sample_results/current/gemini`. Báo cáo có timestamp, model, prompt và kết quả từng lượt. Bộ Gemini đã lưu nằm tại `sample_results/md_cases_2026-10-21/`.
