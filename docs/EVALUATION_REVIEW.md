# Chấm rubric và sử dụng bằng chứng

Đánh giá có ba lớp riêng biệt: proxy tự động trong báo cáo gốc, nhận xét hỗ trợ của AI trong `sample_results/rubric_review/assistant_review.md`, và điểm do người trong nhóm xác nhận. Không đổi tên proxy thành điểm thủ công; không dùng nhận xét AI làm chữ ký người chấm.

## Bắt đầu chấm

Mở `sample_results/rubric_review/review.html` trực tiếp bằng Chrome/Edge. Trang chạy offline, không có CDN và không gửi dữ liệu tới API. Có 29 case với input, expected behavior, output từng lượt, extraction đã ẩn danh, metadata model và điểm proxy gốc.

1. Nhập tên người chấm. Đọc input và mọi lượt output, không chỉ reply cuối.
2. Chấm 0/1/2 cho năm tiêu chí theo mô tả ngay dưới mỗi ô. Viết nhận xét ít nhất 10 ký tự cho mỗi điểm.
3. Nếu evidence đã che dữ liệu giao nhận không đủ kết luận, để trống tiêu chí đó. Xem output mock/đã ẩn danh an toàn bổ sung trong buổi demo; không khôi phục PII thật vào log.
4. Tải JSON trước khi đóng trang; form không tự lưu. Có thể nạp lại bản JSON để tiếp tục. Dùng tính năng lưu khi mới chấm một phần.
5. Chép file đã tải về vào `sample_results/rubric_review/review.completed.json`, giữ nguyên các trường evidence/source.

Chạy từ thư mục gốc repository, không cần cài thêm thư viện:

```powershell
python scripts/review_evaluation.py validate sample_results/rubric_review/review.completed.json --complete
python scripts/review_evaluation.py render sample_results/rubric_review/review.completed.json --output sample_results/rubric_review/final_review.md
```

`--complete` từ chối nếu còn ô trống, thiếu tên/ngày người chấm, điểm bool/ngoài 0–2, thiếu nhận xét, mất case hoặc evidence không khớp nguồn. Bản chấm một phần vẫn render được, nhưng không được dùng làm nghiệm thu cuối. Dấu — là chưa chấm, không phải 0. Tổng /10 chỉ có khi đủ năm tiêu chí; trung bình không phải accuracy của Gemini.

## Rubric

| Tiêu chí | 0 | 1 | 2 |
|---|---|---|---|
| Intent | Sai | Một phần hoặc mơ hồ | Đúng expected behavior |
| Extraction và groundedness | Bịa hoặc sai thông tin chính | Có lỗi nhỏ | Bám input, field có căn cứ |
| Format và validation | Không parse hoặc bypass rule | Parse nhưng vi phạm rule | Đúng schema và business rules |
| Action routing | Action sai hoặc không an toàn | Cảnh báo nhưng route chưa rõ | Draft, hỏi bổ sung hoặc handoff đúng |
| Customer response | Sai/không hữu ích | Đúng nhưng chưa rõ | Ngắn, chính xác, có bước tiếp theo |

Chấm response theo nội dung khách thực sự thấy, gồm thẻ đơn nếu UI hiển thị; nhận xét AI riêng về text reply không đủ để kết luận toàn bộ UI thiếu thông tin. F01–F04 là lỗi được chèn; S01 bị policy chặn trước model. Những case này chứng minh cách workflow xử lý, không chứng minh model tự nhận diện lỗi hoặc chống injection.

## Tái tạo bộ chấm

```powershell
python scripts/review_evaluation.py prepare --report sample_results/md_cases_2026-10-21/final/evaluation_gemini.json --report sample_results/md_cases_2026-10-21/literal_final/evaluation_gemini.json --cases tests/test_cases.json --cases tests/spec_literal_cases.json --output sample_results/rubric_review/regenerated
```

Không ghi đè bài chấm đang thực hiện. Khi thay prompt/model/test set, tạo báo cáo và bộ chấm mới. Các nguồn được fingerprint theo nội dung JSON chuẩn hóa để không lỗi vì LF/CRLF.

## Bằng chứng hiện có

Hai báo cáo cuối ngày 21/10 ghi 29/29 case đạt proxy, 27 generation request thật trong vòng chạy cuối. Đây là kết quả lưu trong repository, không phải lần chạy mới của bản TV5. Bộ case đã dùng để cải tiến prompt nên không phải held-out benchmark. Đọc thêm `sample_results/STATUS.md` trước khi trình bày kết quả.
