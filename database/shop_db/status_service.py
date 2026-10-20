"""Cập nhật trạng thái đơn + trừ/hoàn tồn kho trong cùng transaction.

cart -> pending_confirmation -> confirmed;  mọi trạng thái chưa kết thúc -> cancelled.
Tồn kho chỉ bị trừ khi đơn chuyển sang `confirmed`, hoàn lại nếu hủy đơn đã confirmed.
"""
from .audit_service import Ctx, log_event
from .db import NOW_SQL, transaction
from .errors import InsufficientStock, InvalidStatusTransition, ValidationError
from .order_common import STATUSES, fetch_order, missing_delivery_fields, order_to_dict, reprice_and_check_stock

ALLOWED_TRANSITIONS = {
    "cart": {"pending_confirmation", "cancelled"},
    "pending_confirmation": {"confirmed", "cancelled"},
    "confirmed": {"cancelled"},
    "cancelled": set(),
}


def change_status(conn, ctx: Ctx, order_id, new_status, reason=None) -> dict:
    if new_status not in STATUSES:
        raise ValidationError("Trạng thái không hợp lệ", field="status")
    with transaction(conn):
        row = fetch_order(conn, order_id)
        old = row["status"]
        if new_status not in ALLOWED_TRANSITIONS[old]:
            raise InvalidStatusTransition(f"Không thể chuyển từ {old} sang {new_status}",
                                          from_status=old, to_status=new_status)
        price_changes, stock_adjusted = [], False

        if new_status in ("pending_confirmation", "confirmed"):
            missing = missing_delivery_fields(row)
            if missing:
                raise ValidationError("Thiếu thông tin giao nhận", missing=missing)
            price_changes = reprice_and_check_stock(conn, order_id, allow_price_change=(new_status != "confirmed"))

        items = conn.execute("SELECT sku, quantity FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
        if new_status == "confirmed":
            for it in items:
                cur = conn.execute(
                    f"UPDATE inventory SET quantity = quantity - ?, updated_at = {NOW_SQL}"
                    " WHERE sku = ? AND quantity >= ?", (it["quantity"], it["sku"], it["quantity"]))
                if cur.rowcount != 1:  # có người khác vừa lấy hàng -> rollback toàn bộ
                    raise InsufficientStock("Không đủ tồn kho", shortages=[{"sku": it["sku"]}])
            stock_adjusted = True
        elif old == "confirmed" and new_status == "cancelled":
            for it in items:
                conn.execute(f"UPDATE inventory SET quantity = quantity + ?, updated_at = {NOW_SQL} WHERE sku = ?",
                             (it["quantity"], it["sku"]))
            stock_adjusted = True

        conn.execute(f"UPDATE orders SET status = ?, updated_at = {NOW_SQL} WHERE id = ?", (new_status, order_id))
        log_event(conn, ctx, "status_changed", order_id, old, new_status,
                  {"reason": reason, "price_changes": price_changes, "stock_adjusted": stock_adjusted})
        return order_to_dict(conn, order_id)
