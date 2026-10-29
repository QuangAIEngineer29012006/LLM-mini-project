import re

from database.shop_db import catalog_service as catalog, order_service as orders
from database.shop_db.db import transaction
from database.shop_db.errors import ItemNotFound, OrderNotEditable, ValidationError

from .errors import ApiProblem
from .storage import replay, save_receipt


# Đổi dữ liệu catalog nội bộ thành cấu trúc sản phẩm/biến thể cho frontend.
def product_view(product):
    return {
        **{k: product[k] for k in ("product_id", "name", "category", "description", "in_stock")},
        "price_from": product["price_min"], "price_to": product["price_max"],
        "variants": [{"sku": v["sku"], "label": v["variant_name"], "unit_price": v["price"],
                      "stock": v["stock"], "color": v["color"], "size": v["size"]}
                     for v in product["variants"]],
    }


# Kiểm tra mã đơn dạng DH000001 rồi lấy phần ID số để truy vấn database.
def order_number(value):
    if not isinstance(value, str) or not re.fullmatch(r"DH\d{6,10}", value):
        raise ApiProblem(404, "not_found", "Không tìm thấy đơn hàng trong phiên của bạn.")
    return int(value[2:])


# Lấy đơn và từ chối truy cập nếu đơn không thuộc chủ phiên đang yêu cầu.
def owned_order(conn, owner, order_id):
    order = orders.get_order(conn, order_id)
    if order["owner_id"] != owner:
        raise ApiProblem(404, "not_found", "Không tìm thấy đơn hàng trong phiên của bạn.")
    return order


# Ghép dòng hàng, biến thể có thể đổi và giao nhận thành dữ liệu đơn cho frontend.
def order_view(conn, order):
    rows = conn.execute("SELECT * FROM order_items WHERE order_id=? ORDER BY id", (order["id"],)).fetchall()
    items = []
    for row in rows:
        variants = conn.execute(
            "SELECT v.sku, v.variant_name FROM product_variants v JOIN products p ON p.id=v.product_id"
            " WHERE v.product_id=(SELECT product_id FROM product_variants WHERE sku=?)"
            " AND v.is_active=1 AND p.is_active=1 ORDER BY v.sku", (row["sku"],)).fetchall()
        items.append({"item_id": str(row["id"]), "sku": row["sku"], "name": row["product_name"],
                      "variant_label": row["variant_name"], "quantity": row["quantity"],
                      "unit_price": row["unit_price"], "line_total": row["line_total"],
                      "available_variants": [{"sku": v["sku"], "label": v["variant_name"]} for v in variants]})
    return {"order_id": f"DH{order['id']:06d}", "status": order["status"],
            "editable": order["status"] in {"cart", "pending_confirmation"},
            "shipping": {"recipient_name": order["customer_name"], "phone": order["phone"], "address": order["address"]},
            "items": items, "total": order["total_amount"], "source": order["source"]}


# Tìm giỏ gắn với phiên; chỉ tạo giỏ mới khi tham số create được bật.
def cart_order(conn, session, ctx, create=False):
    row = conn.execute("SELECT cart_id FROM api_sessions WHERE owner_id=?", (session["owner_id"],)).fetchone()
    if row and row["cart_id"]:
        return owned_order(conn, session["owner_id"], row["cart_id"])
    if create:
        order = orders.create_cart(conn, ctx, session["owner_id"], [])
        conn.execute("UPDATE api_sessions SET cart_id=? WHERE owner_id=?", (order["id"], session["owner_id"]))
        return order
    return None


# Trả giỏ theo định dạng frontend hoặc cấu trúc giỏ trống nếu chưa có giỏ.
def cart_view(conn, session, ctx):
    order = cart_order(conn, session, ctx)
    if order is None:
        return {"items": [], "total": 0}
    return order_view(conn, order)


# Lấy dòng hàng theo cả mã đơn và item ID để tránh thao tác nhầm đơn.
def item_row(conn, order_id, item_id):
    row = conn.execute("SELECT * FROM order_items WHERE order_id=? AND CAST(id AS TEXT)=?",
                       (order_id, item_id)).fetchone()
    if row is None:
        raise ItemNotFound("Không tìm thấy sản phẩm trong đơn.")
    return row


# Sửa số lượng/biến thể trong transaction, kiểm tra quyền và trạng thái cho phép sửa.
def update_item(conn, ctx, owner, order_id, item_id, changes):
    with transaction(conn):
        order = owned_order(conn, owner, order_id)
        if order["status"] not in {"cart", "pending_confirmation"}:
            raise OrderNotEditable("Đơn không còn cho phép chỉnh sửa.")
        old = item_row(conn, order_id, item_id)
        sku, qty = changes.get("sku", old["sku"]), changes.get("quantity", old["quantity"])
        if sku == old["sku"]:
            return orders.set_item_quantity(conn, ctx, order_id, sku, qty)
        before, after = catalog.get_variant(conn, old["sku"]), catalog.get_variant(conn, sku)
        if before["product_id"] != after["product_id"]:
            raise ValidationError("Chỉ được đổi biến thể thuộc cùng sản phẩm.", field="sku")
        orders.remove_item(conn, ctx, order_id, old["sku"])
        return orders.add_item(conn, ctx, order_id, sku, qty)


# Chuyển giỏ thành đơn chờ xác nhận, tách giỏ khỏi phiên và lưu kết quả chống gửi trùng.
def checkout(conn, ctx, session, shipping, key):
    owner = session["owner_id"]
    with transaction(conn):
        existing = replay(conn, owner, "checkout", key, shipping)
        if existing:
            return existing
        cart = cart_order(conn, session, ctx)
        if not cart or not cart["items"]:
            raise ApiProblem(409, "empty_cart", "Giỏ hàng đang trống.")
        delivery = {"customer_name": shipping["recipient_name"], "phone": shipping["phone"], "address": shipping["address"]}
        order = orders.submit_order(conn, ctx, cart["id"], delivery)
        conn.execute("UPDATE api_sessions SET cart_id=NULL WHERE owner_id=?", (owner,))
        result = order_view(conn, order)
        save_receipt(conn, owner, "checkout", key, shipping, result)
        return result
