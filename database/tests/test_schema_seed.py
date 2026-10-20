import os
import tempfile
import unittest

from shop_db.db import connect, latest_version, migrate
from shop_db.seed import reset_and_seed, seed_catalog
from tests.helpers import DBTestCase


class SchemaSeedTests(DBTestCase):
    def test_migrate_creates_all_tables_and_version(self):
        tables = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("products", "product_variants", "inventory", "product_aliases",
                  "orders", "order_items", "audit_logs"):
            self.assertIn(t, tables)
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], latest_version())

    def test_seed_meets_requirements(self):
        s = self.conn.execute(
            "SELECT COUNT(*) n, COUNT(DISTINCT p.category) c FROM product_variants v"
            " JOIN products p ON p.id = v.product_id WHERE v.is_active = 1 AND p.is_active = 1").fetchone()
        self.assertGreaterEqual(s["n"], 10)
        self.assertGreaterEqual(s["c"], 3)
        self.assertGreaterEqual(self.count("product_aliases"), 10)
        self.assertGreater(self.conn.execute("SELECT COUNT(*) FROM inventory WHERE quantity = 0").fetchone()[0], 0)

    def test_reset_is_repeatable(self):
        first = reset_and_seed(self.conn)
        second = reset_and_seed(self.conn)
        self.assertEqual(first, second)
        self.assertEqual(self.count("orders"), 0)

    def test_migrate_is_idempotent(self):
        before = self.count("products")
        self.assertEqual(migrate(self.conn), latest_version())
        self.assertEqual(self.count("products"), before)

    def test_constraints_reject_bad_data(self):
        with self.assertRaises(Exception):
            self.conn.execute("UPDATE inventory SET quantity = -1 WHERE sku = 'TSH-BLK-M'")
        with self.assertRaises(Exception):
            self.conn.execute("INSERT INTO order_items (order_id, sku, product_name, variant_name, quantity,"
                              " unit_price, line_total) VALUES (999, 'TSH-BLK-M', 'x', 'y', 1, 1, 1)")

    def test_fresh_file_db(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "new.db")
            conn = connect(path)
            migrate(conn)
            seed_catalog(conn)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM product_variants").fetchone()[0], 17)
            conn.close()


if __name__ == "__main__":
    unittest.main()
