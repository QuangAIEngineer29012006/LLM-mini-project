---
doc_id: DOC-ADM-RAG-OPS
title: Quy trình quản trị phát hành corpus, nâng cấp phiên bản và rollback
version: 1.0
access_level: admin
author: TV1 - Database & Business Data
effective_date: 2026-10-01
data_notice: Dữ liệu mô phỏng cho mini-project, không phải dữ liệu thật.
---

## Quy trình phát hành corpus release
Tài liệu này dành riêng cho quản trị viên hệ thống (`admin`) nhằm kiểm soát vòng đời dữ liệu tri thức và tính nhất quán với cơ sở dữ liệu bán hàng. Mọi thay đổi nội dung tài liệu hoặc metadata đều phải thông qua file cấu hình chuẩn `corpus_manifest_*.json` làm nguồn sự thật duy nhất; nghiêm cấm chỉnh sửa trực tiếp các bảng lưu trữ metadata trong SQLite bằng câu lệnh thủ công.

## Kiểm tra trước khi kích hoạt
Trước khi đồng bộ một bản phát hành mới vào cơ sở dữ liệu và bàn giao cho quy trình lập chỉ mục RAG, quản trị viên bắt buộc chạy lệnh kiểm tra `sku_sync_service --check` và xác nhận kết quả đạt tuyệt đối (`ok = True`, mã thoát bằng `0`):
- Không có file thiếu, file rỗng, sai bảng mã UTF-8, chứa BOM hoặc lệch mã băm `content_sha256`.
- Không có mã sản phẩm, mã biến thể hay mức giá tham khảo nào lệch với cơ sở dữ liệu danh mục hiện hành, đồng thời không xuất hiện con số tồn kho ghi cứng trong văn bản.

## Nâng cấp 1.0 sang 1.1
Khi phát hành bản cập nhật chính sách hoặc sản phẩm (ví dụ nâng cấp chính sách đổi trả `DOC-POL-RETURN` từ phiên bản `1.0` lên `1.1` trong bản phát hành `1.1.0`):
- Tạo file văn bản phiên bản mới độc lập để giữ nguyên tính bất biến lịch sử của phiên bản `1.0`, điền đầy đủ ghi chú thay đổi nghiệp vụ vào trường `change_note` trong manifest `1.1`.
- Chạy đồng bộ manifest `1.1` để cơ sở dữ liệu tự động tắt cờ hiệu lực của phiên bản `1.0` và chỉ giữ duy nhất phiên bản `1.1` ở trạng thái hoạt động, sau đó kích hoạt quy trình tái lập chỉ mục vector và xóa bộ nhớ đệm liên quan.

## Rollback phiên bản
Nếu phát hiện sai sót nghiệp vụ hoặc lỗi chỉ mục sau khi nâng cấp lên bản `1.1.0`, quản trị viên thực hiện quay lui (`rollback`) bằng cách chạy lại lệnh đồng bộ với file `corpus_manifest_v1.0.json` đã kiểm định trước đó, kết hợp khôi phục gói chỉ mục tương ứng với bản `1.0.0` để đưa hệ thống về trạng thái ổn định tức thì mà không làm mất lịch sử phiên bản.

## Yêu cầu log an toàn
Mọi sự kiện đồng bộ thành công (`sync_applied`) hoặc bị từ chối (`sync_rejected`) trong bảng `corpus_sync_events` phải áp dụng cơ chế chỉ-thêm (`append-only`) và lọc sạch dữ liệu nhạy cảm: chỉ ghi mã phát hành, số lượng tài liệu, danh sách mã `doc_id` hoặc mã lỗi kỹ thuật; tuyệt đối không ghi khóa bí mật (`secret`), thông tin định danh cá nhân (PII) hay toàn văn nội dung tài liệu nội bộ vào nhật ký.

