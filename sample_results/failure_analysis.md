> Báo cáo lịch sử của vòng phát triển trước. Xem [trạng thái hiện hành](STATUS.md) và [kết quả 21/10](md_cases_2026-10-21/REPORT.md) để đọc model, prompt và kết quả mới hơn. Nội dung cũ bên dưới được giữ để truy vết.

# Failure analysis và revision note

Prompt hiện tại: `order-extraction-v1`, zero-shot. Backend/fake version đầu được sửa trong lúc phát triển; không có thí nghiệm A/B với Gemini vì chưa có key. Các ví dụ là dữ liệu demo.

## 1. Nhầm màu từ một phần của từ

Input: `Đơn lúc nãy đổi thành 2 cái`.

Bản FakeLLM đầu dò màu theo substring không dấu. `do` của màu `đỏ` khớp đầu từ `đơn`, dẫn đến color=`Đơ`, rồi evidence validator chặn với `ungrounded_output`. Hệ thống không sửa đơn, nhưng người dùng nhận lỗi thay vì được hỏi mã đơn.

Thay đổi: dò màu với ranh giới từ. Kết quả sau sửa: nhận `update_order`, không tự thêm màu; khi chưa có đơn nháp duy nhất thì hỏi `order_reference`. Được kiểm tra bởi `test_update_target_ownership_and_ambiguity`, case S02 và kiểm tra đổi màu không có trong catalog. Đây là sửa rule fake, không phải cải thiện điểm model Gemini.

## 2. Khác catalog giữa frontend mock và database

Input trong đề/giao diện mẫu: `Chốt 2 áo xanh size M`.

Frontend mock có SKU áo xanh, nhưng seed database chỉ có áo thun đen/trắng. Nếu ghép trực tiếp catalog mock hoặc lấy biến thể có điểm gần nhất, hệ thống có thể ghi nhầm SKU. Trường hợp này không nên được tính là happy path trên catalog hiện tại.

Thay đổi: adapter API đọc catalog SQLite; resolver lọc chính xác màu/size, chỉ nhận khi còn duy nhất một SKU. Không khớp màu xanh thì hỏi làm rõ, không tạo đơn. Test `test_missing_variant_follow_up_and_unknown_color_never_guessed` kiểm tra không sinh thêm đơn; demo dùng `áo thun đen size M`.

## 3. Structured JSON hợp lệ vẫn có thể bịa giao nhận

Failure injection: output có đúng JSON schema nhưng customer.name là `Invented Person` trong khi message chỉ có `Chốt 1 TSH-BLK-M`.

Nếu chỉ kiểm tra schema và tồn kho, hệ thống có thể lưu tên bịa ở context rồi dùng cho đơn sau. Thay đổi: grounding validator đối chiếu field với tin nhắn hiện tại trước khi merge; không cho model sao chép slot cũ từ prompt. Kết quả là `failed_validation/ungrounded_output`, order count bằng 0. Test cùng nhóm còn chặn SKU bịa, quantity bool và field price do model thêm.

Giới hạn: kiểm tra substring không phát hiện hết phủ định, quan hệ sản phẩm-số lượng hoặc prompt injection diễn đạt mới. Cần chạy bộ case với Gemini thật, đọc output và bổ sung test độc lập trước khi kết luận chất lượng extraction.
