import unittest

from scripts.error_analysis import build_error_analysis, classify_case


class ErrorAnalysisTests(unittest.TestCase):
    def test_classifies_multiple_independent_failures(self):
        result = {
            "id": "M01", "type": "multi", "role": "customer", "query": "q",
            "passed": False, "route_ok": False, "expected_route": "knowledge",
            "route": "handoff", "status_ok": True, "orders_ok": True,
            "expected_status": "answered", "evidence_ok": False,
            "citations": ["bad"], "citations_resolved": 0, "citations_supported": 0,
            "retrieval": {"hit@3": False, "recall@5": 0.5, "mrr": 0.0, "evidence_coverage": 0.5},
        }
        self.assertEqual(
            classify_case(result),
            ["routing", "retrieval", "context", "grounding", "citation"],
        )

    def test_passed_case_has_no_categories(self):
        result = {
            "passed": True, "route_ok": True, "status_ok": True, "orders_ok": True,
            "expected_status": "answered", "evidence_ok": True, "citations": [],
            "retrieval": {"hit@3": True, "recall@5": 1.0, "mrr": 1.0, "evidence_coverage": 1.0},
        }
        self.assertEqual(classify_case(result), [])

    def test_build_report_keeps_all_categories_and_case_details(self):
        result = {
            "id": "N01", "type": "no_evidence", "role": "customer", "query": "unknown",
            "passed": False, "route_ok": True, "status_ok": False, "orders_ok": True,
            "status": "answered", "expected_status": "insufficient_evidence",
            "evidence_ok": True, "citations": [], "retrieval": None,
        }
        report = build_error_analysis([result])
        self.assertEqual(report["error_case_count"], 1)
        self.assertEqual(report["category_counts"]["status_safety"], 1)
        self.assertEqual(report["cases"][0]["id"], "N01")


if __name__ == "__main__":
    unittest.main()
