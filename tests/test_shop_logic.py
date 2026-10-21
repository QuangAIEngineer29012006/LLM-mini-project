"""Test logic thuần + mock giỏ hàng (không cần streamlit). Chạy: python -m unittest discover -s tests -t ."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "dev_stubs")]  # dev_stubs chỉ có khi chạy riêng; ghép rồi thì bỏ qua

from api_client import ApiError  # noqa: E402
from mock_shop import CATALOG, MockShopClient  # noqa: E402
from shop_logic import (  # noqa: E402
    MAX_QTY, chunk, filter_products, max_selectable, normalize, pick_default_variant,
    price_text, stock_label, variant_option_label,
)


class LogicTests(unittest.TestCase):
    def test_normalize_and_filter(self):
        self.assertEqual(normalize("Áo Thun Đen"), "ao thun den")
        products = [
            {"name": "Áo thun basic", "category": "apparel"},
            {"name": "Cà phê rang xay", "category": "food"},
        ]
        self.assertEqual(len(filter_products(products, query="ao thun")), 1)
        self.assertEqual(len(filter_products(products, category="food")), 1)
        self.assertEqual(len(filter_products(products)), 2)
        self.assertEqual(filter_products(products, query="xyz"), [])

    def test_stock_and_quantity_helpers(self):
        self.assertEqual(stock_label(0), "Hết hàng")
        self.assertIn("Sắp hết", stock_label(3))
        self.assertTrue(stock_label(50).startswith("Còn hàng"))
        self.assertEqual(max_selectable(0), 1)
        self.assertEqual(max_selectable(7), 7)
        self.assertEqual(max_selectable(1000), MAX_QTY)

    def test_labels_and_default_variant(self):
        fmt = lambda v: f"{v}đ"
        self.assertEqual(price_text({"price_from": 5, "price_to": 5}, fmt), "5đ")
        self.assertEqual(price_text({"price_from": 5, "price_to": 9}, fmt), "Từ 5đ")
        out = {"sku": "A", "label": "Đen", "unit_price": 1, "stock": 0}
        ok = {"sku": "B", "label": "Xanh", "unit_price": 1, "stock": 2}
        self.assertTrue(variant_option_label(out, fmt).endswith("Hết hàng"))
        self.assertEqual(pick_default_variant([out, ok]), "B")
        self.assertEqual(pick_default_variant([out]), "A")
        self.assertIsNone(pick_default_variant([]))

    def test_chunk(self):
        self.assertEqual(chunk([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])

    def test_catalog_meets_requirements(self):
        self.assertGreaterEqual(len(CATALOG), 10)
        self.assertGreaterEqual(len({v["category"] for v in CATALOG.values()}), 3)
        self.assertTrue(any(v["stock"] == 0 for v in CATALOG.values()))


class MockCartTests(unittest.TestCase):
    def setUp(self):
        self.c = MockShopClient()

    def test_list_and_detail(self):
        products = self.c.list_products()
        self.assertEqual(len(products), 9)
        detail = self.c.get_product("tshirt")
        self.assertEqual(len(detail["variants"]), 3)
        with self.assertRaises(ApiError) as ctx:
            self.c.get_product("nope")
        self.assertEqual(ctx.exception.status, 404)

    def test_add_merge_update_remove_total_from_server(self):
        self.c.add_to_cart("TSHIRT-BLU-M", 2)
        cart = self.c.add_to_cart("TSHIRT-BLU-M", 1)
        self.assertEqual(cart["items"][0]["quantity"], 3)
        self.assertEqual(cart["total"], 3 * 199000)
        cart = self.c.update_cart_item("TSHIRT-BLU-M", 5)
        self.assertEqual(cart["total"], 5 * 199000)
        cart = self.c.remove_cart_item("TSHIRT-BLU-M")
        self.assertEqual(cart["items"], [])
        self.assertEqual(cart["total"], 0)

    def test_out_of_stock_and_over_stock(self):
        with self.assertRaises(ApiError) as ctx:
            self.c.add_to_cart("TSHIRT-BLK-M", 1)  # tồn 0
        self.assertEqual((ctx.exception.status, ctx.exception.code), (409, "out_of_stock"))
        self.c.add_to_cart("TSHIRT-BLU-L", 2)  # tồn 3
        with self.assertRaises(ApiError):
            self.c.add_to_cart("TSHIRT-BLU-L", 2)  # cộng dồn vượt tồn
        self.assertEqual(self.c.get_cart()["items"][0]["quantity"], 2)  # giỏ không đổi
        with self.assertRaises(ApiError):
            self.c.update_cart_item("TSHIRT-BLU-L", 4)

    def test_invalid_input_rejected(self):
        for bad in (0, -1, 1.5, "2", None, True, MAX_QTY + 1):
            with self.assertRaises(ApiError) as ctx:
                self.c.add_to_cart("TSHIRT-BLU-M", bad)
            self.assertEqual(ctx.exception.status, 422)
        with self.assertRaises(ApiError) as ctx:
            self.c.add_to_cart("FAKE-SKU", 1)
        self.assertEqual(ctx.exception.status, 404)
        with self.assertRaises(ApiError):
            self.c.update_cart_item("TSHIRT-BLU-M", 1)  # chưa có trong giỏ
        with self.assertRaises(ApiError):
            self.c.remove_cart_item("TSHIRT-BLU-M")


if __name__ == "__main__":
    unittest.main()
