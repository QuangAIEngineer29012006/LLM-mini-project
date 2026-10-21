import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from database.shop_db.db import connect


SHIPPING = {"recipient_name": "Khách Demo", "phone": "0912345678", "address": "12 Đường Mẫu, Phường Mẫu, Quận 7"}
DELIVERY_TEXT = "Tên Khách Demo, SĐT 0912345678, giao về 12 Đường Mẫu, Phường Mẫu, Quận 7"


class BackendTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = self.temp.name + "/test.db"
        self.app = create_app(Settings(db_path=self.path, request_limit=10000, session_limit=1000, chat_limit=1000))
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.headers = self.session()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def session(self):
        result = self.client.post("/api/session")
        self.assertEqual(result.status_code, 201)
        return {"Authorization": "Bearer " + result.json()["token"]}

    def post_chat(self, message, headers=None, key=None):
        h = dict(headers or self.headers)
        if key:
            h["Idempotency-Key"] = key
        return self.client.post("/api/chat", headers=h, json={"message": message})

    def draft(self, sku="TSH-BLK-M", headers=None):
        h = headers or self.headers
        added = self.client.post("/api/cart/items", headers=h, json={"sku": sku, "quantity": 1})
        self.assertEqual(added.status_code, 200, added.text)
        result = self.client.post("/api/orders", headers=h, json={"shipping": SHIPPING})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def scalar(self, sql, params=()):
        conn = connect(self.path)
        try:
            return conn.execute(sql, params).fetchone()[0]
        finally:
            conn.close()
