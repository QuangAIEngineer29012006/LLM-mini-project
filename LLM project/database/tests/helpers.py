import unittest

from shop_db.audit_service import Ctx
from shop_db.db import connect
from shop_db.seed import reset_and_seed

CTX = Ctx("customer", "cust-1", "req-test")
STAFF = Ctx("staff", "staff-1", "req-staff")
DELIVERY = {"customer_name": "Nguyễn Văn A", "phone": "0912345678", "address": "12 Phố Huế, Hai Bà Trưng, Hà Nội"}


class DBTestCase(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        reset_and_seed(self.conn)

    def tearDown(self):
        self.conn.close()

    def stock(self, sku):
        return self.conn.execute("SELECT quantity FROM inventory WHERE sku = ?", (sku,)).fetchone()[0]

    def count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
