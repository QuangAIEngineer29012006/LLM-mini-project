# Kịch bản demo 10–12 phút

Khởi động FastAPI tại cổng 8000 và React/Vite tại cổng 5173 theo README. Chuẩn bị catalog seed, hai phiên trình duyệt và dữ liệu giả: Khách Demo, 0912345678, 12 Đường Mẫu, Quận 7. Chọn chế độ Gemini hoặc offline trước buổi trình bày và giới thiệu rõ chế độ đang dùng.

| Thời gian | Thao tác | Ý chính |
|---|---|---|
| 0:00–1:00 | Giới thiệu UI → API → RAG → DB | Kiến trúc và phần kế thừa project cũ |
| 1:00–2:30 | Xem catalog, chọn áo đen M, thêm giỏ, đặt đơn | Giá server, tồn kho, đơn nháp và mã đơn |
| 2:30–4:00 | Chat `Chốt 1 nón đen`, bổ sung giao nhận, sửa đơn | Thu thập nhiều lượt, validation và ownership |
| 4:00–5:15 | Hỏi chính sách/bảo hành có citation | Grounded answer, source và version |
| 5:15–6:15 | Mixed query: hỏi chính sách rồi thêm SKU rõ ràng | Knowledge có citation, action chỉ chạy sau validation |
| 6:15–7:15 | No-evidence, access-denied và prompt injection | Từ chối an toàn, không lộ tài liệu nội bộ |
| 7:15–8:15 | Mở staff/admin và xem index/re-index status | Role filter, activate và rollback |
| 8:15–9:30 | Trình bày metric, error trace và rubric review | Hit@3, Recall@5, MRR, citation và lỗi near-miss |
| 9:30–10:30 | Demo lại một cải tiến và kết luận | Bằng chứng kiểm thử, giới hạn và hướng phát triển |

Khi minh họa sửa đơn, lấy mã thực tế trên UI. Báo cáo Gemini đã lưu là bằng chứng lần kiểm thử có timestamp. Nếu chuyển provider trong demo, cập nhật `.env`, khởi động lại backend và thông báo chế độ mới.
