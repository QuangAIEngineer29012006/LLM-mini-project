---
doc_id: DOC-INT-STOCK-OPS
title: Hướng dẫn vận hành tồn kho, biến động giá snapshot và sản phẩm ngừng bán
version: 1.0
access_level: staff
author: TV1 - Database & Business Data
effective_date: 2026-10-01
data_notice: Dữ liệu mô phỏng cho mini-project, không phải dữ liệu thật.
---

## Kiểm tra tồn kho trên hệ thống
Nhân viên vận hành chỉ sử dụng kết quả truy vấn thời gian thực từ bảng tồn kho trên hệ thống cơ sở dữ liệu để trả lời khả năng đáp ứng đơn hàng. Đơn nháp ở trạng thái `pending_confirmation` chưa khóa hàng trong kho, do đó nhân viên cần kiểm tra lại trạng thái sẵn hàng ngay trước khi thực hiện thao tác xác nhận đơn.

## Xử lý price_changed khi giá đổi sau khi lên đơn
Hệ thống lưu giá chụp nhanh (`snapshot`) trên từng dòng mặt hàng tại thời điểm khách tạo đơn nháp để bảo vệ tính minh bạch:
- Nếu bảng giá danh mục thay đổi trước khi đơn được chuyển sang `confirmed`, hệ thống sẽ chặn thao tác xác nhận tự động và trả về cảnh báo `price_changed`.
- Nhân viên phải thông báo rõ mức giá mới cho khách hàng, chỉ khi khách đồng ý mới thực hiện thao tác làm mới giá đơn hàng (`refresh_prices`) rồi tiến hành xác nhận đơn theo đúng quy trình.

## Tư vấn khi hết biến thể
Khi màu sắc hoặc kích cỡ khách yêu cầu đang tạm hết trên hệ thống, nhân viên tra cứu các biến thể còn sẵn hàng thuộc cùng sản phẩm hoặc sản phẩm tương đương trong danh mục đang mở bán để gợi ý khách chọn thay thế. Nhân viên không nhận giữ chỗ miệng và không hẹn ngày nhập kho cụ thể khi chưa có lệnh nhập chính thức trên hệ thống.

## Quy trình ngừng bán sản phẩm
Khi cửa hàng quyết định dừng kinh doanh một mặt hàng hoặc biến thể (ví dụ thực tế như sản phẩm Áo khoác dù mang mã biến thể JKT-NVY-L đã ngừng bán):
- Quản trị dữ liệu cập nhật cờ `is_active = 0` tại bảng sản phẩm hoặc bảng biến thể trong cơ sở dữ liệu để khóa ngay mọi thao tác hiển thị danh mục và tạo đơn mới đối với mã JKT-NVY-L.
- Tiếp theo, cập nhật tài liệu sản phẩm tương ứng sang trạng thái `discontinued`, phát hành phiên bản manifest mới và chạy công cụ kiểm tra `sku_sync_service --check` đảm bảo đồng bộ hoàn toàn trước khi đồng bộ lại hệ thống tra cứu tri thức.

