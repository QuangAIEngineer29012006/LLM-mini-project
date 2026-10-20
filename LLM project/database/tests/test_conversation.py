import os
import tempfile
import unittest

from shop_db import conversation_service as conv
from shop_db import order_service as orders
from shop_db.db import connect, migrate
from shop_db.errors import ConversationNotFound, OrderNotFound, ValidationError
from tests.helpers import CTX, DBTestCase


class ConversationTests(DBTestCase):
    def test_create_and_get(self):
        c = conv.get_or_create_conversation(self.conn, "u1")
        self.assertEqual((c["owner_id"], c["state"], c["context"]), ("u1", "idle", {}))
        self.assertEqual(conv.get_or_create_conversation(self.conn, "u1", c["id"])["id"], c["id"])
        self.assertEqual(conv.get_latest_conversation(self.conn, "u1")["id"], c["id"])
        self.assertIsNone(conv.get_latest_conversation(self.conn, "nguoi-la"))
        with self.assertRaises(ConversationNotFound):
            conv.get_conversation(self.conn, "khong-co")

    def test_merge_context_across_turns(self):
        c = conv.create_conversation(self.conn, "u1")
        conv.update_conversation(self.conn, c["id"], state="collecting_info", pending_intent="create_order",
                                 merge={"items": [{"sku": "TSH-BLK-M", "quantity": 2}], "customer_name": "Lê B"})
        c2 = conv.update_conversation(self.conn, c["id"], merge={"phone": "0912345678", "customer_name": None})
        self.assertEqual(c2["context"], {"items": [{"sku": "TSH-BLK-M", "quantity": 2}], "phone": "0912345678"})
        self.assertEqual((c2["state"], c2["pending_intent"]), ("collecting_info", "create_order"))

    def test_replace_and_reset(self):
        c = conv.create_conversation(self.conn, "u1")
        conv.update_conversation(self.conn, c["id"], context={"a": 1}, state="handoff")
        r = conv.reset_conversation(self.conn, c["id"])
        self.assertEqual((r["context"], r["state"], r["pending_intent"], r["last_order_id"]), ({}, "idle", None, None))

    def test_last_order_reference_must_exist(self):
        c = conv.create_conversation(self.conn, "u1")
        o = orders.create_cart(self.conn, CTX, "u1", [{"sku": "CAP-BLK-F", "quantity": 1}])
        self.assertEqual(conv.update_conversation(self.conn, c["id"], last_order_id=o["id"])["last_order_id"], o["id"])
        with self.assertRaises(OrderNotFound):
            conv.update_conversation(self.conn, c["id"], last_order_id=9999)

    def test_validation(self):
        c = conv.create_conversation(self.conn, "u1")
        bad_updates = [{"state": "hack"}, {"context": "text"}, {"context": {"x": object()}},
                       {"context": {"big": "x" * 9000}}, {"merge": [1]}, {"context": {}, "merge": {}},
                       {"pending_intent": "x" * 60}]
        for kw in bad_updates:
            with self.assertRaises(ValidationError, msg=repr(kw)[:40]):
                conv.update_conversation(self.conn, c["id"], **kw)
        with self.assertRaises(ValidationError):
            conv.create_conversation(self.conn, "")
        self.assertEqual(conv.get_conversation(self.conn, c["id"])["context"], {})

    def test_messages_order_truncate_prune(self):
        c = conv.create_conversation(self.conn, "u1")
        conv.add_message(self.conn, c["id"], "user", "xin chào")
        conv.add_message(self.conn, c["id"], "assistant", "chào bạn")
        self.assertEqual([m["role"] for m in conv.get_messages(self.conn, c["id"])], ["user", "assistant"])
        self.assertEqual(len(conv.add_message(self.conn, c["id"], "user", "x" * 5000)["content"]), 2000)
        for i in range(conv.MAX_MESSAGES_PER_CONVERSATION + 5):
            conv.add_message(self.conn, c["id"], "user", f"m{i}")
        self.assertEqual(self.count("conversation_messages"), conv.MAX_MESSAGES_PER_CONVERSATION)
        last = conv.get_messages(self.conn, c["id"], limit=1)[0]
        self.assertEqual(last["content"], f"m{conv.MAX_MESSAGES_PER_CONVERSATION + 4}")
        for role, content in (("bot", "x"), ("user", ""), ("user", "   "), ("user", None)):
            with self.assertRaises(ValidationError):
                conv.add_message(self.conn, c["id"], role, content)
        with self.assertRaises(ConversationNotFound):
            conv.add_message(self.conn, "khong-co", "user", "hi")

    def test_conversations_are_isolated(self):
        a, b = conv.create_conversation(self.conn, "ua"), conv.create_conversation(self.conn, "ub")
        conv.update_conversation(self.conn, a["id"], merge={"k": "va"})
        conv.add_message(self.conn, a["id"], "user", "tin của A")
        self.assertEqual(conv.get_conversation(self.conn, b["id"])["context"], {})
        self.assertEqual(conv.get_messages(self.conn, b["id"]), [])

    def test_context_survives_new_connection(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.db")
            c1 = connect(path); migrate(c1)
            cid = conv.create_conversation(c1, "u1")["id"]
            conv.update_conversation(c1, cid, merge={"missing": ["phone", "address"]}, state="collecting_info")
            c1.close()
            c2 = connect(path)
            got = conv.get_conversation(c2, cid)
            self.assertEqual((got["context"], got["state"]), ({"missing": ["phone", "address"]}, "collecting_info"))
            c2.close()


if __name__ == "__main__":
    unittest.main()
