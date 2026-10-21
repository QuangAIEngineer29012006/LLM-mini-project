import copy
import tempfile
import unittest
from pathlib import Path

from scripts import browser_acceptance as acceptance


class BrowserAcceptanceTests(unittest.TestCase):
    def test_template_has_no_fabricated_passes(self):
        self.assertEqual(acceptance.validate(acceptance.template())["not_run"], 15)

    def test_incomplete_cannot_be_signed_off(self):
        with self.assertRaises(ValueError):
            acceptance.validate(acceptance.template(), complete=True)

    def test_case_cannot_be_dropped_or_duplicated(self):
        data = acceptance.template()
        data["cases"][-1] = copy.deepcopy(data["cases"][0])
        with self.assertRaises(ValueError):
            acceptance.validate(data)

    def test_pass_requires_observation_and_evidence(self):
        data = acceptance.template()
        data["cases"][0].update(status="pass", observed="Đã kiểm tra catalog trên Chrome.")
        with self.assertRaisesRegex(ValueError, "evidence"):
            acceptance.validate(data)

    def test_valid_record_and_missing_screenshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / "evidence.txt").write_text("Test-only browser observation")
            data = acceptance.template()
            data.update(tester="Demo", tested_commit="abc123", browser_version="Chrome demo", os="Windows",
                        provider="fake", tested_at="2026-10-21T10:00:00+07:00")
            data["cases"][0].update(status="pass", observed="Đã xem catalog trong phiên demo.", evidence=["evidence.txt"])
            self.assertEqual(acceptance.validate(data, root=root)["pass"], 1)
            data["cases"][0]["evidence"] = ["absent.png"]
            with self.assertRaisesRegex(ValueError, "Missing"):
                acceptance.validate(data, root=root)
