# Evaluation Gemini — 21/10/2026

Model trong metadata: `gemini-3.5-flash-lite`. Prompt cuối: `shop-assistant-v3`. Tổng 29 case gồm 18 case chính và 11 case bổ sung.

| Vòng | Bộ chính | Bộ bổ sung | Tổng |
|---|---:|---:|---:|
| Trước cải tiến | 17/18 | 10/11 | 27/29 |
| Sau cải tiến | 18/18 | 11/11 | 29/29 |

Điểm là kết quả kiểm tra tự động cho intent, extraction, validation, routing và response trên bộ case phát triển. Hai thay đổi chính: chuẩn hóa màu/size ở M05 và phân loại yêu cầu hỗ trợ ở L06. Xem [phân tích cải tiến](../failure_analysis.md).

## Bằng chứng

- `baseline/`, `literal_baseline/`: input/output và kết quả trước sửa.
- `final/`, `literal_final/`: input/output và kết quả sau sửa.
- `summary.json`: tổng hợp metadata và số lượt gọi.

Vòng cuối ghi 27 lượt generation thật. F01–F04 dùng lỗi chèn để kiểm tra JSON/API; S01 đi qua policy trước provider. Bản tổng hợp sử dụng các báo cáo đã lưu này; lần kiểm tra tích hợp mới được ghi riêng tại `../current/`.

## Phạm vi case

Happy path; thiếu thông tin/biến thể; tra giá và tồn kho; sửa đơn; hết hàng/vượt tồn; tham chiếu mơ hồ; prompt injection; JSON/API lỗi. Database test tạo từ cùng schema/seed; kiểm tra trạng thái `pending_confirmation`, số đơn, item và tồn kho trước/sau. Điểm rubric 0/1/2 được nhập qua form tại `../rubric_review/review.html`.
