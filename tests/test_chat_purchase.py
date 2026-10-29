import json

from src.llm_client import FakeLLMClient
from tests.backend_helpers import BackendTestCase, DELIVERY_TEXT
from tests.test_llm import StubLLM


REQUEST = 'đặt cho tôi balo laptop Balo laptop xám, 15inch'


class ChatPurchaseTests(BackendTestCase):
    def test_exact_request_resolves_backpack_and_asks_for_count_and_shipping(self):
        result = self.post_chat(REQUEST).json()
        self.assertEqual(result['route'], 'ask_missing', result)
        self.assertEqual(set(result['missing_fields']), {'quantity', 'recipient_name', 'phone', 'address'})
        item = result['purchase']['items'][0]
        self.assertEqual((item['sku'], item['variant_label'], item['unit_price'], item['stock'], item['quantity']),
                         ('BAG-GRY-15', 'Xám / 15 inch', 520000, 4, None))
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM orders'), 0)
        final = self.post_chat('Chốt 2 BAG-GRY-15, ' + DELIVERY_TEXT, key='backpack-checkout-001').json()
        self.assertEqual(final['route'], 'draft_created', final)
        self.assertEqual(final['order']['status'], 'pending_confirmation')
        self.assertEqual(final['order']['total'], 1040000)
        self.assertEqual(len(final['order']['items']), 1)
        replay = self.post_chat('Chốt 2 BAG-GRY-15, ' + DELIVERY_TEXT, key='backpack-checkout-001').json()
        self.assertEqual(replay['order']['order_id'], final['order']['order_id'])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM orders'), 1)
        self.assertEqual(self.scalar("SELECT quantity FROM inventory WHERE sku='BAG-GRY-15'"), 4)

    def test_model_inferred_count_is_discarded_and_never_treated_as_user_consent(self):
        for guessed in (1, 15):
            with self.subTest(guessed=guessed):
                payload = json.loads(FakeLLMClient().generate(REQUEST, [{'name': 'Balo laptop', 'aliases': []}], {}).text)
                payload['items'][0]['quantity'] = guessed
                payload['items'][0]['variant']['size'] = '15 inch'
                self.app.state.llm_client = StubLLM(json.dumps(payload))
                result = self.post_chat(REQUEST).json()
                self.assertEqual(result['route'], 'ask_missing', result)
                self.assertIn('quantity', result['missing_fields'])
                self.assertIsNone(result['purchase']['items'][0]['quantity'])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM orders'), 0)

    def test_explicit_count_complete_delivery_creates_backpack_order(self):
        result = self.post_chat('Đặt 1 balo laptop xám 15inch, ' + DELIVERY_TEXT).json()
        self.assertEqual(result['route'], 'draft_created', result)
        self.assertEqual(result['order']['items'][0]['sku'], 'BAG-GRY-15')
        self.assertEqual(result['order']['total'], 520000)

    def test_measurement_is_not_quantity_even_when_separated_by_a_space(self):
        result = self.post_chat('Đặt balo laptop xám 15 inch, ' + DELIVERY_TEXT).json()
        self.assertEqual(result['route'], 'ask_missing', result)
        self.assertEqual(result['missing_fields'], ['quantity'])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM orders'), 0)

    def test_no_stock_and_unknown_measurement_never_offer_purchase_form(self):
        for message, route in [('Đặt 1 balo laptop đen 15inch', 'out_of_stock'),
                               ('Đặt 1 balo laptop xám 16inch', 'ask_missing')]:
            with self.subTest(message=message):
                result = self.post_chat(message).json()
                self.assertEqual(result['route'], route, result)
                self.assertNotIn('purchase', result)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM orders'), 0)

    def test_rechecks_stock_on_subsequent_count_and_shipping(self):
        self.post_chat(REQUEST)
        result = self.post_chat('Chốt 5 BAG-GRY-15, ' + DELIVERY_TEXT).json()
        self.assertEqual(result['route'], 'out_of_stock', result)
        self.assertIn('còn 4', result['reply'])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM orders'), 0)

    def test_browsing_backpack_does_not_offer_purchase_form_or_create_order(self):
        result = self.post_chat('Cho xem balo laptop xám 15inch').json()
        self.assertEqual(result['route'], 'catalog_shown', result)
        self.assertNotIn('purchase', result)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM orders'), 0)

    def test_different_explicit_count_cannot_be_silently_replaced(self):
        message = 'Đặt 3 balo laptop xám 15inch'
        payload = json.loads(FakeLLMClient().generate(message, [{'name': 'Balo laptop', 'aliases': []}], {}).text)
        payload['items'][0]['quantity'] = 1
        self.app.state.llm_client = StubLLM(json.dumps(payload))
        result = self.post_chat(message).json()
        self.assertEqual(result['route'], 'failed_validation', result)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM orders'), 0)

    def test_sku_suffix_and_delivery_numbers_are_not_an_order_count(self):
        message = 'Đặt BAG-GRY-15, ' + DELIVERY_TEXT
        payload = json.loads(FakeLLMClient().generate(message, [], {}).text)
        payload['items'][0]['quantity'] = 1
        self.app.state.llm_client = StubLLM(json.dumps(payload))
        result = self.post_chat(message).json()
        self.assertEqual(result['route'], 'ask_missing', result)
        self.assertEqual(result['missing_fields'], ['quantity'])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM orders'), 0)

    def test_model_cannot_turn_negative_or_fractional_count_into_positive_integer(self):
        for count in ('-2', '1.5'):
            message = 'Đặt ' + count + ' balo laptop xám 15inch, ' + DELIVERY_TEXT
            payload = json.loads(FakeLLMClient().generate(message, [{'name': 'Balo laptop', 'aliases': []}], {}).text)
            payload['items'][0]['quantity'] = 2 if count == '-2' else 1
            self.app.state.llm_client = StubLLM(json.dumps(payload))
            result = self.post_chat(message).json()
            self.assertEqual(result['route'], 'failed_validation', result)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM orders'), 0)

    def test_unlabelled_customer_address_cannot_supply_a_missing_quantity(self):
        message = 'Đặt balo laptop xám 15inch, Khách Demo, 0912345678, 12 Đường Mẫu, Quận 7'
        payload = json.loads(FakeLLMClient().generate(message, [{'name': 'Balo laptop', 'aliases': []}], {}).text)
        payload['items'] = [payload['items'][0]]
        payload['items'][0]['quantity'] = 12
        payload['customer'] = {'name': 'Khách Demo', 'phone': '0912345678', 'address': '12 Đường Mẫu, Quận 7'}
        self.app.state.llm_client = StubLLM(json.dumps(payload))
        result = self.post_chat(message).json()
        self.assertEqual(result['route'], 'ask_missing', result)
        self.assertEqual(result['missing_fields'], ['quantity'])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM orders'), 0)

    def test_short_phone_is_reported_as_phone_not_recipient(self):
        message = 'Đặt 1 balo laptop xám 15inch, tên Khách Demo, SĐT 091234567, giao về 12 Đường Mẫu, Quận 7'
        payload = json.loads(FakeLLMClient().generate(message, [{'name': 'Balo laptop', 'aliases': []}], {}).text)
        payload['customer'] = {'name': 'Khách Demo', 'phone': '091234567', 'address': '12 Đường Mẫu, Quận 7'}
        self.app.state.llm_client = StubLLM(json.dumps(payload))
        result = self.post_chat(message).json()
        self.assertEqual(result['route'], 'ask_missing', result)
        self.assertEqual(result['missing_fields'], ['phone'])

    def test_unknown_sku_or_order_reference_gets_a_chat_reply(self):
        for message, missing in [('Chốt 2 TSH-ZZZ-M, ' + DELIVERY_TEXT, 'product'),
                                 ('Sửa đơn DH999999 đổi 3 cái', 'order_reference')]:
            with self.subTest(message=message):
                result = self.post_chat(message, headers=self.session())
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json()['route'], 'ask_missing')
                self.assertEqual(result.json()['missing_fields'], [missing])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM orders'), 0)
