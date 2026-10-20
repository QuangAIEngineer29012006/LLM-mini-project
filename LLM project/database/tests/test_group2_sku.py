import unittest

from shop_db import catalog_service as cat
from shop_db import order_service as orders
from shop_db.errors import ItemNotFound, SkuNotFound, ValidationError
from tests.helpers import CTX, DBTestCase


class SkuNotFoundTests(DBTestCase):
    BAD_SKUS = ["NOPE-1", "TSH-BLK-XL", "'; DROP TABLE orders;--", "", "   ", "A" * 80]

    def test_catalog_lookup(self):
        for sku in self.BAD_SKUS:
            with self.assertRaises(SkuNotFound, msg=repr(sku)):
                cat.get_variant(self.conn, sku)

    def test_availability_never_raises(self):
        for sku in self.BAD_SKUS + [None, 123, ["TSH-BLK-M"]]:
            self.assertEqual(cat.check_availability(self.conn, sku, 1)["reason"], "sku_not_found", repr(sku))

    def test_create_cart_with_unknown_sku_rolls_back(self):
        with self.assertRaises(SkuNotFound):
            orders.create_cart(self.conn, CTX, "u1", [{"sku": "TSH-BLK-M", "quantity": 1},
                                                      {"sku": "TSH-BLK-XXL", "quantity": 1}])
        self.assertEqual((self.count("orders"), self.count("order_items"), self.count("audit_logs")), (0, 0, 0))

    def test_inactive_product_is_not_orderable(self):
        with self.assertRaises(SkuNotFound):
            orders.create_cart(self.conn, CTX, "u1", [{"sku": "JKT-NVY-L", "quantity": 1}])

    def test_sku_deactivated_after_adding_blocks_submit(self):
        o = orders.create_cart(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 1}])
        self.conn.execute("UPDATE product_variants SET is_active = 0 WHERE sku = 'CAP-BLK-F'")
        with self.assertRaises(SkuNotFound):
            orders.submit_order(self.conn, CTX, o["id"],
                                {"customer_name": "Lê B", "phone": "0987654321", "address": "5 Láng Hạ, Hà Nội"})

    def test_item_operations_on_missing_line(self):
        o = orders.create_cart(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 1}])
        with self.assertRaises(ItemNotFound):
            orders.set_item_quantity(self.conn, CTX, o["id"], "CAP-NVY-F", 2)
        with self.assertRaises(ItemNotFound):
            orders.remove_item(self.conn, CTX, o["id"], "CAP-NVY-F")
        with self.assertRaises(SkuNotFound):
            orders.add_item(self.conn, CTX, o["id"], "CAP-RED-F", 1)

    def test_malformed_input_is_rejected(self):
        for items in ("TSH-BLK-M", [{"sku": "TSH-BLK-M"}], [{"sku": "TSH-BLK-M", "quantity": "2"}],
                      [{"sku": "TSH-BLK-M", "quantity": 0}], [{"sku": "TSH-BLK-M", "quantity": 1.5}],
                      [{"sku": "TSH-BLK-M", "quantity": True}], [{"sku": "TSH-BLK-M", "quantity": 100}]):
            with self.assertRaises(ValidationError, msg=repr(items)):
                orders.create_cart(self.conn, CTX, "u1", items)
        self.assertEqual(self.count("orders"), 0)


if __name__ == "__main__":
    unittest.main()
