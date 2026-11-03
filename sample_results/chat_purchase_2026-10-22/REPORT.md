# Đặt hàng qua bot — 22/10/2026

Đã bổ sung luồng đặt hàng ngay trong chat React, dùng Gemini 3.5 Flash-Lite, FastAPI và catalog SQLite hiện tại. Prompt hiện tại `shop-assistant-v4`.

## Cách dùng

Nhắn: **“đặt cho tôi balo laptop Balo laptop xám, 15inch”**. Bot xác định `BAG-GRY-15`, Balo laptop — Xám / 15 inch, giá 520.000 VND, tồn 4. Vì câu này chưa có số lượng và giao nhận nên bot hỏi thêm; không âm thầm đặt 1 sản phẩm.

Trong chat có thẻ sản phẩm và form số lượng, tên người nhận, điện thoại, địa chỉ. Số lượng 1 trên form là giá trị đề xuất để khách xem/sửa trước khi bấm gửi. Khách vẫn có thể nhắn tiếp bằng chữ, ví dụ “Chốt 2 BAG-GRY-15, Tên Khách Demo, SĐT 0912345678, giao về 12 Đường Mẫu, Quận 7”.

Khi đủ thông tin và còn hàng, bot tạo đơn `pending_confirmation`, hiển thị mã đơn, sản phẩm/biến thể, số lượng, tổng tiền và nút mở đúng đơn trong Đơn hàng. Đây là đơn chờ cửa hàng xác nhận; chưa thanh toán, chưa giữ/trừ kho.

## Thay đổi

- Chuẩn hóa size `15inch`/`15 inch` khi đối chiếu biến thể và kiểm tra evidence, giữ số đo chính xác; `16inch` không bị đổi thành `15 inch`.
- Prompt v4 phân biệt số đo với số lượng và không mặc định số lượng 1 khi câu chỉ có tên hàng. Server bỏ số lượng model tự điền khi khách chưa nêu, sau đó hỏi lại. Số trong SKU, phần giao nhận, số đo không được dùng làm số lượng; lượng âm/thập phân hoặc số lượng khác lời khách bị chặn.
- Response `ask_missing` bổ sung `purchase.items` từ DB để UI hiển thị thông tin sản phẩm. Tất cả lần tạo đơn vẫn đi qua validation, kiểm tra giá/tồn hiện tại, quyền phiên và idempotency; không nhận giá/tổng tiền từ form.
- Form ngay trong chat gửi một tin nhắn mới có các giá trị khách vừa chọn; không cần chuyển sang giỏ hàng. Khi khách yêu cầu sản phẩm/biến thể khác không xác định được, form của lựa chọn cũ ngừng hoạt động để tránh đặt nhầm.
- Chat hiển thị tóm tắt đơn thực tế thay vì chỉ trả câu “đã tạo đơn”. Thêm gợi ý “Đặt balo xám 15 inch”. Form có nhãn, lỗi nhập liệu và kích thước input phù hợp mobile.

## Kiểm tra

| Hạng mục | Kết quả | Bằng chứng |
|---|---|---|
| Python application + database | **180/180 PASS** (101 + 79), gồm 11 regression đặt hàng mới | [python-tests.txt](python-tests.txt), `tests/test_chat_purchase.py` |
| React integration | **12/12 PASS**, gồm 3 regression form đặt hàng mới | [react-tests.txt](react-tests.txt), `frontend/src/App.test.tsx` |
| TypeScript + production build | PASS | [build.txt](build.txt) |
| 29 case workflow offline hiện có | 18/18 + 11/11 PASS, FakeLLM | [Bộ chính](fake_main/evaluation_fake.md), [bộ bổ sung](fake_literal/evaluation_fake.md) |
| Gemini thật qua UI, SQLite thử riêng | Câu ví dụ → hỏi số lượng/giao nhận → form → tạo đơn → mở Đơn hàng | [live_gemini_order.json](live_gemini_order.json), [ảnh chat](gemini-created-order.png) |

Kết quả live thử riêng: tạo đúng một đơn `source=chat`, `pending_confirmation`; `BAG-GRY-15` số lượng 2, đơn giá 520.000, tổng 1.040.000 VND. Inventory vẫn 4. Hai lượt Gemini thực tế có route `ask_missing` rồi `draft_created`, retry 0. Dữ liệu giao nhận là dữ liệu demo. Không tạo đơn này trong DB vận hành. Các service thử tại 8001/5174 đã dừng sau kiểm tra.

Trước sửa, gọi đúng câu ví dụ bằng prompt v3 trả `failed_validation/ungrounded_output`: model tự trích số lượng 1 dù không có trong câu. Đây là lỗi trích xuất bị validation chặn, không phải lỗi database hay đơn đã tạo nhưng không hiển thị. Lần sửa này giữ việc chặn tạo đơn không đủ căn cứ và bổ sung đường hỏi tiếp có thể hoàn thành đơn.

Bộ 29 case Gemini đầy đủ ngày 21/10 không chạy lại trong lần này; 29 case mới chạy ở đây là offline. Kết quả live đặt hàng ở bảng trên là luồng mới, không phải điểm chất lượng tổng quát của model. Form hiện gửi thông tin qua tin nhắn `/api/chat`, nên giao nhận demo đi qua provider giống chế độ chat trước đó. Chưa kiểm tra bàn phím ảo trên điện thoại thật hoặc Windows/Safari trong lần này.

Web chính 5173 đã được kiểm tra lại bằng đúng câu ví dụ sau khi restart backend: Gemini v4 trả `ask_missing` cùng thẻ sản phẩm/form. Xem [ảnh form đang chạy](chat-purchase-form.png) và [summary.json](summary.json). Tổng lượt generation thực trong đợt này: 5 (2 chẩn đoán trước sửa, 2 cho luồng tạo đơn thử, 1 kiểm tra web chính), không retry. Catalog và tổng số đơn trong DB vận hành trước/sau giữ nguyên.
