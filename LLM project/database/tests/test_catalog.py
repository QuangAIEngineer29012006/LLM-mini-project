import unittest

from shop_db import catalog_service as cat
from shop_db.errors import ProductNotFound, SkuNotFound, ValidationError
from tests.helpers import DBTestCase


class CatalogTests(DBTestCase):
    def test_search_accent_insensitive_and_alias(self):
        for q in ("áo thun", "ao thun", "AO PHONG", "cho mình hỏi giá áo phông"):
            top = cat.search_products(self.conn, q)[0]
            self.assertEqual(top["name"], "Áo thun basic cotton", q)

    def test_search_matches_variant_attributes(self):
        top = cat.search_products(self.conn, "áo thun đen size M")[0]
        self.assertEqual(top["product_id"], 1)
        self.assertEqual(top["matched_skus"], ["TSH-BLK-M"])

    def test_search_by_sku_and_category(self):
        self.assertEqual(cat.search_products(self.conn, "snk-wht-41")[0]["matched_skus"], ["SNK-WHT-41"])
        names = {r["category"] for r in cat.search_products(self.conn, "phụ kiện")}
        self.assertEqual(names, {"Phụ kiện"})

    def test_search_hides_inactive_and_unknown(self):
        self.assertEqual(cat.search_products(self.conn, "áo khoác dù"), [])
        self.assertEqual(cat.search_products(self.conn, "xe máy"), [])
        self.assertEqual(cat.search_products(self.conn, "   "), [])

    def test_ambiguous_query_returns_several_products(self):
        self.assertGreaterEqual(len(cat.search_products(self.conn, "áo")), 2)

    def test_price_stock_and_detail(self):
        self.assertEqual(cat.get_price(self.conn, "tsh-blk-m"), 150000)
        self.assertEqual(cat.get_stock(self.conn, "TSH-WHT-M"), 0)
        p = cat.get_product(self.conn, 1)
        self.assertEqual(len(p["variants"]), 4)
        self.assertTrue(p["in_stock"])
        self.assertEqual((p["price_min"], p["price_max"]), (150000, 150000))

    def test_list_products_and_categories(self):
        self.assertEqual(cat.list_categories(self.conn), ["Giày", "Phụ kiện", "Áo"])
        self.assertEqual(len(cat.list_products(self.conn)), 6)
        self.assertEqual({p["category"] for p in cat.list_products(self.conn, category="giay")}, {"Giày"})
        with self.assertRaises(ValidationError):
            cat.list_products(self.conn, limit=0)

    def test_check_availability_reasons(self):
        r = cat.check_availability
        self.assertTrue(r(self.conn, "TSH-BLK-M", 25)["ok"])
        self.assertEqual(r(self.conn, "TSH-BLK-M", 26)["reason"], "insufficient_stock")
        self.assertEqual(r(self.conn, "TSH-BLK-M", 26)["available"], 25)
        self.assertEqual(r(self.conn, "TSH-WHT-M", 1)["reason"], "out_of_stock")
        self.assertEqual(r(self.conn, "NOPE-1", 1)["reason"], "sku_not_found")
        self.assertEqual(r(self.conn, "TSH-BLK-M", 0)["reason"], "invalid_quantity")
        self.assertEqual(r(self.conn, "TSH-BLK-M", True)["reason"], "invalid_quantity")
        self.assertEqual(r(self.conn, None, 1)["reason"], "sku_not_found")

    def test_check_items_merges_duplicates_and_totals(self):
        res = cat.check_items(self.conn, [{"sku": "TSH-BLK-M", "quantity": 1}, {"sku": "tsh-blk-m", "quantity": 1},
                                          {"sku": "CAP-BLK-F", "quantity": 1}])
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["results"]), 2)
        self.assertEqual(res["total_amount"], 2 * 150000 + 90000)
        bad = cat.check_items(self.conn, [{"sku": "TSH-BLK-M", "quantity": 1}, {"sku": "TSH-WHT-M", "quantity": 1}])
        self.assertFalse(bad["ok"])
        self.assertIsNone(bad["total_amount"])

    def test_not_found_errors(self):
        with self.assertRaises(SkuNotFound):
            cat.get_variant(self.conn, "JKT-NVY-L")
        with self.assertRaises(ProductNotFound):
            cat.get_product(self.conn, 7)


if __name__ == "__main__":
    unittest.main()
