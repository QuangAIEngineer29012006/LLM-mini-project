import json

from shop_db import audit_service as audit
from shop_db import catalog_service as cat
from shop_db import conversation_service as conv
from shop_db import order_service as orders
from shop_db.audit_service import Ctx
from shop_db.db import connect
from shop_db.errors import DataServiceError
from shop_db.seed import reset_and_seed
from shop_db.status_service import change_status


def step(title):
    print(f"\n=== {title} ===")


conn = connect(":memory:")
step("1. Reset + seed DB mới")
print(reset_and_seed(conn))

customer = Ctx("customer", "cust-42", "req-001")
staff = Ctx("staff", "staff-7", "req-002")

step("2. Tìm sản phẩm (không phân biệt dấu, hiểu alias, màu/size)")
top = cat.search_products(conn, "cho mình hỏi áo thun đen size M")[0]
print(top["name"], "| score", top["score"], "| SKU khớp:", top["matched_skus"])

step("3. Tra giá/tồn kho và kiểm tra số lượng")
print("Giá TSH-BLK-M:", cat.get_price(conn, "TSH-BLK-M"), "| tồn:", cat.get_stock(conn, "TSH-BLK-M"))
for sku, qty in [("TSH-BLK-M", 2), ("TSH-WHT-M", 1), ("HOD-GRY-L", 9), ("NOPE-1", 1)]:
    r = cat.check_availability(conn, sku, qty)
    print(f"  {sku} x{qty}: ok={r['ok']} reason={r['reason']} available={r['available']}")

step("4. Tạo đơn nháp (snapshot giá từ DB, tổng tiền do server tính)")
order = orders.create_draft_order(
    conn, customer, "cust-42",
    [{"sku": "TSH-BLK-M", "quantity": 2}, {"sku": "CAP-BLK-F", "quantity": 1}],
    {"customer_name": "Nguyễn Văn A", "phone": "0912 345 678", "address": "12 Phố Huế, Hà Nội"})
print("Đơn", order["id"], order["status"], "| tổng", order["total_amount"], "| SĐT lưu:", order["phone"])

step("5. Lỗi hết hàng -> rollback, không để lại đơn rác")
before = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
try:
    orders.create_cart(conn, customer, "cust-42", [{"sku": "HOD-GRY-L", "quantity": 10}])
except DataServiceError as e:
    print(e.to_dict())
print("Số đơn trước/sau:", before, conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0])

step("6. Giá đổi sau khi lên đơn: snapshot giữ nguyên, confirm báo lỗi rõ ràng")
conn.execute("UPDATE product_variants SET price = 160000 WHERE sku = 'TSH-BLK-M'")
print("Giá trong đơn vẫn là", orders.get_order(conn, order["id"])["items"][0]["unit_price"])
try:
    change_status(conn, staff, order["id"], "confirmed")
except DataServiceError as e:
    print(e.code, e.details)
orders.refresh_prices(conn, customer, order["id"])

step("7. Confirm: trừ tồn kho trong cùng transaction")
print("Tồn trước:", cat.get_stock(conn, "TSH-BLK-M"))
o = change_status(conn, staff, order["id"], "confirmed")
print("Trạng thái:", o["status"], "| tổng", o["total_amount"], "| tồn sau:", cat.get_stock(conn, "TSH-BLK-M"))

step("8. Audit log (đã lọc dữ liệu nhạy cảm)")
for e in audit.list_events(conn, order_id=order["id"]):
    print(f"  #{e['id']} {e['actor_type']}:{e['actor_id']} {e['action']} "
          f"{e['old_status']}->{e['new_status']} {json.dumps(e['details'], ensure_ascii=False)}")

step("9. Mapping rõ ràng: matched / ambiguous / no_match")
for q in ("áo thun đen size M", "áo thun đen", "áo", "xe máy"):
    r = cat.resolve_product(conn, q)
    extra = r["sku"] or [c.get("sku") or c["name"] for c in r["candidates"]]
    print(f"  {q!r:24} -> {r['status']:9} {r['reason']:20} {extra}")

step("10. Ngữ cảnh hội thoại theo phiên (thiếu thông tin -> hỏi bổ sung)")
c = conv.create_conversation(conn, "cust-99")
conv.add_message(conn, c["id"], "user", "mình muốn đặt 1 nón lưỡi trai đen")
conv.update_conversation(conn, c["id"], state="collecting_info", pending_intent="create_order",
                         merge={"items": [{"sku": "CAP-BLK-F", "quantity": 1}], "missing": ["customer_name", "phone", "address"]})
conv.add_message(conn, c["id"], "assistant", "Bạn cho mình xin tên, SĐT và địa chỉ nhận hàng nhé?")
conv.update_conversation(conn, c["id"], merge={"customer_name": "Trần C", "missing": ["phone", "address"]})
got = conv.get_conversation(conn, c["id"])
print("state:", got["state"], "| intent:", got["pending_intent"], "| context:", json.dumps(got["context"], ensure_ascii=False))
print("số tin nhắn lưu:", len(conv.get_messages(conn, c["id"])))

step("11. Chống tạo đơn trùng (bấm gửi 2 lần / chat gửi lại)")
items = [{"sku": "CAP-BLK-F", "quantity": 1}]
delivery = {"customer_name": "Trần C", "phone": "0987654321", "address": "5 Láng Hạ, Hà Nội"}
first = orders.create_draft_order(conn, customer, "cust-99", items, delivery, "chat", idempotency_key=f"{c['id']}:msg-3")
again = orders.create_draft_order(conn, customer, "cust-99", items, delivery, "chat", idempotency_key=f"{c['id']}:msg-3")
print("lần 1: đơn", first["id"], "replayed =", first["replayed"], "| lần 2: đơn", again["id"], "replayed =", again["replayed"])
print("số đơn của cust-99:", len(orders.list_orders(conn, "cust-99")))
