---
doc_id: DOC-ADM-HR-POLICY
title: Quy chế phân ca trực vận hành và định mức phụ cấp nội bộ
version: 1.0
access_level: admin
author: TV1 - Database & Business Data
effective_date: 2026-10-01
data_notice: Dữ liệu mô phỏng cho mini-project, không phải dữ liệu thật.
---

## Phạm vi áp dụng mô phỏng
Tài liệu quản trị nội bộ này quy định khung phân ca trực và chế độ phụ cấp vận hành dành riêng cho cấp quản trị (`admin`). Toàn bộ con số và quy định dưới đây là dữ liệu giả lập phục vụ kiểm thử phân quyền truy cập tài liệu nhạy cảm, tuyệt đối không phản ánh thông tin nhân sự của bất kỳ cá nhân hay tổ chức thực tế nào.

## Ca trực vận hành hệ thống
Hoạt động điều phối đơn hàng và giám sát hệ thống hỗ trợ trực tuyến được chia thành ba khung ca tiêu chuẩn mỗi ngày:
- Ca sáng: từ 08:00 đến 14:00, phụ trách đối soát đơn chờ xác nhận phát sinh từ tối hôm trước và bàn giao bưu cục đợt đầu ngày.
- Ca chiều: từ 14:00 đến 21:00, phụ trách cao điểm tư vấn trực tuyến, xử lý yêu cầu `handoff` và khiếu nại đơn hàng.
- Ca trực kỹ thuật tối muộn: từ 21:00 đến 23:30, dành cho quản trị viên thực hiện bảo trì cơ sở dữ liệu, kiểm tra đồng bộ danh mục và cập nhật chỉ mục ngoài giờ cao điểm.

## Phụ cấp ca trực mô phỏng
Định mức phụ cấp trách nhiệm mô phỏng áp dụng cho nhân sự được phân công trực chuyên trách ngoài khung hành chính tiêu chuẩn:
- Phụ cấp ca trực kỹ thuật tối muộn và bảo trì nâng cấp phiên bản dữ liệu: 150.000 VND/ca.
- Phụ cấp trực điều phối ngày nghỉ lễ theo lịch phân công được duyệt trước: 250.000 VND/ca.

## Bảo mật thông tin nhân sự
Mọi dữ liệu liên quan đến định mức thu nhập, phụ cấp ca trực, lịch phân công quản trị viên và biên bản đánh giá nội bộ đều được phân loại ở mức quyền truy cập cao nhất (`admin`). Hệ thống tra cứu tri thức bắt buộc chặn truy cập đối với cả vai trò khách hàng (`customer`) lẫn nhân viên hỗ trợ (`staff`) ngay từ bước lọc dữ liệu trước khi tìm kiếm.

