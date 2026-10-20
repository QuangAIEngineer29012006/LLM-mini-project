import unittest

from shop_db import catalog_service as cat
from tests.helpers import DBTestCase


class ResolveTests(DBTestCase):
    def test_matched_exact_variant(self):
        r = cat.resolve_product(self.conn, "cho mình áo thun đen size M")
        self.assertEqual((r["status"], r["sku"]), ("matched", "TSH-BLK-M"))
        self.assertEqual(r["variant"]["price"], 150000)

    def test_matched_by_sku_and_variant_alias(self):
        self.assertEqual(cat.resolve_product(self.conn, "SNK-WHT-41")["sku"], "SNK-WHT-41")
        self.assertEqual(cat.resolve_product(self.conn, "giày trắng 41")["sku"], "SNK-WHT-41")

    def test_matched_when_product_has_single_variant_choice(self):
        r = cat.resolve_product(self.conn, "balo màu xám")
        self.assertEqual((r["status"], r["sku"]), ("matched", "BAG-GRY-15"))

    def test_matched_does_not_hide_out_of_stock(self):
        r = cat.resolve_product(self.conn, "áo thun trắng size M")
        self.assertEqual((r["status"], r["sku"], r["variant"]["in_stock"]), ("matched", "TSH-WHT-M", False))

    def test_variant_unspecified(self):
        r = cat.resolve_product(self.conn, "áo thun")
        self.assertEqual((r["status"], r["reason"]), ("ambiguous", "variant_unspecified"))
        self.assertEqual(len(r["candidates"]), 4)
        self.assertEqual(r["product"]["product_id"], 1)

    def test_variant_ambiguous(self):
        r = cat.resolve_product(self.conn, "áo thun đen")
        self.assertEqual((r["status"], r["reason"]), ("ambiguous", "variant_ambiguous"))
        self.assertEqual({c["sku"] for c in r["candidates"]}, {"TSH-BLK-M", "TSH-BLK-L"})

    def test_multiple_products(self):
        r = cat.resolve_product(self.conn, "áo")
        self.assertEqual((r["status"], r["reason"]), ("ambiguous", "multiple_products"))
        self.assertGreaterEqual(len(r["candidates"]), 2)
        self.assertIsNone(r["sku"])

    def test_no_match(self):
        for q in ("xe máy", "áo khoác dù", "", "   ", None, 123):
            r = cat.resolve_product(self.conn, q)
            self.assertEqual((r["status"], r["sku"], r["candidates"]), ("no_match", None, []), repr(q))


if __name__ == "__main__":
    unittest.main()
