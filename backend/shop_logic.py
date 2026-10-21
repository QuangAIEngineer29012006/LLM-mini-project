"""Hàm thuần (không phụ thuộc streamlit) cho catalog / chi tiết sản phẩm / giỏ hàng. Dễ test."""
import unicodedata

MAX_QTY = 99          # trần số lượng mỗi dòng; backend vẫn kiểm tra tồn kho thật
LOW_STOCK = 5
CATEGORY_LABEL = {"apparel": "Thời trang", "food": "Thực phẩm", "accessories": "Phụ kiện"}


def category_label(code):
    return CATEGORY_LABEL.get(code, str(code).capitalize())


def normalize(text):
    """Bỏ dấu + chữ thường để tìm 'ao thun' ra 'Áo thun'."""
    text = unicodedata.normalize("NFD", str(text or "").lower().replace("đ", "d"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn").strip()


def filter_products(products, category=None, query=""):
    q = normalize(query)
    return [
        p for p in products
        if (not category or p.get("category") == category)
        and (not q or q in normalize(p.get("name", "")))
    ]


def stock_label(stock):
    if stock <= 0:
        return "Hết hàng"
    if stock <= LOW_STOCK:
        return f"Sắp hết (còn {stock})"
    return f"Còn hàng ({stock})"


def max_selectable(stock):
    """Số lượng tối đa cho ô nhập (chỉ để UX; server mới là bên quyết định)."""
    return max(1, min(int(stock), MAX_QTY))


def price_text(product, fmt):
    low = product["price_from"]
    high = product.get("price_to", low)
    return fmt(low) if low == high else f"Từ {fmt(low)}"


def variant_option_label(variant, fmt):
    text = f"{variant['label']} · {fmt(variant['unit_price'])}"
    return text + (" · Hết hàng" if variant["stock"] <= 0 else "")


def pick_default_variant(variants):
    """Ưu tiên biến thể còn hàng đầu tiên."""
    for v in variants:
        if v["stock"] > 0:
            return v["sku"]
    return variants[0]["sku"] if variants else None


def chunk(seq, size):
    return [seq[i:i + size] for i in range(0, len(seq), size)]
