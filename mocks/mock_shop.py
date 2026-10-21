"""PHẦN GHÉP VÀO mock_backend.py của Huy: catalog mẫu (15 SKU, 3 nhóm) + mock API catalog/giỏ hàng.

Giữ nguyên 4 SKU cũ của Huy (cùng giá, tồn kho) để demo của Huy không đổi.
Mixin cần self.cart = [{"sku": ..., "quantity": ...}] (Huy đã có). item_id của giỏ = sku.
"""
from api_client import ApiError
from shop_logic import MAX_QTY

PRODUCTS = {
    "tshirt": {"name": "Áo thun basic", "category": "apparel", "description": "Áo thun cotton, form rộng vừa, mặc hằng ngày."},
    "jean": {"name": "Quần jean ống đứng", "category": "apparel", "description": "Jean xanh co giãn nhẹ, ống đứng."},
    "jacket": {"name": "Áo khoác gió", "category": "apparel", "description": "Áo khoác gió nhẹ, chống nước nhẹ."},
    "coffee": {"name": "Cà phê rang xay", "category": "food", "description": "Cà phê rang xay nguyên chất, đóng hộp."},
    "tea": {"name": "Trà ô long", "category": "food", "description": "Trà ô long sấy khô, gói 200g."},
    "honey": {"name": "Mật ong rừng", "category": "food", "description": "Mật ong nguyên chất, chai thủy tinh."},
    "tote": {"name": "Túi tote vải", "category": "accessories", "description": "Túi tote canvas, đựng vừa laptop 14 inch."},
    "cap": {"name": "Mũ lưỡi trai", "category": "accessories", "description": "Mũ lưỡi trai cotton, khóa điều chỉnh."},
    "bottle": {"name": "Bình giữ nhiệt", "category": "accessories", "description": "Bình inox giữ nóng/lạnh 12 giờ."},
}

# (sku, product_id, nhãn phân loại, giá, tồn kho)
_VARIANTS = [
    ("TSHIRT-BLU-M", "tshirt", "Xanh / M", 199000, 12),
    ("TSHIRT-BLU-L", "tshirt", "Xanh / L", 199000, 3),
    ("TSHIRT-BLK-M", "tshirt", "Đen / M", 209000, 0),
    ("JEAN-BLU-30", "jean", "Xanh / 30", 399000, 8),
    ("JEAN-BLU-32", "jean", "Xanh / 32", 399000, 5),
    ("JACKET-GRY-M", "jacket", "Xám / M", 459000, 6),
    ("JACKET-GRY-L", "jacket", "Xám / L", 459000, 0),
    ("COFFEE-500G", "coffee", "Hộp 500g", 245000, 20),
    ("COFFEE-1KG", "coffee", "Hộp 1kg", 459000, 9),
    ("TEA-OOLONG-200G", "tea", "Gói 200g", 189000, 15),
    ("HONEY-350ML", "honey", "Chai 350ml", 169000, 0),
    ("TOTE-NAT", "tote", "Màu kem", 99000, 30),
    ("CAP-BLK", "cap", "Đen", 129000, 14),
    ("CAP-WHT", "cap", "Trắng", 129000, 2),
    ("BOTTLE-500", "bottle", "500ml", 259000, 11),
    ("BOTTLE-750", "bottle", "750ml", 299000, 4),
]

# Cùng khóa với CATALOG của Huy (name, label, price, stock) + product_id, category.
CATALOG = {
    sku: {
        "name": PRODUCTS[pid]["name"], "label": label, "price": price, "stock": stock,
        "product_id": pid, "category": PRODUCTS[pid]["category"],
    }
    for sku, pid, label, price, stock in _VARIANTS
}


def _err(status, code, message, fields=None):
    return ApiError(message, status=status, code=code, fields=fields)


class MockShopMixin:
    # --- catalog ---
    def list_products(self):
        result = []
        for pid, p in PRODUCTS.items():
            variants = [v for v in CATALOG.values() if v["product_id"] == pid]
            prices = [v["price"] for v in variants]
            result.append({
                "product_id": pid, "name": p["name"], "category": p["category"],
                "price_from": min(prices), "price_to": max(prices),
                "in_stock": any(v["stock"] > 0 for v in variants), "variant_count": len(variants),
            })
        return result

    def get_product(self, product_id):
        if product_id not in PRODUCTS:
            raise _err(404, "not_found", "Không tìm thấy sản phẩm này.")
        p = PRODUCTS[product_id]
        return {
            "product_id": product_id, "name": p["name"], "category": p["category"],
            "description": p["description"],
            "variants": [
                {"sku": sku, "label": v["label"], "unit_price": v["price"], "stock": v["stock"]}
                for sku, v in CATALOG.items() if v["product_id"] == product_id
            ],
        }

    # --- giỏ hàng ---
    def get_cart(self):
        items = []
        for c in self.cart:
            v = CATALOG[c["sku"]]
            items.append({
                "item_id": c["sku"], "sku": c["sku"], "name": v["name"], "variant_label": v["label"],
                "quantity": c["quantity"], "unit_price": v["price"], "line_total": v["price"] * c["quantity"],
            })
        return {"items": items, "total": sum(i["line_total"] for i in items)}

    def add_to_cart(self, sku, quantity):
        self._shop_validate_qty(quantity)
        if sku not in CATALOG:
            raise _err(404, "not_found", "Sản phẩm không tồn tại.")
        line = self._shop_line(sku)
        self._shop_check_stock(sku, (line["quantity"] if line else 0) + quantity)
        if line:
            line["quantity"] += quantity
        else:
            self.cart.append({"sku": sku, "quantity": quantity})
        return self.get_cart()

    def update_cart_item(self, item_id, quantity):
        self._shop_validate_qty(quantity)
        line = self._shop_line(item_id)
        if line is None:
            raise _err(404, "not_found", "Không tìm thấy sản phẩm trong giỏ.")
        self._shop_check_stock(item_id, quantity)
        line["quantity"] = quantity
        return self.get_cart()

    def remove_cart_item(self, item_id):
        line = self._shop_line(item_id)
        if line is None:
            raise _err(404, "not_found", "Không tìm thấy sản phẩm trong giỏ.")
        self.cart.remove(line)
        return self.get_cart()

    # --- helpers ---
    def _shop_line(self, sku):
        return next((c for c in self.cart if c["sku"] == sku), None)

    def _shop_validate_qty(self, quantity):
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_QTY:
            raise _err(422, "validation", f"Số lượng phải là số nguyên từ 1 đến {MAX_QTY}.",
                       {"quantity": "Số lượng không hợp lệ."})

    def _shop_check_stock(self, sku, quantity):
        v = CATALOG[sku]
        if v["stock"] < quantity:
            msg = (f"{v['name']} ({v['label']}) đã hết hàng." if v["stock"] == 0
                   else f"{v['name']} ({v['label']}) chỉ còn {v['stock']} sản phẩm.")
            raise _err(409, "out_of_stock", msg)


class MockShopClient(MockShopMixin):
    """Client giả chạy RIÊNG phần TV3 (dev_app.py). Khi ghép, dùng MockClient của Huy."""

    def __init__(self):
        self.token = None
        self.cart = []

    def start_session(self):
        self.token = "mock-session"
