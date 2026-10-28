---
doc_id: DOC-FAQ-PUBLIC
title: Câu hỏi thường gặp dành cho khách mua hàng
version: 1.0
access_level: public
author: TV1 - Database & Business Data
effective_date: 2026-10-01
data_notice: Dữ liệu mô phỏng cho mini-project, không phải dữ liệu thật.
---

## Làm sao biết biến thể tôi chọn còn hàng hay đã hết?
Tài liệu mô tả sản phẩm chỉ liệt kê danh mục các màu sắc và kích cỡ mà cửa hàng sản xuất, không ghi số lượng hàng tồn cố định. Khi bạn xem trang sản phẩm, thêm mặt hàng vào giỏ hoặc nhắn mã biến thể cụ thể cho trợ lý hội thoại, hệ thống cửa hàng sẽ truy vấn trực tiếp dữ liệu kho tại thời điểm đó để báo chính xác biến thể đang sẵn hàng hay tạm hết.

## Vì sao giá tham khảo trong tài liệu có thể khác giá lúc đặt đơn?
Mức giá ghi trong hồ sơ sản phẩm là giá tham khảo niêm yết của từng phiên bản tài liệu. Mọi đơn nháp và giỏ hàng đều được máy chủ tính tiền tự động dựa trên bảng giá hiệu lực hiện hành trong cơ sở dữ liệu cửa hàng tại lúc tạo hoặc gửi đơn; nếu bảng giá thay đổi trước khi đơn được xác nhận, hệ thống sẽ thông báo rõ để bạn kiểm tra lại trước khi chốt.

## Tôi muốn sửa số lượng hoặc thông tin người nhận trên đơn nháp thì làm thế nào?
Khi đơn hàng vẫn đang ở trạng thái giỏ hàng (`cart`) hoặc chờ xác nhận (`pending_confirmation`), bạn có thể đổi số lượng, đổi biến thể màu/cỡ thuộc cùng sản phẩm tại mục Đơn hàng trên website hoặc nhắn trực tiếp yêu cầu cập nhật trong phiên trò chuyện của mình. Nếu đơn đã được nhân viên chuyển sang trạng thái đã xác nhận (`confirmed`), bạn vui lòng yêu cầu gặp nhân viên hỗ trợ để được kiểm tra.

## Tôi nhận kiện hàng bị móp hộp hoặc thiếu sản phẩm thì cần làm gì?
Bạn hãy giữ nguyên bao bì, phiếu giao nhận và chuẩn bị video quay liền mạch lúc mở hộp kèm hình ảnh thực tế, sau đó gửi thông báo ngay cho cửa hàng kèm mã đơn hàng của bạn. Thời hạn tiếp nhận báo thiếu hàng, điều kiện đổi sản phẩm lỗi hoặc đổi kích cỡ theo từng mặt hàng được áp dụng nghiêm ngặt theo phiên bản hiện hành của tài liệu chính sách DOC-POL-RETURN.

## Trợ lý trò chuyện có tự tạo mã giảm giá hoặc duyệt hoàn tiền được không?
Không. Trợ lý AI không có quyền tạo mã ưu đãi, không tự ý giảm giá đơn hàng, không thay đổi quy định bảo hành hay duyệt hoàn tiền. Các yêu cầu vượt ngoài quy tắc tự động hoặc nằm ngoài nội dung chính sách công khai đều phải do nhân viên cửa hàng trực tiếp xem xét.

## Khi nào cuộc trò chuyện được chuyển sang nhân viên hỗ trợ?
Nếu bạn gửi yêu cầu đặc biệt cần con người quyết định (như khiếu nại đơn hàng đã giao, xử lý đơn đã xác nhận, hỏi chứng từ riêng hoặc tình huống phức tạp chưa đủ thông tin xác thực), trợ lý sẽ chuyển phiên sang trạng thái cần nhân viên hỗ trợ (`handoff`) để bộ phận chăm sóc khách hàng tiếp nhận xử lý.

