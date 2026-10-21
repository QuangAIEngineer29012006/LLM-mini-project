"""API client duy nhất của frontend.

Mọi dữ liệu đi qua đây. Frontend không truy cập database và không gửi giá,
tổng tiền, tồn kho, user_id hay trạng thái lên server: những giá trị đó do backend quyết định.
"""
import os
import uuid
from urllib.parse import quote

import requests

from backend.shop_api import ShopApiMixin

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
TIMEOUT = float(os.getenv("API_TIMEOUT_SECONDS", "55"))

_KIND_BY_STATUS = {
    401: "auth", 403: "forbidden", 404: "not_found",
    409: "conflict", 422: "validation", 429: "rate_limit",
}


class ApiError(Exception):
    """Lỗi đã chuẩn hóa để UI hiển thị.

    status=None nghĩa là chưa nhận được phản hồi (code = "timeout" hoặc "network").
    fields: {tên_field: thông báo} khi backend báo lỗi theo từng trường.
    """

    def __init__(self, message, status=None, code=None, fields=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.fields = fields or {}

    @property
    def kind(self):
        if self.status is None:
            return self.code or "network"
        return _KIND_BY_STATUS.get(self.status, "server")


def _parse_error(response):
    """Đọc lỗi dạng {"error": {code, message, fields}} (hoặc {"detail": "..."})."""
    try:
        body = response.json()
    except ValueError:
        body = {}
    body = body if isinstance(body, dict) else {}
    err = body.get("error") if isinstance(body.get("error"), dict) else {}
    detail = body.get("detail") if isinstance(body.get("detail"), str) else None
    message = err.get("message") or detail or f"Máy chủ gặp lỗi (mã {response.status_code}). Hãy thử lại sau."
    fields = err.get("fields") if isinstance(err.get("fields"), dict) else {}
    return ApiError(message, status=response.status_code, code=err.get("code"), fields=fields)


class ApiClient(ShopApiMixin):
    def __init__(self, base_url=API_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.http = requests.Session()
        self.token = None
        self._pending_chat = None

    def _request(self, method, path, headers=None, **kwargs):
        all_headers = dict(headers or {})
        if self.token:
            all_headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = self.http.request(
                method, self.base_url + path, headers=all_headers, timeout=TIMEOUT, **kwargs
            )
        except requests.Timeout:
            raise ApiError("Máy chủ phản hồi quá chậm. Hãy thử lại sau ít phút.", code="timeout")
        except requests.RequestException:
            raise ApiError("Không kết nối được tới máy chủ. Kiểm tra mạng rồi thử lại.", code="network")
        if not response.ok:
            raise _parse_error(response)
        return response.json() if response.content else {}

    # --- phiên khách hàng: dùng chung cho đặt hàng trên web và chat ---
    def start_session(self):
        self.token = self._request("POST", "/api/session")["token"]

    # --- giỏ hàng / đơn ---
    def get_cart(self):
        return self._request("GET", "/api/cart")

    def create_order(self, shipping, idempotency_key=None):
        """Chỉ gửi thông tin giao nhận; backend tự lấy giỏ hàng, giá và tồn kho."""
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._request("POST", "/api/orders", json={"shipping": shipping}, headers=headers)

    def list_orders(self):
        return self._request("GET", "/api/orders")["orders"]

    def get_order(self, order_id):
        return self._request("GET", f"/api/orders/{quote(str(order_id), safe='')}")

    def update_item(self, order_id, item_id, changes):
        """changes: {"quantity": int} và/hoặc {"sku": str} (đổi biến thể)."""
        path = f"/api/orders/{quote(str(order_id), safe='')}/items/{quote(str(item_id), safe='')}"
        return self._request("PATCH", path, json=changes)

    # --- chat: backend hiểu tin nhắn và quyết định hành động ---
    def chat(self, message):
        if not self._pending_chat or self._pending_chat[0] != message:
            self._pending_chat = (message, uuid.uuid4().hex)
        result = self._request("POST", "/api/chat", json={"message": message},
                               headers={"Idempotency-Key": self._pending_chat[1]})
        self._pending_chat = None
        return result
