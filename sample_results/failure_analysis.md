# Phân tích và cải tiến đã kiểm chứng

Prompt hiện hành: `shop-assistant-v3`. Hai ví dụ dưới đây ghi lại vòng lặp quan sát → điều chỉnh → kiểm thử theo yêu cầu mini-project.

## 1. Chuẩn hóa màu và size trong hội thoại nhiều lượt

**Quan sát M05:** output trước cải tiến có màu `màu đen`, trong khi catalog lưu `Đen`, dẫn đến hỏi lại biến thể.

**Điều chỉnh:** chuẩn hóa tiền tố màu/size trước khi map catalog; prompt v3 hướng dẫn tách nhãn khỏi giá trị. Dùng chung quy tắc cho tìm hàng và đặt hàng.

**Kết quả:** case M05 tạo đúng đơn nháp `TSH-BLK-M`, số lượng 1 sau khi đủ giao nhận; regression test vẫn kiểm tra trường hợp màu không tồn tại.

## 2. Phân biệt sửa đơn với yêu cầu hỗ trợ

**Quan sát L06:** câu hỗ trợ gấp được phân loại `update_order` ở bản trước, trong khi hành vi cần thiết là chuyển hỗ trợ.

**Điều chỉnh:** prompt v3 xác định sửa đơn cần nội dung thay đổi đơn; yêu cầu hỗ trợ không có thông tin thay đổi dùng `unknown_or_handoff`.

**Kết quả:** L06 trả đúng intent và route handoff. Tổng kiểm tra tự động trước/sau trên bộ 29 case: **27/29 → 29/29**.

Bằng chứng input/output và điểm từng tiêu chí giữ tại `md_cases_2026-10-21/baseline/`, `literal_baseline/`, `final/` và `literal_final/`. Đây là so sánh trên cùng bộ case dùng trong quá trình phát triển.
