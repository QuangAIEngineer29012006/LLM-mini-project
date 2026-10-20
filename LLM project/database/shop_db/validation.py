import re

from .errors import SkuNotFound, ValidationError

MAX_ITEMS_PER_ORDER = 20
MAX_QTY_PER_ITEM = 99
DELIVERY_FIELDS = ("customer_name", "phone", "address")

_SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9_\-]{0,39}$")
_PHONE_RE = re.compile(r"^(?:\+84|0)(\d{9})$")


def validate_quantity(q, field: str = "quantity") -> int:
    if isinstance(q, bool) or not isinstance(q, int):
        raise ValidationError("Số lượng phải là số nguyên", field=field)
    if q < 1 or q > MAX_QTY_PER_ITEM:
        raise ValidationError(f"Số lượng phải từ 1 đến {MAX_QTY_PER_ITEM}", field=field)
    return q


def normalize_sku(sku) -> str:
    if not isinstance(sku, str):
        raise ValidationError("SKU phải là chuỗi", field="sku")
    s = sku.strip().upper()
    if not _SKU_RE.match(s):
        raise SkuNotFound("SKU không hợp lệ hoặc không tồn tại", sku=sku[:40])
    return s


def normalize_items(items, allow_empty: bool = False) -> list:
    if not isinstance(items, (list, tuple)):
        raise ValidationError("items phải là danh sách", field="items")
    if not items and not allow_empty:
        raise ValidationError("Danh sách sản phẩm đang trống", field="items")
    merged: dict = {}
    for it in items:
        if not isinstance(it, dict) or "sku" not in it or "quantity" not in it:
            raise ValidationError("Mỗi item cần có sku và quantity", field="items")
        sku = normalize_sku(it["sku"])
        qty = validate_quantity(it["quantity"])
        merged[sku] = merged.get(sku, 0) + qty
    if len(merged) > MAX_ITEMS_PER_ORDER:
        raise ValidationError(f"Tối đa {MAX_ITEMS_PER_ORDER} sản phẩm mỗi đơn", field="items")
    for sku, q in merged.items():
        if q > MAX_QTY_PER_ITEM:
            raise ValidationError(f"Tối đa {MAX_QTY_PER_ITEM} cho mỗi sản phẩm", sku=sku)
    return list(merged.items())


def validate_delivery(delivery, require_all: bool = False) -> dict:
    if not isinstance(delivery, dict):
        raise ValidationError("Thông tin giao nhận phải là object", field="delivery")
    unknown = sorted(set(delivery) - set(DELIVERY_FIELDS))
    if unknown:
        raise ValidationError("Có trường giao nhận không hợp lệ", fields=unknown)

    clean, errors = {}, {}
    for key, value in delivery.items():
        if not isinstance(value, str):
            errors[key] = "Phải là chuỗi"
            continue
        if any(ord(c) < 32 and c not in "\t\n\r" for c in value):
            errors[key] = "Chứa ký tự không hợp lệ"
            continue
        v = " ".join(value.split())
        if key == "customer_name" and not (2 <= len(v) <= 100):
            errors[key] = "Tên phải từ 2 đến 100 ký tự"
        elif key == "address" and not (5 <= len(v) <= 200):
            errors[key] = "Địa chỉ phải từ 5 đến 200 ký tự"
        elif key == "phone":
            m = _PHONE_RE.match(re.sub(r"[ .\-]", "", v))
            if not m:
                errors[key] = "Số điện thoại không hợp lệ"
            else:
                v = "0" + m.group(1)
        if key not in errors:
            clean[key] = v
    if require_all:
        for key in DELIVERY_FIELDS:
            if key not in delivery:
                errors[key] = "Bắt buộc"
    if errors:
        raise ValidationError("Thông tin giao nhận không hợp lệ", errors=errors)
    return clean
