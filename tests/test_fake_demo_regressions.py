import json
import unittest

from src.llm_client import FakeLLMClient


class FakeDemoRegressionTests(unittest.TestCase):
    def test_polite_purchase_extracts_quantity_without_inventing_unknown_sku(self):
        client = FakeLLMClient()
        for message, quantity in [("Cho chị 3 hộp loại 500g", 3), ("Cho em hai hộp cà phê", 2)]:
            with self.subTest(message=message):
                data = json.loads(client.generate(message, [], {}).text)
                self.assertEqual(data["intent"], "create_order")
                self.assertEqual(data["items"][0]["quantity"], quantity)
                self.assertIsNone(data["items"][0]["sku"])

    def test_labeled_quantity_is_not_confused_with_order_reference_or_size(self):
        data = json.loads(FakeLLMClient().generate("Đổi đơn DH000001 sang size L, số lượng 2.", [], {}).text)
        self.assertEqual(data["intent"], "update_order")
        self.assertEqual(data["order_reference"], "DH000001")
        self.assertEqual(data["items"][0]["quantity"], 2)

    def test_browsing_is_not_promoted_to_purchase(self):
        data = json.loads(FakeLLMClient().generate("Cho chị xem 3 mẫu áo", [], {}).text)
        self.assertEqual(data["intent"], "browse_catalog")

    def test_pair_of_shoes_is_an_order_not_an_update(self):
        data = json.loads(FakeLLMClient().generate("Cho tôi đặt 1 đôi SNK-WHT-41", [], {}).text)
        self.assertEqual(data["intent"], "create_order")
        self.assertEqual(data["items"][0]["quantity"], 1)
