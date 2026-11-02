"""Deterministic error classification for the RAG evaluation output.

The evaluator deliberately keeps the raw case result.  This module turns a
failed (or near-miss) case into an actionable category without changing the
expected labels or hiding failures.
"""

from collections import Counter
import argparse
import json
from pathlib import Path


ERROR_ORDER = (
    "routing",
    "retrieval",
    "context",
    "grounding",
    "citation",
    "status_safety",
    "action_validation",
)


def classify_case(result):
    """Return all observable error/near-miss categories for one case.

    A case may have more than one category.  The function only uses fields
    already emitted by ``evaluate_rag.py`` so it is safe to run offline.
    """
    categories = []
    retrieval = result.get("retrieval") or {}

    if not result.get("route_ok", True):
        categories.append("routing")
    if retrieval and not retrieval.get("hit@3", True):
        categories.append("retrieval")
    if retrieval and retrieval.get("recall@5", 1.0) < 1.0:
        if "retrieval" not in categories:
            categories.append("retrieval")
    if retrieval and result.get("type") == "multi" and retrieval.get("evidence_coverage", 1.0) < 1.0:
        categories.append("context")
    if result.get("expected_status") == "answered" and not result.get("evidence_ok", True):
        categories.append("grounding")
    if result.get("citations"):
        if result.get("citations_resolved", 0) < len(result["citations"]):
            categories.append("citation")
        elif result.get("citations_supported", 0) < len(result["citations"]):
            categories.append("citation")
    if not result.get("status_ok", True):
        categories.append("status_safety")
    if not result.get("orders_ok", True):
        categories.append("action_validation")

    # Preserve a stable order and remove duplicates from overlapping checks.
    return [category for category in ERROR_ORDER if category in categories]


def _reason(category, result):
    retrieval = result.get("retrieval") or {}
    if category == "routing":
        return f"route={result.get('route')!r}, expected={result.get('expected_route')!r}"
    if category == "retrieval":
        return (f"Hit@3={retrieval.get('hit@3')}, "
                f"Recall@5={retrieval.get('recall@5')}, MRR={retrieval.get('mrr')}")
    if category == "context":
        return f"evidence coverage={retrieval.get('evidence_coverage')} for multi-condition query"
    if category == "grounding":
        return "answer does not contain all expected evidence spans"
    if category == "citation":
        return (f"resolved={result.get('citations_resolved', 0)}, "
                f"supported={result.get('citations_supported', 0)}, "
                f"total={len(result.get('citations') or [])}")
    if category == "status_safety":
        return f"status={result.get('status')!r}, expected={result.get('expected_status')!r}"
    if category == "action_validation":
        return f"orders={result.get('orders')}, expected order count is not satisfied"
    return "observable evaluation mismatch"


def build_error_analysis(results):
    """Build machine-readable error and near-miss analysis from case results."""
    cases = []
    counts = Counter()
    for result in results:
        categories = classify_case(result)
        if not categories:
            continue
        for category in categories:
            counts[category] += 1
        cases.append({
            "id": result.get("id"),
            "type": result.get("type"),
            "role": result.get("role"),
            "query": result.get("query"),
            "passed": bool(result.get("passed")),
            "categories": categories,
            "reasons": {category: _reason(category, result) for category in categories},
        })
    return {
        "case_count": len(results),
        "error_case_count": len(cases),
        "category_counts": {category: counts.get(category, 0) for category in ERROR_ORDER},
        "cases": cases,
    }


def render_markdown(analysis, summary):
    """Render a compact report suitable for the repository artifacts folder."""
    lines = [
        "# Automatic RAG error analysis",
        "",
        "Báo cáo này được sinh từ kết quả evaluation; không thay đổi nhãn expected và không loại bỏ case thất bại.",
        "",
        f"- Cases: {analysis['case_count']}",
        f"- Cases có lỗi/near-miss: {analysis['error_case_count']}",
        f"- Pass: {summary.get('passed')}/{summary.get('cases')}",
        f"- Hit@3: {summary.get('hit@3')}",
        f"- Recall@5: {summary.get('recall@5')}",
        f"- MRR: {summary.get('mrr')}",
        "",
        "## Phân loại",
        "",
        "| Loại | Số case |",
        "|---|---:|",
    ]
    for category, count in analysis["category_counts"].items():
        lines.append(f"| {category} | {count} |")
    lines.extend(["", "## Chi tiết", "", "| Case | Loại | Categories | Phân tích |", "|---|---|---|---|"])
    for case in analysis["cases"]:
        reasons = "<br>".join(f"{key}: {value}" for key, value in case["reasons"].items())
        lines.append(f"| {case['id']} | {case['type']} | {', '.join(case['categories'])} | {reasons} |")
    if not analysis["cases"]:
        lines.append("| — | — | — | Không có lỗi hoặc near-miss được phát hiện. |")
    lines.extend([
        "",
        "## Cách sử dụng",
        "",
        "Báo cáo thủ công vẫn cần xem xét nguyên nhân nghiệp vụ và xác nhận claim; báo cáo tự động chỉ phân loại theo các tín hiệu đo được.",
    ])
    return "\n".join(lines) + "\n"


def main(argv=None):
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Create an error-analysis artifact from an evaluation JSON file")
    parser.add_argument("input", type=Path, help="evaluation_results_*.json")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    results = payload.get("results", [])
    summary = payload.get("summary", {})
    analysis = build_error_analysis(results)
    json_output = args.json_output or args.input.with_name(args.input.stem + "_error_analysis.json")
    markdown_output = args.markdown_output or args.input.with_name(args.input.stem + "_error_analysis.md")
    json_output.write_text(json.dumps({"summary": summary, **analysis}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_output.write_text(render_markdown(analysis, summary), encoding="utf-8")
    print(json.dumps({"json": str(json_output), "markdown": str(markdown_output), **analysis}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
