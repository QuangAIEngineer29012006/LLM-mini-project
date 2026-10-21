import hashlib
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from backend.storage import initialize
from backend.main import RateLimiter
from backend.errors import ApiProblem
from database.shop_db.db import connect

from tests.backend_helpers import BackendTestCase, SHIPPING


class ApiTests(BackendTestCase):
    def test_catalog_contract_and_real_database_prices(self):
        products = self.client.get("/api/products").json()["products"]
        self.assertEqual(len(products), 6)
        self.assertGreaterEqual(sum(len(p["variants"]) for p in products), 10)
        self.assertEqual(len({p["category"] for p in products}), 3)
        item = self.client.get("/api/products/1").json()
        self.assertEqual(item["price_from"], 150000)
        self.assertIn("stock", item["variants"][0])
        self.assertEqual(self.client.get("/api/products/7").status_code, 404)

    def test_cart_merge_edit_remove_checkout(self):
        self.assertEqual(self.client.get("/api/cart", headers=self.headers).json()["items"], [])
        for qty in (1, 2):
            result = self.client.post("/api/cart/items", headers=self.headers, json={"sku": "TSH-BLK-M", "quantity": qty})
        cart = result.json()
        self.assertEqual(cart["total"], 450000)
        iid = cart["items"][0]["item_id"]
        changed = self.client.patch(f"/api/cart/items/{iid}", headers=self.headers, json={"quantity": 2}).json()
        self.assertEqual(changed["total"], 300000)
        removed = self.client.delete(f"/api/cart/items/{iid}", headers=self.headers).json()
        self.assertEqual(removed["total"], 0)
        order = self.draft()
        self.assertEqual(order["status"], "pending_confirmation")
        self.assertEqual(self.scalar("SELECT quantity FROM inventory WHERE sku='TSH-BLK-M'"), 25)
        self.assertEqual(self.client.get("/api/cart", headers=self.headers).json()["items"], [])

    def test_authentication_expiry_revocation_and_hashed_storage(self):
        for path in ("/api/cart", "/api/orders"):
            self.assertEqual(self.client.get(path).status_code, 401)
        token = self.headers["Authorization"].split()[1]
        stored = self.scalar("SELECT token_hash FROM api_sessions LIMIT 1")
        self.assertEqual(stored, hashlib.sha256(token.encode()).hexdigest())
        other = self.session()
        with patch("backend.storage.time.time", return_value=99999999999):
            self.assertEqual(self.client.get("/api/cart", headers=other).status_code, 401)
        self.assertEqual(self.client.delete("/api/session", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get("/api/orders", headers=self.headers).status_code, 401)

    def test_other_session_cannot_read_or_edit_order_or_cart(self):
        order = self.draft()
        outsider = self.session()
        oid, iid = order["order_id"], order["items"][0]["item_id"]
        self.assertEqual(self.client.get(f"/api/orders/{oid}", headers=outsider).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/orders/{oid}/items/{iid}", headers=outsider, json={"quantity": 2}).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/cart/items/{iid}", headers=outsider, json={"quantity": 2}).status_code, 404)
        self.assertEqual(self.client.get("/api/orders", headers=outsider).json()["orders"], [])

    def test_forged_fields_and_bad_quantities_rejected(self):
        for quantity in (True, "2", 0, -1, 1.5, 100):
            r = self.client.post("/api/cart/items", headers=self.headers, json={"sku": "TSH-BLK-M", "quantity": quantity})
            self.assertEqual(r.status_code, 422)
        for field in ("price", "unit_price", "stock", "total", "owner_id", "status", "role"):
            r = self.client.post("/api/cart/items", headers=self.headers, json={"sku": "TSH-BLK-M", "quantity": 1, field: 1})
            self.assertEqual(r.status_code, 422)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM orders"), 0)
        order = self.draft()
        result = self.client.post("/api/orders", headers=self.headers, json={"shipping": SHIPPING, "status": "confirmed", "total": 1})
        self.assertEqual(result.status_code, 422)
        self.assertEqual(self.scalar("SELECT total_amount FROM orders WHERE status='pending_confirmation'"), 150000)
        self.assertEqual(order["status"], "pending_confirmation")

    def test_stock_failure_rolls_back_empty_cart_creation(self):
        for sku, qty in (("TSH-WHT-M", 1), ("SNK-WHT-41", 3), ("NOT-A-SKU", 1)):
            result = self.client.post("/api/cart/items", headers=self.headers, json={"sku": sku, "quantity": qty})
            self.assertIn(result.status_code, (404, 409))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM orders"), 0)

    def test_checkout_idempotency_conflict_and_concurrent_requests(self):
        self.client.post("/api/cart/items", headers=self.headers, json={"sku": "TSH-BLK-M", "quantity": 1})
        headers = {**self.headers, "Idempotency-Key": "checkout-test-001"}
        def checkout(_):
            return self.client.post("/api/orders", headers=headers, json={"shipping": SHIPPING})
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(checkout, range(4)))
        self.assertTrue(all(r.status_code == 200 for r in results), [r.text for r in results])
        self.assertEqual(len({r.json()["order_id"] for r in results}), 1)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM orders"), 1)
        conflict = self.client.post("/api/orders", headers=headers, json={"shipping": {**SHIPPING, "address": "99 Đường Mẫu Khác, Quận 7"}})
        self.assertEqual(conflict.status_code, 409)

    def test_variant_change_checks_product_and_rolls_back(self):
        order = self.draft()
        path = f"/api/orders/{order['order_id']}/items/{order['items'][0]['item_id']}"
        for sku, expected in (("TSH-WHT-M", 409), ("CAP-BLK-F", 422)):
            self.assertEqual(self.client.patch(path, headers=self.headers, json={"sku": sku}).status_code, expected)
        self.assertEqual(self.scalar("SELECT sku FROM order_items LIMIT 1"), "TSH-BLK-M")
        changed = self.client.patch(path, headers=self.headers, json={"sku": "TSH-BLK-L", "quantity": 2})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["items"][0]["sku"], "TSH-BLK-L")
        self.assertEqual(changed.json()["total"], 300000)

    def test_state_lock_audit_and_restart_preserve_data(self):
        order = self.draft()
        conn = connect(self.path)
        conn.execute("UPDATE orders SET status='confirmed' WHERE id=1")
        conn.close()
        path = f"/api/orders/{order['order_id']}/items/{order['items'][0]['item_id']}"
        self.assertEqual(self.client.patch(path, headers=self.headers, json={"quantity": 2}).status_code, 409)
        initialize(self.path)
        self.assertEqual(self.client.get("/api/orders", headers=self.headers).json()["orders"][0]["order_id"], order["order_id"])
        audit = self.scalar("SELECT group_concat(details) FROM audit_logs")
        for private in (SHIPPING["phone"], SHIPPING["address"], SHIPPING["recipient_name"]):
            self.assertNotIn(private, audit)

    def test_error_envelope_limits_and_rate_limit(self):
        self.assertEqual(self.client.post("/api/chat", headers=self.headers, json={"message": "x" * 501}).status_code, 422)
        self.assertEqual(self.client.post("/api/chat", headers=self.headers, content=b"x" * 17000).status_code, 413)
        bad = self.client.post("/api/chat", headers=self.headers, content="{")
        self.assertEqual(bad.status_code, 422)
        self.assertIn("request_id", bad.json())
        self.assertNotIn("Traceback", bad.text)
        self.assertEqual(self.client.get("/api/absent").json()["error"]["code"], "not_found")
        limiter = RateLimiter()
        limiter.check("chat", "session", 1)
        with self.assertRaises(ApiProblem) as error:
            limiter.check("chat", "session", 1)
        self.assertEqual(error.exception.status, 429)
        with patch("backend.main.time.monotonic", return_value=999999999999):
            limiter.check("chat", "session", 1)
