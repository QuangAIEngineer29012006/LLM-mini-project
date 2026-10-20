"""Giỏ hàng / đơn nháp / order_items. Mọi thay đổi nằm trong 1 transaction + có audit.

Lưu ý ranh giới: service này KHÔNG kiểm tra chủ sở hữu. Minh (TV1) phải kiểm tra
(order["owner_id"] == người dùng hiện tại) trước khi gọi hàm sửa/hủy/confirm.
Giá luôn lấy từ DB; client không thể truyền giá.
"""
import hashlib
import json
import re

from .audit_service import Ctx, log_event
from .db import NOW_SQL, transaction
from .errors import (IdempotencyConflict, InsufficientStock, ItemNotFound, OrderNotEditable, OutOfStock,
                     SkuNotFound, ValidationError)
from .order_common import (EDITABLE_STATUSES, fetch_order, order_to_dict, recalc_total,
                           reprice_and_check_stock)
from .status_service import change_status
from .validation import normalize_items, normalize_sku, validate_delivery, validate_quantity

SOURCES = ("web", "chat")


def _clean_owner(owner_id) -> str:
    if not isinstance(owner_id, str) or not (1 <= len(owner_id.strip()) <= 100):
        raise ValidationError("owner_id không hợp lệ", field="owner_id")
    return owner_id.strip()


_KEY_RE = re.compile(r"^[A-Za-z0-9_\-:.]{8,100}$")


def _clean_key(key):
    if key is None:
        return None
    if not isinstance(key, str) or not _KEY_RE.match(key):
        raise ValidationError("idempotency_key phải dài 8-100 ký tự gồm chữ, số, _-:.", field="idempotency_key")
    return key


def _request_hash(source, merged, delivery) -> str:
    payload = {"source": source, "items": sorted([list(x) for x in merged]), "delivery": delivery}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _replay(conn, ctx, owner, key, req_hash):
    if key is None:
        return None
    row = conn.execute("SELECT id, request_hash FROM orders WHERE owner_id = ? AND idempotency_key = ?",
                       (owner, key)).fetchone()
    if row is None:
        return None
    if row["request_hash"] != req_hash:
        raise IdempotencyConflict("idempotency_key đã được dùng cho yêu cầu khác", idempotency_key=key)
    log_event(conn, ctx, "duplicate_request_ignored", row["id"], details={"idempotency_key": key})
    order = order_to_dict(conn, row["id"])
    order["replayed"] = True
    return order


def _require_editable(row) -> None:
    if row["status"] not in EDITABLE_STATUSES:
        raise OrderNotEditable("Đơn hàng không còn chỉnh sửa được", status=row["status"])


def _upsert_item(conn, order_id, sku, new_qty) -> None:
    v = conn.execute(
        "SELECT v.sku, v.variant_name, v.price, p.name AS product_name, COALESCE(i.quantity, 0) AS stock"
        " FROM product_variants v JOIN products p ON p.id = v.product_id"
        " LEFT JOIN inventory i ON i.sku = v.sku"
        " WHERE v.sku = ? AND v.is_active = 1 AND p.is_active = 1", (sku,)).fetchone()
    if v is None:
        raise SkuNotFound("SKU không tồn tại hoặc đã ngừng bán", sku=sku)
    if v["stock"] == 0:
        raise OutOfStock("Sản phẩm đã hết hàng", sku=sku, requested=new_qty, available=0)
    if new_qty > v["stock"]:
        raise InsufficientStock("Không đủ tồn kho", sku=sku, requested=new_qty, available=v["stock"])
    conn.execute(
        "INSERT INTO order_items (order_id, sku, product_name, variant_name, quantity, unit_price, line_total)"
        " VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(order_id, sku) DO UPDATE SET quantity = excluded.quantity,"
        "   unit_price = excluded.unit_price, line_total = excluded.line_total,"
        "   product_name = excluded.product_name, variant_name = excluded.variant_name",
        (order_id, sku, v["product_name"], v["variant_name"], new_qty, v["price"], v["price"] * new_qty))


def _current_qty(conn, order_id, sku) -> int:
    r = conn.execute("SELECT quantity FROM order_items WHERE order_id = ? AND sku = ?", (order_id, sku)).fetchone()
    return r["quantity"] if r else 0


def create_cart(conn, ctx: Ctx, owner_id, items, source: str = "web", idempotency_key=None) -> dict:
    """Tạo giỏ (status=cart). items có thể rỗng. Lỗi bất kỳ -> không để lại đơn nào.

    idempotency_key: gửi lại cùng key + cùng nội dung thì trả đơn cũ (replayed=True), không tạo đơn mới."""
    owner = _clean_owner(owner_id)
    key = _clean_key(idempotency_key)
    if source not in SOURCES:
        raise ValidationError("source không hợp lệ", field="source")
    merged = normalize_items(items, allow_empty=True)
    req_hash = _request_hash(source, merged, None)
    with transaction(conn):
        replay = _replay(conn, ctx, owner, key, req_hash)
        if replay:
            return replay
        order_id = conn.execute(
            "INSERT INTO orders (owner_id, source, status, idempotency_key, request_hash) VALUES (?,?,'cart',?,?)",
            (owner, source, key, req_hash if key else None)).lastrowid
        for sku, qty in merged:
            _upsert_item(conn, order_id, sku, qty)
        total = recalc_total(conn, order_id)
        log_event(conn, ctx, "order_created", order_id, None, "cart",
                  {"source": source, "items": [{"sku": s, "quantity": q} for s, q in merged], "total_amount": total})
        order = order_to_dict(conn, order_id)
        order["replayed"] = False
        return order


def create_draft_order(conn, ctx: Ctx, owner_id, items, delivery, source: str = "web", idempotency_key=None) -> dict:
    """Tạo đơn nháp hoàn chỉnh (pending_confirmation) trong 1 transaction - dùng cho luồng web và chat.

    Chống tạo trùng: truyền idempotency_key ổn định cho mỗi lần người dùng bấm gửi / mỗi tin nhắn chat
    (ví dụ f"{conversation_id}:{message_id}"). Gửi lại cùng key thì nhận lại đơn cũ."""
    owner = _clean_owner(owner_id)
    key = _clean_key(idempotency_key)
    merged = normalize_items(items)
    clean = validate_delivery(delivery, require_all=True)
    req_hash = _request_hash(source, merged, clean)
    with transaction(conn):
        replay = _replay(conn, ctx, owner, key, req_hash)
        if replay:
            return replay
        order = create_cart(conn, ctx, owner, items, source)
        conn.execute(f"UPDATE orders SET customer_name = ?, phone = ?, address = ?, idempotency_key = ?,"
                     f" request_hash = ?, updated_at = {NOW_SQL} WHERE id = ?",
                     (clean["customer_name"], clean["phone"], clean["address"], key,
                      req_hash if key else None, order["id"]))
        log_event(conn, ctx, "delivery_updated", order["id"], details={"changed_fields": sorted(clean)})
        order = change_status(conn, ctx, order["id"], "pending_confirmation")
        order["replayed"] = False
        return order


def get_order(conn, order_id) -> dict:
    return order_to_dict(conn, order_id)


def list_orders(conn, owner_id, statuses=None, limit: int = 20) -> list:
    owner = _clean_owner(owner_id)
    sql, params = "SELECT id FROM orders WHERE owner_id = ?", [owner]
    if statuses:
        sql += f" AND status IN ({','.join('?' * len(statuses))})"
        params += list(statuses)
    sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 100)))
    return [order_to_dict(conn, r["id"]) for r in conn.execute(sql, params).fetchall()]


def get_latest_order(conn, owner_id, statuses=EDITABLE_STATUSES):
    found = list_orders(conn, owner_id, statuses=statuses, limit=1)
    return found[0] if found else None


def add_item(conn, ctx: Ctx, order_id, sku, quantity) -> dict:
    s, qty = normalize_sku(sku), validate_quantity(quantity)
    with transaction(conn):
        _require_editable(fetch_order(conn, order_id))
        new_qty = _current_qty(conn, order_id, s) + qty
        validate_quantity(new_qty)
        _upsert_item(conn, order_id, s, new_qty)
        total = recalc_total(conn, order_id)
        log_event(conn, ctx, "item_added", order_id, details={"sku": s, "quantity": qty,
                                                              "new_quantity": new_qty, "total_amount": total})
        return order_to_dict(conn, order_id)


def set_item_quantity(conn, ctx: Ctx, order_id, sku, quantity) -> dict:
    s, qty = normalize_sku(sku), validate_quantity(quantity)
    with transaction(conn):
        _require_editable(fetch_order(conn, order_id))
        old_qty = _current_qty(conn, order_id, s)
        if old_qty == 0:
            raise ItemNotFound("Sản phẩm không có trong đơn", sku=s)
        _upsert_item(conn, order_id, s, qty)
        total = recalc_total(conn, order_id)
        log_event(conn, ctx, "item_quantity_changed", order_id,
                  details={"sku": s, "old_quantity": old_qty, "new_quantity": qty, "total_amount": total})
        return order_to_dict(conn, order_id)


def remove_item(conn, ctx: Ctx, order_id, sku) -> dict:
    s = normalize_sku(sku)
    with transaction(conn):
        _require_editable(fetch_order(conn, order_id))
        old_qty = _current_qty(conn, order_id, s)
        if old_qty == 0:
            raise ItemNotFound("Sản phẩm không có trong đơn", sku=s)
        conn.execute("DELETE FROM order_items WHERE order_id = ? AND sku = ?", (order_id, s))
        total = recalc_total(conn, order_id)
        log_event(conn, ctx, "item_removed", order_id,
                  details={"sku": s, "old_quantity": old_qty, "total_amount": total})
        return order_to_dict(conn, order_id)


def update_delivery(conn, ctx: Ctx, order_id, delivery) -> dict:
    clean = validate_delivery(delivery, require_all=False)
    if not clean:
        raise ValidationError("Không có thông tin giao nhận để cập nhật", field="delivery")
    with transaction(conn):
        _require_editable(fetch_order(conn, order_id))
        sets = ", ".join(f"{k} = ?" for k in clean)
        conn.execute(f"UPDATE orders SET {sets}, updated_at = {NOW_SQL} WHERE id = ?", (*clean.values(), order_id))
        log_event(conn, ctx, "delivery_updated", order_id, details={"changed_fields": sorted(clean)})
        return order_to_dict(conn, order_id)


def refresh_prices(conn, ctx: Ctx, order_id) -> dict:
    with transaction(conn):
        _require_editable(fetch_order(conn, order_id))
        changes = reprice_and_check_stock(conn, order_id, allow_price_change=True)
        if changes:
            log_event(conn, ctx, "prices_refreshed", order_id, details={"price_changes": changes})
        return order_to_dict(conn, order_id)


def submit_order(conn, ctx: Ctx, order_id, delivery=None) -> dict:
    with transaction(conn):
        if delivery is not None:
            update_delivery(conn, ctx, order_id, delivery)
        return change_status(conn, ctx, order_id, "pending_confirmation")
