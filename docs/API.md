# Hợp đồng API

Base URL mặc định: `http://127.0.0.1:8000`. API nhận/trả JSON. Swagger tại `/docs` liệt kê schema request đầy đủ.

## Phiên và quyền truy cập

`POST /api/session` trả `{ "token": "...", "expires_at": 1790000000 }`. Đây là token ngẫu nhiên không chứa thông tin khách hàng; thời gian hết hạn là Unix timestamp. Gửi `Authorization: Bearer <token>` cho cart, order, chat. `DELETE /api/session` thu hồi phiên. Token chỉ lưu hash SHA-256 trong SQLite. React giữ token trong local storage và gửi token ở các request tiếp theo; API giữ phiên trong SQLite đến khi hết hạn hoặc thu hồi.

Catalog/health là public. Không nhận `owner_id`, `role`, giá, tổng tiền, tồn kho hoặc trạng thái từ client. Các trường ngoài allowlist bị từ chối bằng 422. Khách hàng khác truy cập/sửa đơn trả 404, kể cả biết mã đơn và item ID. API không có endpoint quản trị hoặc xác nhận đơn cho khách hàng.

## Endpoint

| Method | Path | Body | Quyền / kết quả |
|---|---|---|---|
| GET | `/api/health` | | Public; trạng thái DB và provider/model đang chọn, không thử gọi Google |
| POST | `/api/session` | | Public; tạo token (201), rate limit theo IP |
| DELETE | `/api/session` | | Phiên hiện tại; thu hồi token |
| GET | `/api/products` | | Public; `{products: [...]}` |
| GET | `/api/products/{product_id}` | | Public; một sản phẩm đang bán và các biến thể |
| GET | `/api/cart` | | Chỉ giỏ hiện tại của phiên |
| POST | `/api/cart/items` | `{sku, quantity}` | Gộp cùng SKU, kiểm tra tổng số lượng/tồn kho |
| PATCH | `/api/cart/items/{item_id}` | `{quantity}` | Đặt số lượng mới trên giỏ của phiên |
| DELETE | `/api/cart/items/{item_id}` | | Xóa dòng khỏi giỏ của phiên |
| POST | `/api/orders` | `{shipping: {recipient_name, phone, address}}` | Gửi giỏ thành đơn chờ xác nhận, kiểm tra lại giá/tồn, làm trống giỏ hiện tại |
| GET | `/api/orders` | | Tối đa 100 đơn của phiên, không gồm giỏ chưa gửi |
| GET | `/api/orders/{order_id}` | | Chỉ đơn thuộc phiên, mã `DH000001` |
| PATCH | `/api/orders/{order_id}/items/{item_id}` | `{quantity}` và/hoặc `{sku}` | Chỉ cart/pending_confirmation; đổi SKU phải cùng sản phẩm |
| POST | `/api/chat` | `{message}` | Tin nhắn tối đa 500 ký tự; trích xuất + validation + workflow |

Số lượng là integer 1-99, không chấp nhận bool, chuỗi số hoặc số thập phân. Giao nhận: tên 2-100 ký tự, điện thoại Việt Nam dạng `0xxxxxxxxx`/`+84xxxxxxxxx` sau chuẩn hóa, địa chỉ 10-200 ký tự. Validation này chỉ kiểm tra hình thức, chưa xác minh số điện thoại hoặc địa chỉ thật.

`item_id` là chuỗi ID dòng từ DB, không phải SKU. Đổi biến thể có thể gộp với dòng SKU đã có; dùng response mới sau mỗi lần sửa vì item ID có thể thay đổi. Giá/tổng tiền được tính tại server. Đơn nháp chưa giữ hàng và chưa trừ tồn kho.

Ví dụ sản phẩm trả về:

```json
{"product_id":1,"name":"Áo thun basic cotton","category":"Áo","description":"...","price_from":150000,"price_to":150000,"in_stock":true,"variants":[{"sku":"TSH-BLK-M","label":"Đen / M","unit_price":150000,"stock":25,"color":"Đen","size":"M"}]}
```

Ví dụ đơn trả về:

```json
{"order_id":"DH000001","status":"pending_confirmation","editable":true,"shipping":{"recipient_name":"Khách Demo","phone":"0912345678","address":"12 Đường Mẫu, Quận 7"},"items":[{"item_id":"1","sku":"TSH-BLK-M","name":"Áo thun basic cotton","variant_label":"Đen / M","quantity":2,"unit_price":150000,"line_total":300000,"available_variants":[{"sku":"TSH-BLK-M","label":"Đen / M"}]}],"total":300000,"source":"chat"}
```

## Chat và chống gửi trùng

`POST /api/orders` và `POST /api/chat` hỗ trợ header `Idempotency-Key` dài 8-100 ký tự, gồm chữ, số và `_-:.`. Khóa có scope theo chủ phiên và endpoint. Cùng key/cùng body trả response đã lưu; cùng key/khác body trả 409. Dùng key mới cho thao tác mới. Checkout hash thông tin giao nhận trong body, không hash giỏ có thể đã được làm trống sau request thành công.

Frontend tạo key cho checkout và chat. Nếu chat lỗi mạng, client giữ key cho lần gửi lại cùng message. Lỗi JSON/LLM không được cache receipt để người dùng có thể thử lại. Với hai tin nhắn chat khác nhau xử lý đồng thời, backend từ chối tin tính trên context cũ bằng 409 `conversation_busy`; người dùng gửi lại sau khi lượt trước hoàn tất.

Response chat:

```json
{"reply":"Vui lòng bổ sung: tên người nhận, số điện thoại, địa chỉ đầy đủ.","route":"ask_missing","missing_fields":["recipient_name","phone","address"],"order":null,"request_id":"...","intent":"create_order"}
```

Route: `catalog_shown`, `catalog_empty`, `ask_missing`, `draft_created`, `order_updated`, `price_checked`, `stock_checked`, `out_of_stock`, `handoff`, `failed_validation`. Lỗi LLM trả HTTP 200 với route `failed_validation` và `error_type`; chưa ghi order. Lỗi API/business như không có quyền, trạng thái đơn khóa hoặc tồn kho khi sửa đơn trả HTTP tương ứng. Handoff ghi nhận trạng thái cần hỗ trợ và audit của hội thoại.

`browse_catalog` trả thêm `products` theo schema API catalog. Có thể xem toàn bộ nhóm hàng, tìm theo tên/alias, lọc màu/size, ngân sách và chỉ hàng còn tồn. Price bounds do LLM trích xuất phải có số tiền tương ứng trong message; backend áp dụng bộ lọc trên giá trong DB. Không cần nhập giao nhận để xem hàng. `check_price`/`check_stock` có thể trả nhiều biến thể của một sản phẩm, không bắt chọn SKU trước khi xem thông tin. Chỉ khi có yêu cầu mua rõ ràng mới vào nhánh tạo đơn, bắt buộc xác định duy nhất SKU và đủ giao nhận.

Backend lưu ID/SKU đã hiển thị trong context của phiên, đọc lại DB ở lượt sau để xử lý `giá bao nhiêu`, `mẫu này`, hoặc `mẫu đầu tiên`. Không chọn đại một sản phẩm khi người dùng nói `lấy 2 cái` sau khi vừa xem nhiều sản phẩm. Xem catalog giữa luồng thu thập giao nhận không xóa đơn đang thu thập.

Response có `interpretation_source`: `local_catalog` cho mẫu hỏi catalog/giá/tồn rõ nghĩa được xử lý bằng rule, `gemini` cho lượt gọi model thật, hoặc `fake` trong chế độ test offline. Route đọc catalog luôn lấy dữ liệu hiện tại từ SQLite. Timeout, retry và ngân sách gọi model được cấu hình qua `.env`; bộ đếm được lưu trong SQLite và giữ qua các lần khởi động.

## Bổ sung đơn qua hội thoại

Khi `create_order` đã xác định duy nhất SKU nhưng còn thiếu số lượng/giao nhận, response `ask_missing` có thêm `purchase.items`: mỗi dòng gồm `sku`, `name`, `variant_label`, `unit_price`, `stock`, `quantity` (có thể null). Các giá trị giá/tồn và nhãn sản phẩm lấy trực tiếp từ DB. Trường này không xuất hiện cho ý định chỉ xem hàng, SKU không xác định hoặc hết hàng.

React hiển thị form trong chat; gửi form tạo một tin nhắn có số lượng, SKU và giao nhận do người dùng nhập, vẫn dùng `POST /api/chat` và `Idempotency-Key`. Backend kiểm tra lại toàn bộ dữ liệu; không tin giá/tồn từ UI. Đủ thông tin thì trả `draft_created` và `order`; chat hiển thị dòng hàng, tổng tiền và nút mở đúng đơn.

`15inch` và `15 inch` được chuẩn hóa khi đối chiếu size. Kích thước, số trong SKU, điện thoại và địa chỉ không được dùng làm số lượng. Nếu model tự điền số lượng khi khách chưa nêu, server bỏ giá trị tự điền để hỏi lại; không tự tạo đơn với số lượng mặc định. Audit có `discarded_implicit_quantity` để nhận biết bước này. Prompt hiện tại: `shop-assistant-v5`.

## Phản hồi lỗi và cấu hình request

```json
{"error":{"code":"validation","message":"Dữ liệu gửi lên chưa hợp lệ.","fields":{"quantity":"Giá trị không hợp lệ hoặc còn thiếu."}},"request_id":"..."}
```

Mã thường gặp: 401 auth, 404 resource không có trong scope, 409 stock/state/idempotency, 413 body lớn hơn 16 KB, 422 validation, 429 rate limit, 503 DB tạm thời bận. Không phản hồi input/stack trace/provider body hoặc secret. `X-Request-ID` dùng đối chiếu audit; `Cache-Control: no-store` cho response.

Mặc định: 120 request/phút/IP, 20 phiên mới/phút/IP, 10 chat/phút/phiên. 429 có `Retry-After: 60`. Bản demo chạy localhost; các giá trị được cấu hình trong `.env`.

## Tra cứu tài liệu (RAG) và quản trị index

**Role trong phiên.** `POST /api/session` mặc định tạo phiên `customer`. Gửi kèm `X-Demo-Role: staff|admin` và `X-Demo-Key: <DEMO_STAFF_KEY|DEMO_ADMIN_KEY>` để mở phiên mô phỏng; sai hoặc chưa cấu hình khóa → 403. Response có `role`. Role luôn lấy từ phiên, không bao giờ từ body.

| Method | Path | Role | Mô tả |
|---|---|---|---|
| POST | `/api/knowledge` | mọi phiên | `{"question": "..."}` → contract bên dưới. Có rate limit như chat |
| GET | `/api/knowledge/sources/{chunk_id}` | mọi phiên | Nội dung đoạn được trích, `skus`, `product_ids`. Chunk ngoài quyền và chunk không tồn tại đều trả 404 |
| GET | `/api/admin/index` | staff, admin | Trạng thái index, release corpus trong DB, tài liệu role được xem; admin thấy thêm danh sách release |
| POST | `/api/admin/reindex` | admin | `{"action": "build"\|"activate", "release": "1.1.0"}`. Rollback = activate release cũ. 409 `index_error` khi bundle hỏng hoặc chưa build |

Contract trả lời kiến thức (cũng là khối `knowledge` trong response của `/api/chat`):

```json
{"status": "answered | insufficient_evidence | access_denied | handoff | error",
 "answer": "Câu trả lời tiếng Việt có điều kiện cần thiết.",
 "citations": [{"chunk_id": "DOC-POL-WARRANTY@1.0#03", "doc_id": "DOC-POL-WARRANTY", "source": "data_config/corpus/policies/pol_bao_hanh.md",
                "version": "1.0", "title": "...", "section": "Bảo hành Balo laptop"}],
 "missing_information": ""}
```

Phiên staff/admin nhận thêm `debug` (top-k retrieval với điểm/rank/mức quyền, chunk trong context, `index_id`, cache hit) để debug và evaluation; customer không nhận.

**Trong chat.** Câu hỏi kiến thức trả `route: "knowledge"`, `intent: "knowledge_query"` và khối `knowledge`. Câu kết hợp (ví dụ hỏi bảo hành rồi chốt SKU) giữ `route` của luồng đặt hàng (`draft_created`, `ask_missing`…) và có thêm khối `knowledge`; `reply` ghép câu trả lời kiến thức với phản hồi đặt hàng. Kết quả RAG không làm thay đổi đơn, giá, tồn hay thanh toán.
