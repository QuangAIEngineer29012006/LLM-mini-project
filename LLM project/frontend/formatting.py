"""Hằng số và hàm định dạng thuần Python (không phụ thuộc streamlit)."""
import re

STATUS_LABEL = {
    "draft": "Nháp",
    "pending_confirmation": "Chờ xác nhận",
    "needs_information": "Cần bổ sung thông tin",
    "handed_off": "Đã chuyển nhân viên",
    "failed_validation": "Không hợp lệ",
}
# Chỉ dùng khi API không trả cờ "editable"; backend vẫn là bên quyết định.
EDITABLE_STATUSES = {"draft", "pending_confirmation"}

FIELD_LABEL = {
    "recipient_name": "tên người nhận",
    "phone": "số điện thoại",
    "phone_number": "số điện thoại",
    "address": "địa chỉ giao hàng",
    "full_delivery_address": "địa chỉ giao hàng",
    "size": "size",
    "color": "màu sắc",
    "quantity": "số lượng",
    "product": "sản phẩm",
}

ERROR_TITLE = {
    "out_of_stock": "Không đủ tồn kho",
    "order_not_editable": "Đơn không còn cho phép sửa",
    "forbidden": "Không có quyền",
    "auth": "Phiên làm việc không hợp lệ",
    "not_found": "Không tìm thấy",
    "conflict": "Trạng thái hiện tại không cho phép",
    "validation": "Dữ liệu chưa hợp lệ",
    "rate_limit": "Gửi quá nhanh",
    "timeout": "Quá thời gian chờ",
    "network": "Mất kết nối",
}

_MD_PUNCT = re.compile(r"([!-/:-@\[-`{-~])")


def money(value):
    return f"{int(value):,}".replace(",", ".") + " ₫"


def safe_md(text):
    """Escape toàn bộ ký tự markdown: tin nhắn và dữ liệu từ backend là untrusted,
    không để chúng render thành link, ảnh, LaTeX hay emoji shortcode."""
    return _MD_PUNCT.sub(r"\\\1", str(text)).replace("\r", "").replace("\n", "  \n")
