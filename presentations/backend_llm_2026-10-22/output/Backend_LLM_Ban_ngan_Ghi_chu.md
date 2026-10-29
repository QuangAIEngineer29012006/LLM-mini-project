# Backend và xử lý LLM: bản trình bày ngắn

12 slide, thời lượng gợi ý 10–15 phút. Mỗi slide có ghi chú trong PowerPoint.

Bản 88 slide và tài liệu giải thích 100 hàm được giữ nguyên để tra cứu.

## 1. Backend và xử lý LLM

Bản 12 slide dùng khoảng 10–15 phút. Theo dõi một yêu cầu đặt balo từ HTTP tới database. File PowerPoint đầy đủ 88 slide và tài liệu 100 hàm vẫn được giữ để tra cứu.

## 2. Pipeline chung của backend

Đọc từ trái sang phải ở hàng trên, sau đó theo đường nối xuống hàng dưới. Mọi đường ghi đơn đều qua server và DB. Route catalog công khai không cần phiên, còn giỏ/đơn/chat phải có token. Web đi thẳng business service; chat có thêm nhánh hiểu ngôn ngữ.

## 3. Nơi nhận request chat

Giải thích decorator khai báo route, ChatRequest là Pydantic model của body, Request chứa headers/IP. request_key đọc Idempotency-Key. session_db trả kết nối, phiên và Ctx. limiter.check áp giới hạn chat theo owner. Chưa có thao tác tạo đơn ở route này.

## 4. Ngữ cảnh gửi cho model

_catalog_context tìm theo câu hiện tại và sản phẩm đang hỏi, giới hạn 6 sản phẩm và 10 alias mỗi sản phẩm. Context catalog gồm tên, category, description, alias, sku/color/size. Hàm không gửi giá/tồn cho model để model quyết định nghiệp vụ. Không gửi toàn bộ lịch sử chat thô.
_catalog_context ở backend/chat_service.py:45–57 lấy sản phẩm liên quan từ DB, tối đa 6 sản phẩm. Model nhận catalog rút gọn và các trường hội thoại cần thiết. Prompt v4 yêu cầu một JSON có intent, items, customer và evidence. Quy tắc chỉ trích trường mới nằm tại src/prompts.py:21–29.

## 5. Pipeline xử lý LLM

Theo dõi nhánh Gemini của workflow. generate chỉ trả LLMResult. parse_output tạo Extraction. discard_implicit_quantities và validate_grounding kiểm tra dữ liệu trước khi ghép vào context. Sau đó chat dispatch hành động và chỉ ghi trong transaction sau khi kiểm tra lại phiên/revision. Lỗi provider hoặc output chặn đường ghi và trả failed_validation.

## 6. Gọi Gemini qua REST

Đây là implementation REST bằng requests, không dùng SDK agent/tool-calling. API key lấy từ settings và nằm trong header x-goog-api-key. Deck chỉ trích tên biến, không chứa giá trị key. requests.post dùng timeout cấu hình và không tự đi theo redirect.
Giới hạn ngày nằm trong src/quota.py. Mỗi HTTP attempt giữ một lượt trước khi gửi mạng. Các câu catalog rõ nghĩa có thể qua rule và không gọi Gemini. Model ID lấy từ cấu hình. Ví dụ kết quả đã lưu dùng gemini-3.5-flash-lite, không coi đây là tuyên bố về quota nhà cung cấp.

## 7. Kiểm tra kết quả LLM

generate trả LLMResult.text. parse_output kiểm tra chuỗi, kích thước, JSON nghiêm ngặt rồi gọi Extraction.model_validate. discard_implicit_quantities bỏ lượng tự điền. validate_grounding so giá trị với câu khách hiện tại trước khi ghép context. JSON hợp schema không đủ để tự tạo đơn. Nếu provider hoặc output lỗi, workflow trả failed_validation và không thay đổi đơn. Nguồn: src/parser.py:67–78,118–163 và backend/chat_service.py:237–254.

## 8. Ví dụ: 15inch không phải số lượng 15

quantity_source loại số đo, SKU và phần giao nhận khỏi nguồn kiểm tra quantity. discard_implicit_quantities đưa quantity về None nếu không có số lượng rõ ràng cho create_order/update_order. Sau đó _draft kiểm tra trường thiếu và trả ask_missing. Khi khách gửi số lượng mới, _merge_items ghép với biến thể đã chọn. Không coi 15inch là 15 sản phẩm. Nguồn: src/parser.py:104–124, backend/chat_service.py:61–73,121–156.

## 9. Chọn nhánh nghiệp vụ

browse_catalog đọc hàng, create_order gọi _draft, update_order gọi _update, các câu price/stock qua _query. Nếu requires_human_review hoặc confidence thấp hoặc unknown_or_handoff thì handoff trước dispatch. Không có API confirm payment/order cho khách.
Trước đoạn dispatch này, server ghép context ở dòng 271–282. Câu hỏi giá/tồn xen giữa vẫn có thể giữ pending_intent đặt hàng. Các hàm _query, _draft, _update và catalog_reply thực hiện nghiệp vụ tương ứng.

## 10. Tạo đơn nháp qua bot

orders.create_draft_order ở database/shop_db/order_service.py kiểm tra owner/key/items/delivery, tạo cart trong transaction rồi chuyển trạng thái. Giá từng item đọc từ catalog bởi _upsert_item. Lỗi nào cũng rollback. _draft không có nhánh tự xác nhận thanh toán.

## 11. Giá tiền và trạng thái đơn trong DB

Tiếp tục đọc order_common.reprice_and_check_stock và recalc_total nếu được hỏi. change_status khi chuyển confirmed mới có logic trừ kho nhưng API khách hàng hiện tại không cung cấp đường confirm. Kiểm tra tổng của ví dụ balo: 2 × 520000 = 1040000.
Luồng chat gọi Gemini trước transaction ghi. Sau khi model trả, server xác thực lại phiên và revision hội thoại ở backend/chat_service.py:255–265 rồi mới dispatch. create_draft_order đọc giá từ catalog, tạo dòng hàng và chuyển trạng thái trong transaction. Lỗi ở giữa rollback để tránh đơn dở dang. Giá và tồn do lớp dữ liệu quyết định.

## 12. Ví dụ balo đã chạy bằng Gemini thật

Bằng chứng là log đã lưu ngày 22/10 trên SQLite thử riêng. Hai lượt model thật có prompt v4, retry 0. Không sử dụng FakeLLM cho con số live này. Đơn thử không nằm trong DB vận hành. Khi demo trên lớp có thể gõ lại câu đầu, sau đó điền form; phụ thuộc quota và mạng ở thời điểm demo.
Đây là bằng chứng đã lưu ngày 22/10/2026 trên DB thử riêng, không phải một lần gọi Gemini mới khi tạo slide. Giới hạn bản demo: rate limiter trong RAM cho một process, phiên có hạn, chưa có tài khoản khôi phục đơn và hàng đợi nhân viên. Kiểm tra từ vựng chưa bảo đảm hiểu mọi cách nói. Bản dài có kết quả test và tra cứu 100 hàm.
