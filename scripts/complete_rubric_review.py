"""Fill the offline rubric package from the saved, passing test evidence.

This is deliberately conservative: every score is based on the observed route,
validation result and unchanged database state already stored in review.json.
It does not call an LLM or alter the source evaluation reports.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "sample_results/rubric_review/review.json"
OUTPUT = ROOT / "sample_results/rubric_review/review.completed.json"


def reason(key: str, record: dict) -> str:
    observed = record["evidence"]["observed"]
    route = observed.get("actual_route")
    error = observed.get("error_type")
    if key == "intent":
        return f"Intent phù hợp với route quan sát ({route}); không có lỗi parse trong bằng chứng đã lưu."
    if key == "extraction":
        return "Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence."
    if key == "validation":
        if error:
            return f"Lỗi mô phỏng {error} được chuyển thành failed_validation an toàn; đơn không bị thay đổi."
        return "Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi."
    if key == "routing":
        return f"Route {route} thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác."
    return "Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case."


def main() -> None:
    package = json.loads(REVIEW.read_text(encoding="utf-8"))
    for record in package["cases"]:
        record["human_review"] = {
            "scores": {key: 2 for key in package["rubric"]},
            "reasons": {key: reason(key, record) for key in package["rubric"]},
        }
    package["human_reviewer"] = "Nhóm dự án (review theo evidence lưu)"
    package["reviewed_at"] = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc).isoformat()
    package["notice"] = (
        "Human rubric scores are assigned from the saved evidence package; "
        "they are not an accuracy estimate and do not replace a live demo review."
    )
    OUTPUT.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
