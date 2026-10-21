# Nhận xét hỗ trợ của AI trên 29 case

Người hỗ trợ: Codex (AI). Đây không phải xác nhận chấm tay của thành viên nhóm. Dựa trên hai báo cáo Gemini đã lưu tại commit 5dc9e67; không gọi model mới.

Điểm là đề xuất. Dấu — nghĩa là thiếu bằng chứng hoặc không có output model để chấm tiêu chí đó; không quy thành 0. Không tính accuracy/tổng điểm khi còn tiêu chí chưa xác nhận.

Response được góp ý theo text reply; thẻ order trong UI có thể bổ sung đầy đủ, người chấm cần điều chỉnh sau khi xem UI mới.

| Case | Intent | Extract | Validate | Route | Reply | Nhận xét |
|---|---:|---:|---:|---:|---:|---|
| H01 | 2 | — | 2 | 2 | 1 | Item áo đen M số lượng 2 đúng expected. Text reply chỉ xác nhận chung; cần đọc thẻ đơn trên UI mới để chốt điểm response. |
| H02 | 2 | — | 2 | 2 | 1 | Nón đen số lượng 1 đúng expected; text reply chưa nhắc lại item/số lượng. |
| H03 | 2 | — | 2 | 2 | 1 | Hai item đúng SKU/số lượng. Cần kiểm tra thẻ đơn hiển thị cả hai item và tổng tiền. |
| M01 | 2 | 2 | 2 | 2 | 2 | Hỏi đúng ba trường giao nhận thiếu, chưa tạo đơn. |
| M02 | 2 | 2 | 2 | 2 | 2 | Không tự chọn một trong bốn biến thể; đưa lựa chọn và hỏi màu/size. |
| M03 | 2 | 2 | 2 | 2 | 2 | Không đoán sản phẩm từ “mẫu kia”; hỏi tên hoặc SKU. |
| M04 | 2 | — | 2 | 2 | 1 | Đơn được tạo sau tin bổ sung; quantity từ lượt đầu được giữ. PII trong extraction đã che. |
| M05 | 2 | 1 | 2 | 2 | 1 | Lượt đầu missing_information của model chưa liệt kê variant dù thiếu màu/size; backend vẫn hỏi đúng. Các lượt sau giữ item và tạo đúng đơn. |
| I01 | 2 | 2 | 2 | 2 | 2 | Báo SKU trắng M còn 0, không tạo đơn; có bước chọn lại biến thể/số lượng. |
| I02 | 2 | 2 | 2 | 2 | 2 | Phản hồi nêu tồn 2 và yêu cầu 3, không tạo đơn vượt tồn. |
| I03 | 2 | 2 | 2 | 2 | 2 | Không tạo SKU máy bay đồ chơi; yêu cầu sản phẩm/SKU trong catalog. |
| F01 | — | — | 2 | 2 | 2 | Invalid JSON được chèn. Không có extraction model hợp lệ để chấm; workflow trả lỗi an toàn. |
| F02 | — | — | 2 | 2 | 2 | Timeout được chèn, không phải timeout Google thật; workflow báo chậm và chưa đổi đơn. |
| F03 | — | — | 2 | 2 | 2 | Response rỗng được chèn; validation chặn và phản hồi không báo thành công giả. |
| S01 | 2 | — | 2 | 2 | 2 | Policy chặn trước LLM; handoff và không thay đổi đơn. Không coi đây là model chống injection. |
| S02 | 2 | 2 | 2 | 2 | 2 | Trích quantity 2 nhưng chưa xác định đơn; hỏi mã đơn, không sửa tùy ý. |
| Q01 | 2 | 2 | 2 | 2 | 2 | Reply nêu đúng 150,000 VND theo dữ liệu case; SKU/biến thể rõ. |
| Q02 | 2 | 2 | 2 | 2 | 2 | Reply nêu hết hàng/còn 0 và SKU đúng; không suy đoán tồn. |
| L01 | 2 | — | 2 | 2 | 1 | Màu xanh không có trong seed. Chặn đúng, nhưng “bổ sung màu/size” có thể khó hiểu vì khách đã cung cấp; nên nói rõ chọn biến thể khác. |
| L02 | 2 | 2 | 2 | 2 | 2 | Không biết “em này” là sản phẩm nào; hỏi sản phẩm/SKU thay vì đoán. |
| L03 | 2 | — | 2 | 2 | 2 | Không map được hộp 500g, chưa tạo đơn. Phone đã che nên không xác nhận được cách xử lý “09xx...” từ artifact. |
| L04 | 2 | 2 | 2 | 2 | 2 | Không có tên sản phẩm, giữ màu/size và hỏi sản phẩm/SKU. |
| L05 | 2 | 2 | 2 | 2 | 2 | Hỏi giá sản phẩm không có trong catalog; trả không tìm thấy thay vì bịa giá. |
| L06 | 2 | 2 | 2 | 2 | 2 | unknown_or_handoff và human review đúng; không biến yêu cầu hỗ trợ gấp thành sửa đơn. |
| L07 | 2 | 2 | 2 | 2 | 2 | Quantity 2 được trích, nhưng cần mã đơn; route an toàn. |
| U01 | 2 | 2 | 2 | 2 | 1 | Đơn duy nhất được đổi thành quantity 2, total 300000 theo expected; text reply chưa tóm tắt thay đổi. |
| U02 | 2 | 2 | 2 | 2 | 1 | Mã đơn rõ, đổi size L và quantity 2 đúng expected; text reply chung cần đối chiếu thẻ UI. |
| U03 | 2 | 2 | 2 | 2 | 2 | Có hai đơn thì hỏi mã, giữ nguyên cả hai dòng đơn. |
| F04 | — | — | 2 | 2 | 2 | Rate limit được chèn; phản hồi hướng dẫn đợi, không đổi đơn và không tính là 429 provider thật. |
