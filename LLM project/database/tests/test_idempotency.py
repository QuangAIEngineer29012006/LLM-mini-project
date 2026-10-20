import os
import tempfile
import threading
import unittest

from shop_db import audit_service as audit
from shop_db import order_service as orders
from shop_db.db import connect, migrate
from shop_db.errors import IdempotencyConflict, InsufficientStock, ValidationError
from shop_db.seed import seed_catalog
from tests.helpers import CTX, DELIVERY, DBTestCase

ITEMS = [{"sku": "TSH-BLK-M", "quantity": 2}, {"sku": "CAP-BLK-F", "quantity": 1}]


class IdempotencyTests(DBTestCase):
    def test_double_submit_creates_one_order(self):
        a = orders.create_draft_order(self.conn, CTX, "u1", ITEMS, DELIVERY, idempotency_key="web-click-0001")
        b = orders.create_draft_order(self.conn, CTX, "u1", ITEMS, DELIVERY, idempotency_key="web-click-0001")
        self.assertEqual((a["replayed"], b["replayed"]), (False, True))
        self.assertEqual(a["id"], b["id"])
        self.assertEqual((self.count("orders"), self.count("order_items")), (1, 2))
        actions = [e["action"] for e in audit.list_events(self.conn, order_id=a["id"])]
        self.assertEqual(actions.count("duplicate_request_ignored"), 1)
        self.assertEqual(actions.count("status_changed"), 1)

    def test_item_order_and_duplicate_skus_do_not_matter(self):
        a = orders.create_draft_order(self.conn, CTX, "u1", ITEMS, DELIVERY, idempotency_key="key-aaaa-1111")
        reordered = [{"sku": "cap-blk-f", "quantity": 1}, {"sku": "TSH-BLK-M", "quantity": 1},
                     {"sku": "TSH-BLK-M", "quantity": 1}]
        b = orders.create_draft_order(self.conn, CTX, "u1", reordered, DELIVERY, idempotency_key="key-aaaa-1111")
        self.assertEqual(a["id"], b["id"])

    def test_same_key_different_payload_conflicts(self):
        orders.create_draft_order(self.conn, CTX, "u1", ITEMS, DELIVERY, idempotency_key="key-bbbb-2222")
        other = [{"sku": "TSH-BLK-M", "quantity": 3}]
        with self.assertRaises(IdempotencyConflict):
            orders.create_draft_order(self.conn, CTX, "u1", other, DELIVERY, idempotency_key="key-bbbb-2222")
        with self.assertRaises(IdempotencyConflict):
            orders.create_cart(self.conn, CTX, "u1", ITEMS, idempotency_key="key-bbbb-2222")
        self.assertEqual(self.count("orders"), 1)

    def test_key_is_scoped_per_owner(self):
        a = orders.create_draft_order(self.conn, CTX, "ua", ITEMS, DELIVERY, idempotency_key="shared-key-01")
        b = orders.create_draft_order(self.conn, CTX, "ub", ITEMS, DELIVERY, idempotency_key="shared-key-01")
        self.assertNotEqual(a["id"], b["id"])

    def test_no_key_means_no_dedup(self):
        orders.create_draft_order(self.conn, CTX, "u1", ITEMS, DELIVERY)
        orders.create_draft_order(self.conn, CTX, "u1", ITEMS, DELIVERY)
        self.assertEqual(self.count("orders"), 2)

    def test_cart_replay(self):
        a = orders.create_cart(self.conn, CTX, "u1", ITEMS, source="chat", idempotency_key="chat-msg-0001")
        b = orders.create_cart(self.conn, CTX, "u1", ITEMS, source="chat", idempotency_key="chat-msg-0001")
        self.assertEqual((a["id"], b["replayed"]), (b["id"], True))

    def test_failed_attempt_does_not_burn_the_key(self):
        too_many = [{"sku": "HOD-GRY-L", "quantity": 4}]
        with self.assertRaises(InsufficientStock):
            orders.create_draft_order(self.conn, CTX, "u1", too_many, DELIVERY, idempotency_key="retry-key-001")
        self.assertEqual(self.count("orders"), 0)
        ok = orders.create_draft_order(self.conn, CTX, "u1", too_many[:0] or [{"sku": "HOD-GRY-L", "quantity": 3}],
                                       DELIVERY, idempotency_key="retry-key-001")
        self.assertFalse(ok["replayed"])

    def test_invalid_keys_rejected(self):
        for bad in ("", "short", "có dấu cách và tiếng Việt", "x" * 101, 12345678, "a b c d e f g h"):
            with self.assertRaises(ValidationError, msg=repr(bad)):
                orders.create_cart(self.conn, CTX, "u1", ITEMS, idempotency_key=bad)

    def test_unique_index_is_last_line_of_defense(self):
        orders.create_cart(self.conn, CTX, "u1", [], idempotency_key="direct-key-01")
        with self.assertRaises(Exception):
            self.conn.execute("INSERT INTO orders (owner_id, source, status, idempotency_key)"
                              " VALUES ('u1', 'web', 'cart', 'direct-key-01')")


class IdempotencyConcurrencyTests(unittest.TestCase):
    def test_parallel_requests_same_key_create_one_order(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "race.db")
            setup = connect(path); migrate(setup); seed_catalog(setup); setup.close()
            results, errors = [], []

            def worker():
                conn = connect(path)
                try:
                    results.append(orders.create_draft_order(conn, CTX, "u1", ITEMS, DELIVERY,
                                                             idempotency_key="parallel-key-1")["id"])
                except Exception as e:
                    errors.append(e)
                finally:
                    conn.close()

            threads = [threading.Thread(target=worker) for _ in range(6)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            self.assertEqual(errors, [])
            self.assertEqual(len(set(results)), 1)
            check = connect(path)
            self.assertEqual(check.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 1)
            check.close()


if __name__ == "__main__":
    unittest.main()
