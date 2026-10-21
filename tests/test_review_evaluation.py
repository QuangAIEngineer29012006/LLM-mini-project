import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import review_evaluation as review


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        scope = patch.object(review, "ROOT", self.root)
        scope.start()
        self.addCleanup(scope.stop)
        self.cases = self.root / "cases.json"
        self.report = self.root / "report.json"
        self.cases.write_text(json.dumps([{"id": "H01", "messages": ["</script><img src=x>"]}]))
        self.report.write_text(json.dumps({"provider": "fake", "cases": [{"id": "H01", "actual_route": "ask_missing"}]}))
        self.package = review.build([self.report], [self.cases])

    def filled(self):
        package = copy.deepcopy(self.package)
        package.update(human_reviewer="Reviewer Demo", reviewed_at="2026-10-21T10:00:00+07:00")
        package["cases"][0]["human_review"] = {
            "scores": {key: 1 for key in review.CRITERIA},
            "reasons": {key: "Đã xem output và đối chiếu input." for key in review.CRITERIA},
        }
        return package

    def test_blank_is_pending_not_zero(self):
        self.assertEqual(review.validate(self.package), 0)
        self.assertIn("0/1 case", review.markdown(self.package))
        self.assertNotIn("Điểm trung bình", review.markdown(self.package))

    def test_complete_rejects_pending(self):
        with self.assertRaisesRegex(ValueError, "Unreviewed"):
            review.validate(self.package, complete=True)

    def test_one_is_valid_and_has_correct_total(self):
        package = self.filled()
        self.assertEqual(review.validate(package, complete=True), 5)
        self.assertIn("5.00/10", review.markdown(package))

    def test_boolean_and_out_of_range_scores_rejected(self):
        for bad in [True, -1, 3, "2", 1.5]:
            with self.subTest(bad=bad):
                package = self.filled()
                package["cases"][0]["human_review"]["scores"]["intent"] = bad
                with self.assertRaises(ValueError):
                    review.validate(package)

    def test_assigned_score_requires_reason_and_reviewer(self):
        package = self.filled()
        package["cases"][0]["human_review"]["reasons"]["intent"] = ""
        with self.assertRaisesRegex(ValueError, "Explain"):
            review.validate(package)
        package = self.filled()
        package["human_reviewer"] = ""
        with self.assertRaisesRegex(ValueError, "Reviewer"):
            review.validate(package)

    def test_evidence_mutation_is_rejected(self):
        package = self.filled()
        package["cases"][0]["evidence"]["observed"]["actual_route"] = "draft_created"
        with self.assertRaisesRegex(ValueError, "Evidence changed"):
            review.validate(package)

    def test_changed_source_is_rejected(self):
        self.report.write_text(json.dumps({"cases": [{"id": "H01", "actual_route": "changed"}]}))
        with self.assertRaisesRegex(ValueError, "Source changed"):
            review.validate(self.package)

    def test_duplicate_case_is_rejected(self):
        package = copy.deepcopy(self.package)
        package["cases"].append(copy.deepcopy(package["cases"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            review.validate(package)

    def test_missing_case_is_rejected(self):
        package = self.filled()
        package["sources"]["extra.json"] = review.digest({"cases": [{"id": "H02"}]})
        (self.root / "extra.json").write_text(json.dumps({"cases": [{"id": "H02"}]}))
        with self.assertRaisesRegex(ValueError, "every observed"):
            review.validate(package)

    def test_html_does_not_execute_test_input(self):
        output = review.review_html(self.package)
        self.assertNotIn("</script><img src=x>", output)
        self.assertIn("\\u003c/script", output)

    def test_source_cannot_escape_repository(self):
        with self.assertRaisesRegex(ValueError, "inside repository"):
            review.source_path("../outside.json")


if __name__ == "__main__":
    unittest.main()
