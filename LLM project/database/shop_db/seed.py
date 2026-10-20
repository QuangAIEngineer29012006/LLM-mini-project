import argparse

from .db import connect, drop_all, migrate, transaction
from .text_utils import normalize

# stock = 0 -> hết hàng. is_active = 0 -> ngừng bán (không hiện trong catalog).
PRODUCTS = [
    {"id": 1, "name": "Áo thun basic cotton", "category": "Áo",
     "description": "Áo thun cotton 100%, form regular.",
     "aliases": ["áo thun", "áo phông", "ao thun basic", "t-shirt"],
     "variants": [
         {"sku": "TSH-BLK-M", "variant_name": "Đen / M", "color": "Đen", "size": "M", "price": 150000, "stock": 25,
          "aliases": ["áo thun đen m"]},
         {"sku": "TSH-BLK-L", "variant_name": "Đen / L", "color": "Đen", "size": "L", "price": 150000, "stock": 12},
         {"sku": "TSH-WHT-M", "variant_name": "Trắng / M", "color": "Trắng", "size": "M", "price": 150000, "stock": 0},
         {"sku": "TSH-WHT-L", "variant_name": "Trắng / L", "color": "Trắng", "size": "L", "price": 150000, "stock": 8},
     ]},
    {"id": 2, "name": "Áo hoodie nỉ", "category": "Áo",
     "description": "Hoodie nỉ bông dày, có mũ.",
     "aliases": ["hoodie", "áo nỉ", "áo khoác nỉ"],
     "variants": [
         {"sku": "HOD-GRY-M", "variant_name": "Xám / M", "color": "Xám", "size": "M", "price": 380000, "stock": 5},
         {"sku": "HOD-GRY-L", "variant_name": "Xám / L", "color": "Xám", "size": "L", "price": 380000, "stock": 3},
         {"sku": "HOD-BLK-L", "variant_name": "Đen / L", "color": "Đen", "size": "L", "price": 390000, "stock": 0},
     ]},
    {"id": 3, "name": "Giày sneaker trắng", "category": "Giày",
     "description": "Sneaker da tổng hợp, đế cao su.",
     "aliases": ["sneaker", "giày thể thao", "giày trắng"],
     "variants": [
         {"sku": "SNK-WHT-40", "variant_name": "Trắng / 40", "color": "Trắng", "size": "40", "price": 750000, "stock": 6},
         {"sku": "SNK-WHT-41", "variant_name": "Trắng / 41", "color": "Trắng", "size": "41", "price": 750000, "stock": 2,
          "aliases": ["giày trắng 41"]},
         {"sku": "SNK-WHT-42", "variant_name": "Trắng / 42", "color": "Trắng", "size": "42", "price": 750000, "stock": 0},
     ]},
    {"id": 4, "name": "Dép quai ngang", "category": "Giày",
     "description": "Dép quai ngang đế êm.",
     "aliases": ["dép", "dép lê"],
     "variants": [
         {"sku": "SLD-BLK-40", "variant_name": "Đen / 40", "color": "Đen", "size": "40", "price": 120000, "stock": 30},
         {"sku": "SLD-BLK-42", "variant_name": "Đen / 42", "color": "Đen", "size": "42", "price": 120000, "stock": 18},
     ]},
    {"id": 5, "name": "Nón lưỡi trai", "category": "Phụ kiện",
     "description": "Nón lưỡi trai cotton, khóa điều chỉnh.",
     "aliases": ["mũ lưỡi trai", "nón", "cap", "mũ"],
     "variants": [
         {"sku": "CAP-NVY-F", "variant_name": "Xanh navy / Free", "color": "Xanh navy", "size": "Free", "price": 90000, "stock": 20},
         {"sku": "CAP-BLK-F", "variant_name": "Đen / Free", "color": "Đen", "size": "Free", "price": 90000, "stock": 15},
     ]},
    {"id": 6, "name": "Balo laptop", "category": "Phụ kiện",
     "description": "Balo chống nước, ngăn laptop 15 inch.",
     "aliases": ["balo", "ba lô", "cặp laptop"],
     "variants": [
         {"sku": "BAG-GRY-15", "variant_name": "Xám / 15 inch", "color": "Xám", "size": "15 inch", "price": 520000, "stock": 4},
         {"sku": "BAG-BLK-15", "variant_name": "Đen / 15 inch", "color": "Đen", "size": "15 inch", "price": 520000, "stock": 0},
     ]},
    {"id": 7, "name": "Áo khoác dù (ngừng bán)", "category": "Áo", "is_active": 0,
     "description": "Sản phẩm đã ngừng bán - dùng để test ẩn khỏi catalog.",
     "aliases": ["áo khoác dù"],
     "variants": [
         {"sku": "JKT-NVY-L", "variant_name": "Xanh navy / L", "color": "Xanh navy", "size": "L", "price": 450000, "stock": 10},
     ]},
]


def seed_catalog(conn) -> dict:
    with transaction(conn):
        for p in PRODUCTS:
            conn.execute(
                "INSERT INTO products (id, name, category, description, is_active) VALUES (?,?,?,?,?)",
                (p["id"], p["name"], p["category"], p["description"], p.get("is_active", 1)))
            for a in p["aliases"]:
                conn.execute(
                    "INSERT INTO product_aliases (product_id, sku, alias, alias_normalized) VALUES (?,?,?,?)",
                    (p["id"], None, a, normalize(a)))
            for v in p["variants"]:
                conn.execute(
                    "INSERT INTO product_variants (sku, product_id, variant_name, color, size, price, is_active)"
                    " VALUES (?,?,?,?,?,?,1)",
                    (v["sku"], p["id"], v["variant_name"], v["color"], v["size"], v["price"]))
                conn.execute("INSERT INTO inventory (sku, quantity) VALUES (?,?)", (v["sku"], v["stock"]))
                for a in v.get("aliases", []):
                    conn.execute(
                        "INSERT INTO product_aliases (product_id, sku, alias, alias_normalized) VALUES (?,?,?,?)",
                        (p["id"], v["sku"], a, normalize(a)))
    return summary(conn)


def summary(conn) -> dict:
    q = lambda sql: conn.execute(sql).fetchone()[0]
    return {
        "products": q("SELECT COUNT(*) FROM products"),
        "skus": q("SELECT COUNT(*) FROM product_variants"),
        "categories": q("SELECT COUNT(DISTINCT category) FROM products"),
        "out_of_stock_skus": q("SELECT COUNT(*) FROM inventory WHERE quantity = 0"),
    }


def reset_and_seed(conn) -> dict:
    drop_all(conn)
    migrate(conn)
    return seed_catalog(conn)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Seed dữ liệu mock cho shop DB")
    ap.add_argument("--db", help="đường dẫn DB (mặc định data/shop.db hoặc biến SHOP_DB_PATH)")
    ap.add_argument("--reset", action="store_true", help="xóa sạch và tạo lại")
    args = ap.parse_args(argv)

    conn = connect(args.db)
    if args.reset:
        result = reset_and_seed(conn)
        print("Đã reset và seed:", result)
        return
    migrate(conn)
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]:
        print("DB đã có dữ liệu. Dùng --reset để tạo lại.")
        return
    print("Đã seed:", seed_catalog(conn))


if __name__ == "__main__":
    main()
