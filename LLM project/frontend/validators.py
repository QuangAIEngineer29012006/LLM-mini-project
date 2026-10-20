"""Kiểm tra form giao nhận phía client, chỉ để báo lỗi nhanh. Backend vẫn kiểm tra lại."""
import re

PHONE_RE = re.compile(r"^(0|\+84)(3|5|7|8|9)\d{8}$")


def validate_shipping(name, phone, address):
    """Trả về (dữ liệu đã chuẩn hóa, {field: thông báo lỗi})."""
    data = {
        "recipient_name": " ".join((name or "").split()),
        "phone": re.sub(r"[\s.\-]", "", phone or ""),
        "address": " ".join((address or "").split()),
    }
    errors = {}
    if len(data["recipient_name"]) < 2:
        errors["recipient_name"] = "Nhập tên người nhận (ít nhất 2 ký tự)."
    if not PHONE_RE.match(data["phone"]):
        errors["phone"] = "Số điện thoại chưa đúng. Ví dụ: 0912345678 hoặc +84912345678."
    if len(data["address"]) < 10:
        errors["address"] = "Nhập địa chỉ đầy đủ: số nhà, đường, phường/xã, quận/huyện."
    return data, errors
