"""Catalog / inventory service. Mọi hàm nhận `conn` làm tham số đầu tiên.

Quy ước lỗi:
  - get_variant / get_price / get_stock / get_product: raise SkuNotFound / ProductNotFound.
  - check_availability: KHÔNG raise, trả dict có `ok` và `reason`.
"""
from .errors import ProductNotFound, SkuNotFound, ValidationError
from .text_utils import normalize
from .validation import normalize_items, normalize_sku

REASON_OK = "ok"
REASON_INVALID_QTY = "invalid_quantity"
REASON_SKU_NOT_FOUND = "sku_not_found"
REASON_OUT_OF_STOCK = "out_of_stock"
REASON_INSUFFICIENT = "insufficient_stock"

MIN_SEARCH_SCORE = 30

_VARIANT_SQL = """
SELECT v.sku, v.product_id, p.name AS product_name, p.category, v.variant_name,
       v.color, v.size, v.price, COALESCE(i.quantity, 0) AS stock,
       v.is_active AS variant_active, p.is_active AS product_active
FROM product_variants v
JOIN products p ON p.id = v.product_id
LEFT JOIN inventory i ON i.sku = v.sku
"""


def _variant_dict(r) -> dict:
    return {
        "sku": r["sku"], "product_id": r["product_id"], "product_name": r["product_name"],
        "category": r["category"], "variant_name": r["variant_name"],
        "color": r["color"], "size": r["size"], "price": r["price"], "stock": r["stock"],
        "in_stock": r["stock"] > 0,
    }


def get_variant(conn, sku) -> dict:
    s = normalize_sku(sku)
    r = conn.execute(_VARIANT_SQL + " WHERE v.sku = ? AND v.is_active = 1 AND p.is_active = 1", (s,)).fetchone()
    if r is None:
        raise SkuNotFound("SKU không tồn tại hoặc đã ngừng bán", sku=s)
    return _variant_dict(r)


def get_price(conn, sku) -> int:
    return get_variant(conn, sku)["price"]


def get_stock(conn, sku) -> int:
    return get_variant(conn, sku)["stock"]


def list_categories(conn) -> list:
    rows = conn.execute("SELECT DISTINCT category FROM products WHERE is_active = 1 ORDER BY category").fetchall()
    return [r["category"] for r in rows]


def _variants_by_product(conn, only_product=None) -> dict:
    sql = _VARIANT_SQL + " WHERE v.is_active = 1 AND p.is_active = 1"
    params = ()
    if only_product is not None:
        sql += " AND v.product_id = ?"
        params = (only_product,)
    out: dict = {}
    for r in conn.execute(sql + " ORDER BY v.product_id, v.sku", params):
        out.setdefault(r["product_id"], []).append(_variant_dict(r))
    return out


def _summarize(p, variants) -> dict:
    prices = [v["price"] for v in variants]
    return {
        "product_id": p["id"], "name": p["name"], "category": p["category"],
        "description": p["description"],
        "price_min": min(prices) if prices else None, "price_max": max(prices) if prices else None,
        "in_stock": any(v["in_stock"] for v in variants), "variants": variants,
    }


def get_product(conn, product_id) -> dict:
    p = conn.execute("SELECT * FROM products WHERE id = ? AND is_active = 1", (product_id,)).fetchone()
    if p is None:
        raise ProductNotFound("Sản phẩm không tồn tại hoặc đã ngừng bán", product_id=product_id)
    return _summarize(p, _variants_by_product(conn, p["id"]).get(p["id"], []))


def list_products(conn, category=None, limit: int = 50, offset: int = 0) -> list:
    if not isinstance(limit, int) or not isinstance(offset, int) or limit < 1 or offset < 0:
        raise ValidationError("limit/offset không hợp lệ")
    limit = min(limit, 100)
    rows = conn.execute("SELECT * FROM products WHERE is_active = 1 ORDER BY id").fetchall()
    if category:
        cat = normalize(category)
        rows = [p for p in rows if normalize(p["category"]) == cat]
    by_prod = _variants_by_product(conn)
    return [_summarize(p, by_prod.get(p["id"], [])) for p in rows[offset:offset + limit]]


def _score(q: str, c: str) -> int:
    if not q or not c:
        return 0
    if q == c:
        return 100
    if f" {c} " in f" {q} ":
        return 80
    if f" {q} " in f" {c} ":
        return 70
    qt, ct = set(q.split()), set(c.split())
    if ct <= qt:
        return 60
    ratio = len(qt & ct) / len(ct)
    return int(40 * ratio) if ratio >= 0.5 else 0


def _attr_hits(v, q: str) -> int:
    padded = f" {q} "
    hits = 0
    for attr in (v["color"], v["size"]):
        a = normalize(attr)
        if a and f" {a} " in padded:
            hits += 1
    return hits


def search_products(conn, query, category=None, limit: int = 5) -> list:
    q = normalize(query)
    if not q:
        return []
    products = conn.execute("SELECT * FROM products WHERE is_active = 1").fetchall()
    if category:
        cat = normalize(category)
        products = [p for p in products if normalize(p["category"]) == cat]
    by_prod = _variants_by_product(conn)
    aliases: dict = {}
    for a in conn.execute("SELECT product_id, sku, alias_normalized FROM product_aliases"):
        aliases.setdefault(a["product_id"], []).append((a["alias_normalized"], a["sku"]))

    results = []
    for p in products:
        variants = by_prod.get(p["id"], [])
        if not variants:
            continue
        best, match_type, sku_hits = 0, None, set()
        cands = [(normalize(p["name"]), "name", None)]
        cands += [(al, "alias", sku) for al, sku in aliases.get(p["id"], [])]
        cands += [(normalize(v["sku"]), "sku", v["sku"]) for v in variants]
        for text, kind, sku in cands:
            s = _score(q, text)
            if kind == "sku" and s < 80:
                s = 0
            if s > best:
                best, match_type = s, kind
            if s >= 80 and sku:
                sku_hits.add(sku)
        if q == normalize(p["category"]) and best < 50:
            best, match_type = 50, "category"
        if best < MIN_SEARCH_SCORE:
            continue
        for v in variants:
            v["match_degree"] = _attr_hits(v, q) + (2 if v["sku"] in sku_hits else 0)
        top = max(v["match_degree"] for v in variants)
        item = _summarize(p, variants)
        item.update(score=best, match_type=match_type,
                    matched_skus=[v["sku"] for v in variants if top > 0 and v["match_degree"] == top])
        results.append(item)
    results.sort(key=lambda r: (-r["score"], r["name"]))
    return results[:max(1, min(int(limit), 20))]


def check_availability(conn, sku, quantity) -> dict:
    res = {"sku": sku if isinstance(sku, str) else None, "requested": quantity,
           "available": 0, "unit_price": None, "ok": False, "reason": REASON_OK}
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        res["reason"] = REASON_INVALID_QTY
        return res
    try:
        v = get_variant(conn, sku)
    except (SkuNotFound, ValidationError):
        res["reason"] = REASON_SKU_NOT_FOUND
        return res
    res.update(sku=v["sku"], available=v["stock"], unit_price=v["price"])
    if v["stock"] == 0:
        res["reason"] = REASON_OUT_OF_STOCK
    elif quantity > v["stock"]:
        res["reason"] = REASON_INSUFFICIENT
    else:
        res["ok"] = True
    return res


def check_items(conn, items) -> dict:
    merged = normalize_items(items)
    results = [check_availability(conn, sku, qty) for sku, qty in merged]
    total = sum(r["unit_price"] * r["requested"] for r in results) if all(r["ok"] for r in results) else None
    return {"ok": all(r["ok"] for r in results), "results": results, "total_amount": total}


AMBIGUOUS_SCORE_GAP = 10


def resolve_product(conn, query) -> dict:
    """Kết quả rõ ràng cho bước mapping của chat.

    status:
      matched   - xác định đúng 1 SKU (`sku`, `variant`).
      ambiguous - nhiều ứng viên; `reason` = multiple_products | variant_unspecified | variant_ambiguous,
                  `candidates` liệt kê để hỏi lại khách.
      no_match  - không có sản phẩm nào khớp.
    Không kiểm tra tồn kho: dùng check_availability sau khi đã có SKU.
    """
    out = {"status": "no_match", "reason": "no_product_found", "query": query if isinstance(query, str) else None,
           "product": None, "sku": None, "variant": None, "candidates": []}
    results = search_products(conn, query, limit=5)
    if not results:
        return out
    top = results[0]
    close = [r for r in results if top["score"] - r["score"] < AMBIGUOUS_SCORE_GAP]
    if len(close) > 1:
        out.update(status="ambiguous", reason="multiple_products",
                   candidates=[{"product_id": r["product_id"], "name": r["name"], "score": r["score"]} for r in close])
        return out
    out["product"] = {k: top[k] for k in ("product_id", "name", "category", "price_min", "price_max", "in_stock")}
    variants = {v["sku"]: v for v in top["variants"]}
    if top["matched_skus"] and len(top["matched_skus"]) == 1:
        sku = top["matched_skus"][0]
        out.update(status="matched", reason="ok", sku=sku, variant=variants[sku])
    elif len(variants) == 1:
        sku = next(iter(variants))
        out.update(status="matched", reason="ok", sku=sku, variant=variants[sku])
    elif top["matched_skus"]:
        out.update(status="ambiguous", reason="variant_ambiguous",
                   candidates=[variants[s] for s in top["matched_skus"]])
    else:
        out.update(status="ambiguous", reason="variant_unspecified", candidates=list(variants.values()))
    return out
