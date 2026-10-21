"""PHẦN GHÉP VÀO api_client.py của Huy: mixin các lời gọi API của TV3.

Cách ghép:  from shop_api import ShopApiMixin
            class ApiClient(ShopApiMixin):  ...
Chỉ dùng self._request(...) có sẵn của ApiClient. Không gửi giá / tổng tiền / tồn kho lên server.
"""
from urllib.parse import quote


def _seg(value):
    return quote(str(value), safe="")


class ShopApiMixin:
    # --- catalog ---
    def list_products(self):
        return self._request("GET", "/api/products")["products"]

    def get_product(self, product_id):
        return self._request("GET", f"/api/products/{_seg(product_id)}")

    # --- giỏ hàng (mỗi hàm trả về giỏ hàng mới: {items, total}) ---
    def add_to_cart(self, sku, quantity):
        return self._request("POST", "/api/cart/items", json={"sku": sku, "quantity": quantity})

    def update_cart_item(self, item_id, quantity):
        return self._request("PATCH", f"/api/cart/items/{_seg(item_id)}", json={"quantity": quantity})

    def remove_cart_item(self, item_id):
        return self._request("DELETE", f"/api/cart/items/{_seg(item_id)}")
