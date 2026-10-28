---
doc_id: DOC-INT-SOP-SUPPORT
title: Quy trình nội bộ tiếp nhận handoff, xác minh thiếu hàng và duyệt đơn
version: 1.0
access_level: staff
author: TV1 - Database & Business Data
effective_date: 2026-10-01
data_notice: Dữ liệu mô phỏng cho mini-project, không phải dữ liệu thật.
---

## Tiếp nhận handoff từ trợ lý
Khi phiên trò chuyện của khách hàng chuyển sang trạng thái cần nhân viên hỗ trợ (`handoff`), nhân viên chăm sóc khách hàng (CSKH) đọc lại lịch sử hội thoại gần nhất, kiểm tra ngữ cảnh thu thập dở dang và mã đơn liên kết (`last_order_id`) trước khi phản hồi. Nhân viên tuyệt đối không yêu cầu khách lặp lại các thông tin giao nhận đã hiển thị hợp lệ trên hệ thống.

## Xác minh báo thiếu hàng
Khi khách phản ánh kiện hàng giao thiếu số lượng hoặc móp rách bao bì trong thời hạn quy định tại DOC-POL-RETURN, nhân viên thực hiện đủ ba bước đối chiếu nội bộ:
- Kiểm tra chi tiết dòng mặt hàng snapshot (`order_items`) và nhật ký chuyển trạng thái của đơn trên cơ sở dữ liệu.
- Kiểm tra tính liền mạch của video mở hộp từ lúc kiện hàng còn nguyên niêm phong vận chuyển đến khi kiểm đếm từng món bên trong.
- Đối chiếu biên bản cân nặng lúc xuất kho với đơn vị vận chuyển trước khi lập phiếu gửi bù sản phẩm thiếu.

## Xác nhận hoặc hủy đơn pending_confirmation theo quy trình
- Trước khi chuyển đơn từ `pending_confirmation` sang `confirmed`, nhân viên rà soát lại địa chỉ nhận hàng, số điện thoại chuẩn hóa và thông báo phí vận chuyển thực tế cho khách.
- Thao tác chuyển sang `confirmed` sẽ tự động kiểm tra tồn kho và trừ số lượng tương ứng trong cùng một giao dịch cơ sở dữ liệu; nếu hai đơn cùng tranh số lượng cuối cùng khiến hệ thống báo thiếu hàng, nhân viên liên hệ khách để tư vấn đổi biến thể hoặc hủy đơn nháp.
- Nếu khách yêu cầu hủy đơn đã ở trạng thái `confirmed` khi kiện hàng chưa bàn giao bưu cục, nhân viên thực hiện chuyển trạng thái sang `cancelled` để hệ thống hoàn trả tồn kho tự động và lưu vết kiểm toán.

## SLA phản hồi nội bộ 4 giờ làm việc
Mọi phiếu yêu cầu chuyển tiếp (`handoff`) và khiếu nại thiếu hàng, bảo hành hợp lệ phải được nhân viên CSKH ca trực tiếp nhận phản hồi lần đầu trong vòng tối đa 4 giờ làm việc kể từ thời điểm ghi nhận trên hệ thống (khung giờ làm việc nội bộ tính từ 08:00 đến 21:00 hằng ngày). Các trường hợp tồn đọng quá 4 giờ làm việc phải được báo cáo trưởng ca điều phối lại nhân sự.

## Thông tin không được nói với khách
Nhân viên CSKH không được tiết lộ các chỉ tiêu SLA nội bộ, ghi chú phân loại rủi ro nội bộ, cấu trúc bảng cơ sở dữ liệu, nhật ký kiểm toán hệ thống (`audit_logs`) hoặc quy định hạn mức duyệt chi phí nội bộ tại DOC-INT-PROMO-RULES ra kênh trò chuyện công khai với khách mua hàng.

