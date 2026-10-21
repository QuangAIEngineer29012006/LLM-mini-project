# Kịch bản demo 7 phút

Khởi động FastAPI tại cổng 8000 và React/Vite tại cổng 5173 theo README. Chuẩn bị catalog seed, hai phiên trình duyệt và dữ liệu giả: Khách Demo, 0912345678, 12 Đường Mẫu, Quận 7. Chọn chế độ Gemini hoặc offline trước buổi trình bày và giới thiệu rõ chế độ đang dùng.

| Thời gian | Thao tác | Ý chính |
|---|---|---|
| 0:00–0:30 | Giới thiệu UI → API → AI/rules → DB | Website và chat dùng chung nghiệp vụ |
| 0:30–1:30 | Chọn áo đen M, thêm giỏ, điền giao nhận, đặt đơn | Giá server, đơn nháp và mã đơn |
| 1:30–2:40 | Chat `Chốt 1 nón đen`, bổ sung giao nhận | Thu thập thông tin nhiều lượt |
| 2:40–3:20 | Dùng mã đơn thật để sửa số lượng | Kiểm tra tồn và cập nhật tổng tiền |
| 3:20–4:00 | Đặt áo trắng M hết hàng hoặc 3 giày trắng 41 | Validation và phản hồi hướng dẫn |
| 4:00–4:45 | Dùng phiên ẩn danh và kết quả test quyền | Mỗi phiên chỉ thao tác đơn của mình |
| 4:45–5:30 | Gửi yêu cầu mơ hồ và prompt injection trong bộ case | Hỏi bổ sung hoặc handoff |
| 5:30–6:10 | Trình bày kết quả test lỗi JSON/API | Workflow xử lý lỗi có kiểm soát |
| 6:10–7:00 | Mở evaluation và hai ví dụ cải tiến | Kết quả, rubric và đóng góp kỹ thuật |

Khi minh họa sửa đơn, lấy mã thực tế trên UI. Báo cáo Gemini đã lưu là bằng chứng lần kiểm thử có timestamp. Nếu chuyển provider trong demo, cập nhật `.env`, khởi động lại backend và thông báo chế độ mới.
