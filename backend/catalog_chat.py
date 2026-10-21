from database.shop_db import catalog_service as catalog
from database.shop_db.text_utils import normalize

from .services import product_view
from .variant_utils import attribute_value
from src.parser import Extraction


def local_catalog_request(message):
    text = normalize(message)
    browse = {"cua hang ban gi", "cua hang ban nhung gi", "cua hang ban ban nhung gi", "shop ban gi", "shop ban nhung gi",
              "toi muon tham khao san pham", "toi muon tham khao san pham cua hang ban ban nhung gi",
              "cho toi xem san pham", "cho xem san pham", "xem catalog", "xem danh muc san pham"}
    price = {"gia bao nhieu", "mau nay gia bao nhieu", "gia mau nay bao nhieu"}
    stock = {"con hang khong", "mau nay con hang khong", "mau nay con khong"}
    intent = "browse_catalog" if text in browse else "check_price" if text in price else "check_stock" if text in stock else None
    if intent is None:
        return None
    items = [] if intent == "browse_catalog" else [{"requested_product": None, "sku": None, "quantity": None,
                                                  "variant": {"color": None, "size": None}}]
    return Extraction.model_validate({"intent": intent, "confidence": "high", "items": items,
                                      "customer": {"name": None, "phone": None, "address": None},
                                      "order_reference": None, "missing_information": [], "requires_human_review": False,
                                      "evidence": [message]})


def _matches(value, actual, field=None):
    requested, known = attribute_value(value, field), attribute_value(actual, field)
    return not value or requested == known or (field == "color" and known.startswith(requested + " "))


def find_products(conn, items, filters):
    found = {}
    for item in items or [{"requested_product": None, "sku": None, "variant": {}}]:
        query, sku = item.get("requested_product"), item.get("sku")
        if sku:
            variant = catalog.get_variant(conn, sku)
            products = [catalog.get_product(conn, variant["product_id"])]
        elif query:
            categories = [c for c in catalog.list_categories(conn) if normalize(c) == normalize(query)]
            products = catalog.list_products(conn, category=categories[0], limit=100) if categories else catalog.search_products(conn, query, limit=20)
        else:
            products = catalog.list_products(conn, limit=100)
        for p in products:
            if filters.category and not _matches(filters.category, p["category"]):
                continue
            requested = item.get("variant", {})
            variants = [v for v in p["variants"]
                        if (not sku or v["sku"] == sku)
                        and _matches(requested.get("color"), v["color"], field="color")
                        and _matches(requested.get("size"), v["size"], field="size")
                        and (filters.min_price is None or v["price"] >= filters.min_price)
                        and (filters.max_price is None or v["price"] <= filters.max_price)
                        and (not filters.in_stock_only or v["stock"] > 0)]
            if not variants:
                continue
            if p["product_id"] in found:
                previous = found[p["product_id"]]["variants"]
                variants = list({v["sku"]: v for v in [*previous, *variants]}.values())
            found[p["product_id"]] = {**p, "variants": variants,
                                      "price_min": min(v["price"] for v in variants),
                                      "price_max": max(v["price"] for v in variants),
                                      "in_stock": any(v["stock"] > 0 for v in variants)}
    return list(found.values())


def catalog_reply(conn, items, filters, intent):
    products = find_products(conn, items, filters)
    if not products:
        return {"reply": "Hiện cửa hàng chưa có sản phẩm khớp yêu cầu trong catalog. Bạn có thể đổi từ khóa, màu/size hoặc mức giá để mình tìm lại.",
                "route": "catalog_empty", "missing_fields": [], "order": None, "products": []}
    shown = products[:8]
    if intent == "browse_catalog":
        lines = ["Mình tìm được các sản phẩm sau trong cửa hàng:"]
    else:
        lines = ["Thông tin hiện tại từ cửa hàng:"]
    for index, p in enumerate(shown, 1):
        lines.append(f"\n{index}. {p['name']} ({p['category']})")
        if intent == "browse_catalog" and p.get("description"):
            lines.append(p["description"])
        if intent == "browse_catalog" and len(shown) > 1:
            price = f"{p['price_min']:,} VND" if p["price_min"] == p["price_max"] else f"{p['price_min']:,}–{p['price_max']:,} VND"
            lines.append(f"Giá {price}; " + ("còn hàng." if p["in_stock"] else "hiện hết hàng."))
            continue
        for v in p["variants"]:
            stock = f"còn {v['stock']} sản phẩm" if v["stock"] else "hết hàng (còn 0 sản phẩm)"
            facts = f"giá {v['price']:,} VND; {stock}"
            lines.append(f"- {v['variant_name']} ({v['sku']}): {facts}.")
    if len(products) > len(shown):
        lines.append(f"\nĐang hiển thị {len(shown)}/{len(products)} sản phẩm phù hợp. Bạn muốn xem nhóm nào cụ thể?")
    else:
        lines.append("\nBạn muốn xem kỹ sản phẩm, màu hoặc size nào?")
    return {"reply": "\n".join(lines), "route": {"browse_catalog": "catalog_shown", "check_price": "price_checked", "check_stock": "stock_checked"}[intent],
            "missing_fields": [], "order": None, "products": [product_view(p) for p in shown]}


def browsing_context(result):
    products = result.get("products", [])
    return {"catalog_product_ids": [p["product_id"] for p in products],
            "catalog_skus": [v["sku"] for p in products for v in p["variants"]][:40]}


def resolve_reference(conn, items, context, message):
    ids = context.get("catalog_product_ids", [])
    if not ids or not items or len(items) != 1:
        return items
    item = items[0]
    query = normalize(item.get("requested_product"))
    references = {"mau nay", "mau do", "cai nay", "cai do", "ao nay", "ao do", "san pham nay", "san pham do", "mau dau tien", "mau cuoi"}
    if item.get("sku") or (query and query not in references):
        return items
    text = normalize(message)
    if "mau dau tien" in text or "san pham dau tien" in text:
        target = ids[0]
    elif "mau cuoi" in text or "san pham cuoi" in text:
        target = ids[-1]
    elif len(ids) == 1:
        target = ids[0]
    else:
        return items
    product = catalog.get_product(conn, target)
    result = {**item, "requested_product": product["name"]}
    skus = [v["sku"] for v in product["variants"] if v["sku"] in context.get("catalog_skus", [])]
    if len(skus) == 1 and not any(item["variant"].values()):
        result["sku"] = skus[0]
    return [result]
