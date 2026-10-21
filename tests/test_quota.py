import tempfile
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import requests

from backend.config import Settings
from src.llm_client import GeminiLLMClient, LLMError
from src.quota import DailyBudget, DailyLimitReached


class DailyBudgetTests(unittest.TestCase):
    def test_config_accepts_flash_lite_500_without_raising_other_model_limit(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "fake", "LLM_MODEL_ID": "gemini-3.5-flash-lite", "LLM_DAILY_REQUEST_LIMIT": "500"}):
            self.assertEqual(Settings.from_env().llm_daily_limit, 500)
            with patch.dict(os.environ, {"LLM_DAILY_REQUEST_LIMIT": "501"}):
                with self.assertRaises(ValueError):
                    Settings.from_env()
            with patch.dict(os.environ, {"LLM_MODEL_ID": "gemini-3.6-flash"}):
                with self.assertRaises(ValueError):
                    Settings.from_env()

    def test_persists_and_separates_models_and_pacific_days(self):
        with tempfile.TemporaryDirectory() as folder:
            path = folder + "/quota.db"
            day = datetime(2026, 10, 21, 6, 59, tzinfo=timezone.utc)
            budget = DailyBudget(path, 1)
            self.assertEqual(budget.reserve("gemini-3.6-flash", day), 1)
            with self.assertRaises(DailyLimitReached):
                DailyBudget(path, 1).reserve("gemini-3.6-flash", day)
            self.assertEqual(budget.reserve("another-model", day), 1)
            after_reset = datetime(2026, 10, 21, 7, 1, tzinfo=timezone.utc)
            self.assertEqual(budget.reserve("gemini-3.6-flash", after_reset), 1)

    def test_concurrent_attempts_cannot_exceed_twenty(self):
        with tempfile.TemporaryDirectory() as folder:
            budget = DailyBudget(folder + "/quota.db", 20)
            def reserve(_):
                try:
                    budget.reserve("gemini-3.6-flash")
                    return True
                except DailyLimitReached:
                    return False
            with ThreadPoolExecutor(max_workers=8) as pool:
                self.assertEqual(sum(pool.map(reserve, range(30))), 20)

    @patch("src.llm_client.requests.post")
    def test_budget_prevents_network_call(self, post):
        with tempfile.TemporaryDirectory() as folder:
            client = GeminiLLMClient(Settings(db_path="unused", api_key="test-key", llm_usage_path=folder + "/quota.db", llm_daily_limit=0))
            with self.assertRaises(LLMError) as caught:
                client.generate("message", [], {})
            self.assertEqual(caught.exception.code, "llm_daily_limit")
            post.assert_not_called()

    @patch("src.llm_client.requests.post")
    def test_default_does_not_retry_and_failed_attempt_still_counts(self, post):
        post.side_effect = requests.Timeout()
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(db_path="unused", api_key="test-key", llm_usage_path=folder + "/quota.db", llm_daily_limit=1)
            client = GeminiLLMClient(settings)
            with self.assertRaises(LLMError) as first:
                client.generate("message", [], {})
            self.assertEqual(first.exception.code, "llm_timeout")
            self.assertEqual(post.call_count, 1)
            with self.assertRaises(LLMError) as second:
                client.generate("message", [], {})
            self.assertEqual(second.exception.code, "llm_daily_limit")
            self.assertEqual(post.call_count, 1)
