import json
import sqlite3
import unittest

from shop_db import audit_service as audit
from shop_db import order_service as orders
from shop_db.errors import InvalidStatusTransition, OrderNotEditable, PriceChanged, ValidationError
from shop_db.status_service import change_status
from tests.helpers import CTX, DELIVERY, STAFF, DBTestCase


class SnapshotAuditTests(DBTestCase):
    def test_snapshot_survives_price_change(self):
        o = orders.create_cart(self.conn, CTX, "u1", [{"sku": "TSH-BLK-M", "quantity": 2}])
        self.assertEqual((o["items"][0]["unit_price"], o["total_amount"]), (150000, 300000))
        self.conn.execute("UPDATE product_variants SET price = 160000 WHERE sku = 'TSH-BLK-M'")
        again = orders.get_order(self.conn, o["id"])
        self.assertEqual((again["items"][0]["unit_price"], again["total_amount"]), (150000, 300000))

    def test_snapshot_keeps_names_after_rename(self):
        o = orders.create_cart(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 1}])
        self.conn.execute("UPDATE products SET name = 'Tên mới' WHERE id = 5")
        self.assertEqual(orders.get_order(self.conn, o["id"])["items"][0]["product_name"], "Nón lưỡi trai")

    def test_total_is_computed_server_side(self):
        o = orders.create_cart(self.conn, CTX, "u1", [{"sku": "TSH-BLK-M", "quantity": 2},
                                                      {"sku": "SNK-WHT-40", "quantity": 1}])
        self.assertEqual(o["total_amount"], 2 * 150000 + 750000)
        o = orders.set_item_quantity(self.conn, CTX, o["id"], "TSH-BLK-M", 1)
        self.assertEqual(o["total_amount"], 150000 + 750000)
        o = orders.remove_item(self.conn, CTX, o["id"], "SNK-WHT-40")
        self.assertEqual(o["total_amount"], 150000)

    def test_submit_reprices_but_confirm_refuses_silent_change(self):
        o = orders.create_cart(self.conn, CTX, "u1", [{"sku": "TSH-BLK-M", "quantity": 1}])
        self.conn.execute("UPDATE product_variants SET price = 170000 WHERE sku = 'TSH-BLK-M'")
        o = orders.submit_order(self.conn, CTX, o["id"], DELIVERY)
        self.assertEqual(o["total_amount"], 170000)
        self.conn.execute("UPDATE product_variants SET price = 180000 WHERE sku = 'TSH-BLK-M'")
        with self.assertRaises(PriceChanged) as cm:
            change_status(self.conn, CTX, o["id"], "confirmed")
        self.assertEqual(cm.exception.details["changes"][0]["new_price"], 180000)
        self.assertEqual(self.stock("TSH-BLK-M"), 25)
        o = orders.refresh_prices(self.conn, CTX, o["id"])
        self.assertEqual(o["total_amount"], 180000)
        self.assertEqual(change_status(self.conn, CTX, o["id"], "confirmed")["status"], "confirmed")

    def test_audit_trail_for_full_lifecycle(self):
        o = orders.create_cart(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 1}], source="chat")
        orders.add_item(self.conn, CTX, o["id"], "TSH-BLK-M", 1)
        orders.update_delivery(self.conn, CTX, o["id"], DELIVERY)
        change_status(self.conn, CTX, o["id"], "pending_confirmation")
        change_status(self.conn, STAFF, o["id"], "confirmed")
        change_status(self.conn, STAFF, o["id"], "cancelled", reason="hết xe giao")
        events = audit.list_events(self.conn, order_id=o["id"])
        self.assertEqual([e["action"] for e in events],
                         ["order_created", "item_added", "delivery_updated",
                          "status_changed", "status_changed", "status_changed"])
        self.assertEqual([(e["old_status"], e["new_status"]) for e in events if e["action"] == "status_changed"],
                         [("cart", "pending_confirmation"), ("pending_confirmation", "confirmed"),
                          ("confirmed", "cancelled")])
        self.assertEqual(events[0]["details"]["source"], "chat")
        self.assertEqual((events[-1]["actor_type"], events[-1]["actor_id"], events[-1]["request_id"]),
                         ("staff", "staff-1", "req-staff"))
        self.assertEqual(events[-1]["details"]["reason"], "hết xe giao")

    def test_audit_never_stores_personal_data(self):
        o = orders.create_draft_order(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 1}], DELIVERY)
        change_status(self.conn, CTX, o["id"], "cancelled", reason="gọi 0912 345 678 giúp mình, ở 12 Phố Huế")
        raw = json.dumps([e["details"] for e in audit.list_events(self.conn, order_id=o["id"])], ensure_ascii=False)
        for secret in ("0912345678", "0912 345 678", "Nguyễn Văn A", "Phố Huế, Hai Bà Trưng"):
            self.assertNotIn(secret, raw)

    def test_sanitize_rules(self):
        s = audit.sanitize({"password": "x", "Token": "abc", "address": "1 Đường A", "phone": "0912345678",
                            "note": "x" * 500, "nested": {"api_key": "k", "ok": 1}, "list": ["0987654321", "TSH-BLK-M"]})
        self.assertEqual(s["password"], "[REDACTED]")
        self.assertEqual(s["Token"], "[REDACTED]")
        self.assertEqual(s["address"], "[REDACTED]")
        self.assertEqual(s["phone"], "***678")
        self.assertEqual(len(s["note"]), 200)
        self.assertEqual(s["nested"], {"api_key": "[REDACTED]", "ok": 1})
        self.assertEqual(s["list"], ["***321", "TSH-BLK-M"])

    def test_audit_is_append_only(self):
        orders.create_cart(self.conn, CTX, "u1", [])
        with self.assertRaises(sqlite3.DatabaseError):
            self.conn.execute("UPDATE audit_logs SET action = 'x'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.conn.execute("DELETE FROM audit_logs")

    def test_invalid_ctx_and_transitions(self):
        with self.assertRaises(ValueError):
            audit.Ctx("hacker", "x")
        o = orders.create_cart(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 1}])
        with self.assertRaises(InvalidStatusTransition):
            change_status(self.conn, CTX, o["id"], "confirmed")
        with self.assertRaises(ValidationError) as cm:
            change_status(self.conn, CTX, o["id"], "pending_confirmation")
        self.assertEqual(cm.exception.details["missing"], ["customer_name", "phone", "address"])
        self.assertEqual(self.count("audit_logs"), 1)
        change_status(self.conn, CTX, o["id"], "cancelled")
        with self.assertRaises(OrderNotEditable):
            orders.add_item(self.conn, CTX, o["id"], "CAP-NVY-F", 1)
        with self.assertRaises(InvalidStatusTransition):
            change_status(self.conn, CTX, o["id"], "pending_confirmation")

    def test_delivery_validation_and_latest_order(self):
        o = orders.create_cart(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 1}])
        for bad in ({"phone": "123"}, {"customer_name": "A"}, {"address": "x"}, {"email": "a@b.c"}, {"phone": 912345678}):
            with self.assertRaises(ValidationError, msg=repr(bad)):
                orders.update_delivery(self.conn, CTX, o["id"], bad)
        o = orders.update_delivery(self.conn, CTX, o["id"], {"phone": "+84 912-345-678"})
        self.assertEqual(o["phone"], "0912345678")
        self.assertFalse(o["delivery_complete"])
        self.assertEqual(orders.get_latest_order(self.conn, "u1")["id"], o["id"])
        self.assertIsNone(orders.get_latest_order(self.conn, "nguoi-la"))


if __name__ == "__main__":
    unittest.main()
