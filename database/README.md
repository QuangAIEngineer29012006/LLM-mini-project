# Vu (TV2) - Database và service dữ liệu

Phần của Vu trong LLM miniproject, theo bản phân công mới (6 việc: schema → migration/seed → catalog/inventory → cart/order → hội thoại + audit → test/tài liệu). Python 3.9+, chỉ dùng thư viện chuẩn (SQLite), **không cần cài thêm gì**.

## Chạy nhanh

```bash
python -m shop_db.seed --reset                 # tạo schema + migration + nạp dữ liệu mock (data/shop.db)
python -m unittest discover -s tests -v   # 79 test
python demo.py                                 # kịch bản demo phần dữ liệu
```

Đổi file DB: `--db đường/dẫn.db` hoặc biến môi trường `SHOP_DB_PATH`. Test dùng DB `:memory:` hoặc file tạm nên không đụng dữ liệu thật. **Reset dữ liệu demo:** `python -m shop_db.seed --reset`.

## Cấu trúc

| Việc | File | Nội dung |
|---|---|---|
| 1. Schema | `shop_db/schema.sql`, `shop_db/db.py` | Bảng sản phẩm, biến thể, tồn kho, alias, đơn, dòng đơn, audit; kết nối và transaction |
| 2. Migration + seed | `shop_db/migrations/`, `shop_db/seed.py` | Migration theo version (`PRAGMA user_version`); 17 SKU / 7 sản phẩm / 3 nhóm, alias, SKU hết hàng; lệnh seed/reset |
| 3. Catalog / inventory | `shop_db/catalog_service.py` | Tìm, tra giá/tồn kho, kiểm tra số lượng, `resolve_product` (matched / ambiguous / no_match) |
| 4. Cart / order | `shop_db/order_service.py`, `order_common.py`, `status_service.py` | Giỏ hàng, đơn nháp, snapshot giá, transaction, chống tạo đơn trùng, trừ/hoàn kho |
| 5. Hội thoại + audit | `shop_db/conversation_service.py`, `audit_service.py` | Ngữ cảnh theo phiên, tin nhắn; audit tạo/sửa đơn và chuyển trạng thái |
| 6. Test + tài liệu | `tests/`, `docs/DATABASE.md`, `demo.py` | 79 test, tài liệu schema, hướng dẫn reset, demo |

## Cách Minh (TV1) gọi service

```python
from shop_db.db import connect, migrate
from shop_db.audit_service import Ctx
from shop_db import catalog_service as catalog, order_service as orders, conversation_service as conv
from shop_db.status_service import change_status
from shop_db.errors import DataServiceError

conn = connect(); migrate(conn)                       # mỗi request/luồng một connection
ctx = Ctx("customer", "cust-42", request_id)          # actor_type: customer|staff|chat|system

catalog.resolve_product(conn, "áo thun đen size M")  # {"status": "matched", "sku": ...}
catalog.check_items(conn, [{"sku": "TSH-BLK-M", "quantity": 2}])
order = orders.create_draft_order(conn, ctx, "cust-42", items, delivery, source="chat",
                                  idempotency_key=f"{conversation_id}:{message_id}")
c = conv.get_or_create_conversation(conn, "cust-42")
conv.update_conversation(conn, c["id"], state="collecting_info", merge={"missing": ["phone"]})
try:
    change_status(conn, ctx, order["id"], "confirmed")
except DataServiceError as e:
    e.code, e.message, e.details                      # map sang mã lỗi/phản hồi an toàn
```

## Ranh giới và lưu ý khi tích hợp

- **Không kiểm tra quyền sở hữu**: Minh phải so `order["owner_id"]` / `conversation["owner_id"]` với người dùng hiện tại **trước khi** gọi hàm sửa, hủy, confirm hay đọc hội thoại.
- Giá và tổng tiền **luôn do DB tính**; service không nhận giá từ client.
- **Chống tạo đơn trùng:** truyền `idempotency_key` ổn định cho mỗi lần người dùng bấm gửi hoặc mỗi tin nhắn chat. Gửi lại cùng key và cùng nội dung → trả đơn cũ với `replayed=True`; cùng key nhưng nội dung khác → lỗi `idempotency_conflict`. Key có phạm vi theo `owner_id`.
- **Hội thoại:** `context` là JSON tối đa 8 KB, có thể chứa tên/SĐT/địa chỉ để chat dùng lại; thông tin này **không** được chép sang audit. Danh sách state (`idle`, `collecting_info`, `awaiting_confirmation`, `handoff`) nằm trong `conversation_service.STATES`, đổi theo thiết kế chung nếu cần.
- `actor_id` trong `Ctx` phải là ID nội bộ hoặc ID phiên đã băm, **không phải token/secret** (audit lưu nguyên giá trị này).
- Mỗi hàm ghi dữ liệu tự mở transaction (`BEGIN IMMEDIATE`); gọi lồng nhau thì dùng chung transaction ngoài. Lỗi → rollback toàn bộ, kể cả audit.
- Mọi lỗi nghiệp vụ là `DataServiceError` có `.code`: `validation_error`, `sku_not_found`, `out_of_stock`, `insufficient_stock`, `price_changed`, `order_not_found`, `item_not_found`, `order_not_editable`, `invalid_status_transition`, `product_not_found`, `idempotency_conflict`, `conversation_not_found`.
- `check_availability` và `resolve_product` **không raise** (trả `ok`/`reason` hoặc `status`), phù hợp cho chat; các hàm ghi thì raise.
