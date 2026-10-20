import unittest

from shop_db import order_service as orders
from shop_db.errors import InsufficientStock, OutOfStock
from shop_db.status_service import change_status
from tests.helpers import CTX, DELIVERY, DBTestCase


class InsufficientStockTests(DBTestCase):
    def test_create_cart_exceeds_stock_rolls_back(self):
        with self.assertRaises(InsufficientStock) as cm:
            orders.create_cart(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 1},
                                                      {"sku": "HOD-GRY-L", "quantity": 4}])
        self.assertEqual(cm.exception.details["available"], 3)
        self.assertEqual(cm.exception.code, "insufficient_stock")
        self.assertEqual((self.count("orders"), self.count("order_items"), self.count("audit_logs")), (0, 0, 0))

    def test_out_of_stock_variant(self):
        with self.assertRaises(OutOfStock) as cm:
            orders.create_cart(self.conn, CTX, "u1", [{"sku": "TSH-WHT-M", "quantity": 1}])
        self.assertEqual(cm.exception.code, "out_of_stock")
        self.assertEqual(self.count("orders"), 0)

    def test_add_item_counts_existing_quantity(self):
        o = orders.create_cart(self.conn, CTX, "u1", [{"sku": "HOD-GRY-L", "quantity": 2}])
        with self.assertRaises(InsufficientStock):
            orders.add_item(self.conn, CTX, o["id"], "HOD-GRY-L", 2)
        self.assertEqual(orders.get_order(self.conn, o["id"])["items"][0]["quantity"], 2)
        self.assertEqual(self.count("audit_logs"), 1)

    def test_set_quantity_over_stock_keeps_old_value(self):
        o = orders.create_cart(self.conn, CTX, "u1", [{"sku": "SNK-WHT-41", "quantity": 1}])
        with self.assertRaises(InsufficientStock):
            orders.set_item_quantity(self.conn, CTX, o["id"], "SNK-WHT-41", 3)
        self.assertEqual(orders.get_order(self.conn, o["id"])["total_amount"], 750000)

    def test_stock_taken_by_another_order_blocks_confirm(self):
        a = orders.create_draft_order(self.conn, CTX, "ua", [{"sku": "SNK-WHT-41", "quantity": 2}], DELIVERY)
        b = orders.create_draft_order(self.conn, CTX, "ub", [{"sku": "SNK-WHT-41", "quantity": 2}], DELIVERY)
        change_status(self.conn, CTX, a["id"], "confirmed")
        self.assertEqual(self.stock("SNK-WHT-41"), 0)
        with self.assertRaises(InsufficientStock) as cm:
            change_status(self.conn, CTX, b["id"], "confirmed")
        self.assertEqual(cm.exception.details["shortages"][0]["reason"], "out_of_stock")
        self.assertEqual(orders.get_order(self.conn, b["id"])["status"], "pending_confirmation")
        self.assertEqual(self.stock("SNK-WHT-41"), 0)

    def test_multi_item_confirm_is_atomic(self):
        o = orders.create_draft_order(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 2},
                                                             {"sku": "BAG-GRY-15", "quantity": 1}], DELIVERY)
        self.conn.execute("UPDATE inventory SET quantity = 0 WHERE sku = 'BAG-GRY-15'")
        with self.assertRaises(InsufficientStock):
            change_status(self.conn, CTX, o["id"], "confirmed")
        self.assertEqual(self.stock("CAP-BLK-F"), 15)
        self.assertEqual(orders.get_order(self.conn, o["id"])["status"], "pending_confirmation")

    def test_confirm_decrements_and_cancel_restores(self):
        o = orders.create_draft_order(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 5}], DELIVERY)
        self.assertEqual(self.stock("CAP-BLK-F"), 15)
        change_status(self.conn, CTX, o["id"], "confirmed")
        self.assertEqual(self.stock("CAP-BLK-F"), 10)
        change_status(self.conn, CTX, o["id"], "cancelled", reason="khách đổi ý")
        self.assertEqual(self.stock("CAP-BLK-F"), 15)


if __name__ == "__main__":
    unittest.main()
