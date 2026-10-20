from .db import NOW_SQL
from .errors import InsufficientStock, OrderNotFound, PriceChanged, SkuNotFound, ValidationError
from .validation import DELIVERY_FIELDS

STATUSES = ("cart", "pending_confirmation", "confirmed", "cancelled")
EDITABLE_STATUSES = ("cart", "pending_confirmation")


def fetch_order(conn, order_id):
    if isinstance(order_id, bool) or not isinstance(order_id, int):
        raise OrderNotFound("Không tìm thấy đơn hàng", order_id=str(order_id)[:30])
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if row is None:
        raise OrderNotFound("Không tìm thấy đơn hàng", order_id=order_id)
    return row


def missing_delivery_fields(row) -> list:
    return [f for f in DELIVERY_FIELDS if not row[f]]


def order_to_dict(conn, order_id) -> dict:
    r = fetch_order(conn, order_id)
    items = [dict(i) for i in conn.execute(
        "SELECT sku, product_name, variant_name, quantity, unit_price, line_total"
        " FROM order_items WHERE order_id = ? ORDER BY id", (order_id,))]
    return {
        "id": r["id"], "owner_id": r["owner_id"], "source": r["source"], "status": r["status"],
        "customer_name": r["customer_name"], "phone": r["phone"], "address": r["address"],
        "delivery_complete": not missing_delivery_fields(r),
        "items": items, "item_count": sum(i["quantity"] for i in items),
        "total_amount": r["total_amount"], "created_at": r["created_at"], "updated_at": r["updated_at"],
    }


def recalc_total(conn, order_id) -> int:
    total = conn.execute("SELECT COALESCE(SUM(line_total), 0) FROM order_items WHERE order_id = ?",
                         (order_id,)).fetchone()[0]
    conn.execute(f"UPDATE orders SET total_amount = ?, updated_at = {NOW_SQL} WHERE id = ?", (total, order_id))
    return total


def reprice_and_check_stock(conn, order_id, allow_price_change: bool = True) -> list:
    """Đọc lại giá/tồn kho từ DB cho mọi dòng của đơn.

    - Thiếu hàng: raise InsufficientStock (details.shortages liệt kê từng SKU).
    - Giá đổi: allow_price_change=True -> cập nhật snapshot, trả danh sách thay đổi;
               False -> raise PriceChanged (không sửa gì).
    """
    rows = conn.execute(
        "SELECT oi.sku, oi.quantity, oi.unit_price, v.price AS cur_price,"
        "       v.is_active AS v_active, p.is_active AS p_active, COALESCE(i.quantity, 0) AS stock"
        " FROM order_items oi"
        " JOIN product_variants v ON v.sku = oi.sku"
        " JOIN products p ON p.id = v.product_id"
        " LEFT JOIN inventory i ON i.sku = oi.sku"
        " WHERE oi.order_id = ? ORDER BY oi.id", (order_id,)).fetchall()
    if not rows:
        raise ValidationError("Đơn hàng chưa có sản phẩm nào", field="items")
    gone = [r["sku"] for r in rows if not (r["v_active"] and r["p_active"])]
    if gone:
        raise SkuNotFound("Có sản phẩm đã ngừng bán", skus=gone)
    shortages = [{"sku": r["sku"], "requested": r["quantity"], "available": r["stock"],
                  "reason": "out_of_stock" if r["stock"] == 0 else "insufficient_stock"}
                 for r in rows if r["quantity"] > r["stock"]]
    if shortages:
        raise InsufficientStock("Không đủ tồn kho", shortages=shortages)
    changes = [{"sku": r["sku"], "old_price": r["unit_price"], "new_price": r["cur_price"]}
               for r in rows if r["cur_price"] != r["unit_price"]]
    if changes and not allow_price_change:
        raise PriceChanged("Giá đã thay đổi từ lúc thêm vào đơn", changes=changes)
    for r in rows:
        if r["cur_price"] != r["unit_price"]:
            conn.execute("UPDATE order_items SET unit_price = ?, line_total = ? * quantity"
                         " WHERE order_id = ? AND sku = ?",
                         (r["cur_price"], r["cur_price"], order_id, r["sku"]))
    recalc_total(conn, order_id)
    return changes
