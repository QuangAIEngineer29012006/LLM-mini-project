import sqlite3
import unittest
from unittest import mock

from shop_db import order_service as orders
from shop_db import audit_service
from shop_db.db import connect, latest_version, migrate, transaction
from shop_db.errors import ValidationError
from tests.helpers import CTX, DELIVERY, DBTestCase


class RelationTests(DBTestCase):
    def test_foreign_keys_enabled(self):
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_cannot_delete_variant_used_by_order(self):
        orders.create_cart(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 1}])
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM product_variants WHERE sku = 'CAP-BLK-F'")

    def test_deleting_order_cascades_items_but_audit_blocks_it(self):
        o = orders.create_cart(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 1}])
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM orders WHERE id = ?", (o["id"],))
        self.assertEqual(self.count("order_items"), 1)

    def test_deleting_unaudited_order_cascades_items(self):
        oid = self.conn.execute("INSERT INTO orders (owner_id, source, status) VALUES ('u','web','cart')").lastrowid
        self.conn.execute("INSERT INTO order_items (order_id, sku, product_name, variant_name, quantity, unit_price,"
                          " line_total) VALUES (?, 'CAP-BLK-F', 'n', 'v', 1, 1, 1)", (oid,))
        self.conn.execute("DELETE FROM orders WHERE id = ?", (oid,))
        self.assertEqual(self.count("order_items"), 0)

    def test_deleting_product_cascades_to_variants_inventory_aliases(self):
        self.conn.execute("DELETE FROM products WHERE id = 7")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM product_variants WHERE product_id = 7").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM inventory WHERE sku = 'JKT-NVY-L'").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM product_aliases WHERE product_id = 7").fetchone()[0], 0)

    def test_check_constraints(self):
        bad = [
            "INSERT INTO orders (owner_id, source, status) VALUES ('u', 'fax', 'cart')",
            "INSERT INTO orders (owner_id, source, status) VALUES ('u', 'web', 'shipped')",
            "INSERT INTO product_variants (sku, product_id, variant_name, price) VALUES ('X-1', 1, 'v', -5)",
            "INSERT INTO audit_logs (actor_type, actor_id, action) VALUES ('alien', 'x', 'a')",
            "INSERT INTO conversation_messages (conversation_id, role, content) VALUES ('x', 'user', 'hi')",
        ]
        for sql in bad:
            with self.assertRaises(sqlite3.IntegrityError, msg=sql):
                self.conn.execute(sql)

    def test_unique_item_per_order(self):
        o = orders.create_cart(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 1}])
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO order_items (order_id, sku, product_name, variant_name, quantity,"
                              " unit_price, line_total) VALUES (?, 'CAP-BLK-F', 'n', 'v', 1, 1, 1)", (o["id"],))


class TransactionTests(DBTestCase):
    def test_audit_failure_rolls_back_the_whole_order(self):
        with mock.patch("shop_db.order_service.log_event", side_effect=RuntimeError("audit down")):
            with self.assertRaises(RuntimeError):
                orders.create_cart(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 1}])
        self.assertEqual((self.count("orders"), self.count("order_items")), (0, 0))
        self.assertFalse(self.conn.in_transaction)

    def test_failure_midway_through_draft_rolls_back_everything(self):
        with mock.patch("shop_db.status_service.log_event", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                orders.create_draft_order(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 1}], DELIVERY)
        self.assertEqual((self.count("orders"), self.count("order_items"), self.count("audit_logs")), (0, 0, 0))

    def test_failed_confirm_leaves_stock_and_status_untouched(self):
        o = orders.create_draft_order(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 2}], DELIVERY)
        from shop_db.status_service import change_status
        with mock.patch("shop_db.status_service.log_event", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                change_status(self.conn, CTX, o["id"], "confirmed")
        self.assertEqual(self.stock("CAP-BLK-F"), 15)
        self.assertEqual(orders.get_order(self.conn, o["id"])["status"], "pending_confirmation")

    def test_nested_transaction_shares_outer_one(self):
        with self.assertRaises(ValidationError):
            with transaction(self.conn):
                orders.create_cart(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 1}])
                self.assertTrue(self.conn.in_transaction)
                raise ValidationError("hủy cả khối")
        self.assertEqual(self.count("orders"), 0)

    def test_two_connections_do_not_see_uncommitted_data(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.db")
            a, b = connect(path), connect(path)
            migrate(a)
            a.execute("BEGIN IMMEDIATE")
            a.execute("INSERT INTO products (id, name, category) VALUES (1, 'x', 'y')")
            self.assertEqual(b.execute("SELECT COUNT(*) FROM products").fetchone()[0], 0)
            a.execute("COMMIT")
            self.assertEqual(b.execute("SELECT COUNT(*) FROM products").fetchone()[0], 1)
            a.close(); b.close()


class MigrationUpgradeTests(unittest.TestCase):
    def test_upgrade_v1_to_latest_keeps_data(self):
        conn = connect(":memory:")
        self.assertEqual(migrate(conn, target_version=1), 1)
        conn.execute("INSERT INTO orders (owner_id, source, status) VALUES ('old-user', 'web', 'cart')")
        self.assertEqual(migrate(conn), latest_version())
        row = conn.execute("SELECT owner_id, idempotency_key FROM orders").fetchone()
        self.assertEqual((row["owner_id"], row["idempotency_key"]), ("old-user", None))
        conn.execute("INSERT INTO conversations (id, owner_id) VALUES ('c1', 'old-user')")
        self.assertEqual(migrate(conn), latest_version())


if __name__ == "__main__":
    unittest.main()
