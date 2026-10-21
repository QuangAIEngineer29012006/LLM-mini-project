"""Backend giả theo đúng hợp đồng API (xem README_frontend.md), để dev/test frontend độc lập.
Bật bằng biến môi trường FRONTEND_MOCK=1. Khi tích hợp, đổi sang ApiClient mà không sửa màn hình nào."""
import copy
import itertools
import re

from api_client import ApiError
from mock_shop import CATALOG, MockShopMixin

EDITABLE = {"draft", "pending_confirmation"}


def _err(status, code, message, fields=None):
    return ApiError(message, status=status, code=code, fields=fields)


class MockClient(MockShopMixin):
    def __init__(self):
        self.token = None
        self.cart = [{"sku": "TSHIRT-BLU-M", "quantity": 2}]
        self.orders = {}
        self._seq = itertools.count(1001)
        self._by_key = {}
        self._awaiting_info = False

    def start_session(self):
        self.token = "mock-session"

    # --- helpers ---
    def _line(self, item_id, sku, qty):
        p = CATALOG[sku]
        variants = [{"sku": s, "label": v["label"]} for s, v in CATALOG.items() if v["name"] == p["name"]]
        return {
            "item_id": item_id, "sku": sku, "name": p["name"], "variant_label": p["label"],
            "quantity": qty, "unit_price": p["price"], "line_total": p["price"] * qty,
            "available_variants": variants,
        }

    def _check_stock(self, sku, qty):
        p = CATALOG[sku]
        if p["stock"] < qty:
            raise _err(409, "out_of_stock", f"{p['name']} ({p['label']}) chỉ còn {p['stock']} sản phẩm.")

    def _new_order(self, lines, shipping):
        for sku, qty in lines:
            self._check_stock(sku, qty)
        items = [self._line(str(i), s, q) for i, (s, q) in enumerate(lines, 1)]
        order = {
            "order_id": f"DH{next(self._seq)}", "status": "pending_confirmation", "editable": True,
            "shipping": shipping, "items": items, "total": sum(i["line_total"] for i in items),
        }
        self.orders[order["order_id"]] = order
        return copy.deepcopy(order)

    # --- API ---
    def create_order(self, shipping, idempotency_key=None):
        if idempotency_key in self._by_key:
            return copy.deepcopy(self.orders[self._by_key[idempotency_key]])
        if not self.cart:
            raise _err(409, "empty_cart", "Giỏ hàng đang trống.")
        errors = {}
        if not re.fullmatch(r"(0|\+84)\d{9}", shipping.get("phone", "")):
            errors["phone"] = "Số điện thoại phải có 10 chữ số."
        if len(shipping.get("recipient_name", "")) < 2:
            errors["recipient_name"] = "Tên người nhận quá ngắn."
        if len(shipping.get("address", "")) < 10:
            errors["address"] = "Địa chỉ quá ngắn."
        if errors:
            raise _err(422, "validation", "Thông tin giao nhận chưa hợp lệ.", errors)
        order = self._new_order([(c["sku"], c["quantity"]) for c in self.cart], shipping)
        if idempotency_key:
            self._by_key[idempotency_key] = order["order_id"]
        return order

    def list_orders(self):
        return copy.deepcopy(list(self.orders.values()))

    def get_order(self, order_id):
        if order_id not in self.orders:
            raise _err(404, "not_found", "Không tìm thấy đơn hàng này trong phiên của bạn.")
        return copy.deepcopy(self.orders[order_id])

    def update_item(self, order_id, item_id, changes):
        order = self.orders.get(order_id) or self.get_order(order_id)  # get_order ném 404
        if order["status"] not in EDITABLE:
            raise _err(409, "order_not_editable", "Đơn đã chuyển trạng thái nên không thể sửa.")
        old = next((i for i in order["items"] if i["item_id"] == item_id), None)
        if old is None:
            raise _err(404, "not_found", "Không tìm thấy sản phẩm trong đơn.")
        sku, qty = changes.get("sku", old["sku"]), changes.get("quantity", old["quantity"])
        if sku not in CATALOG or qty < 1:
            raise _err(422, "validation", "Phân loại hoặc số lượng không hợp lệ.")
        self._check_stock(sku, qty)
        order["items"][order["items"].index(old)] = self._line(item_id, sku, qty)
        order["total"] = sum(i["line_total"] for i in order["items"])
        return copy.deepcopy(order)

    def chat(self, message):
        text = message.lower()
        reply = lambda msg, route, missing=(), order=None: {
            "reply": msg, "route": route, "missing_fields": list(missing), "order": order,
        }
        if "bỏ qua" in text or "api key" in text:
            return reply("Yêu cầu này cần nhân viên xem xét nên đã được chuyển tiếp.", "handoff")
        if "timeout" in text:
            raise ApiError("Máy chủ phản hồi quá chậm. Hãy thử lại sau ít phút.", code="timeout")
        if "giá" in text:
            return reply("Áo thun basic giá 199.000 ₫.", "answer")
        if "chốt" in text or self._awaiting_info:
            phone = re.search(r"0\d{9}", text.replace(" ", ""))
            if not phone:
                self._awaiting_info = True
                return reply("Bạn cho mình xin tên, số điện thoại và địa chỉ nhận hàng nhé.", "ask_missing",
                             ["recipient_name", "phone", "address"])
            self._awaiting_info = False
            order = self._new_order([("TSHIRT-BLU-M", 2)],
                                    {"recipient_name": "Khách demo", "phone": phone.group(), "address": "Quận 7, TP.HCM"})
            return reply("Mình đã tạo đơn nháp, bạn kiểm tra lại giúp nhé.", "draft_created", order=order)
        return reply("Mình chưa rõ yêu cầu của bạn nên đã chuyển cho nhân viên.", "handoff")
