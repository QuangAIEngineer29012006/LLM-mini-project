"""Record real-browser acceptance separately from AppTest. No synthetic PASS results."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = [
    ("B01", "Catalog và tìm kiếm", "Giá/tồn từ API; tìm áo thun và xóa bộ lọc được."),
    ("B02", "Chi tiết và biến thể hết hàng", "Chọn áo trắng size M; không thêm SKU hết hàng vào giỏ."),
    ("B03", "Giỏ hàng", "Thêm áo đen M; sửa số lượng, xóa item; tổng tiền cập nhật."),
    ("B04", "Form giao nhận", "Thiếu/sai field được báo rõ; không tạo đơn khi form sai."),
    ("B05", "Checkout và gửi hai lần", "Gửi thông tin mock; một yêu cầu lặp không tạo hai đơn; pending_confirmation."),
    ("B06", "Sửa đơn", "Sửa số lượng/size; giá và tồn được kiểm tra lại; không sửa nhầm đơn."),
    ("B07", "Chat nhiều lượt", "Đặt áo đen M, bổ sung giao nhận; đơn xuất hiện trong cùng phiên."),
    ("B08", "Tra giá/tồn giữa hội thoại", "Giá/tồn đúng DB; yêu cầu mua đang dở vẫn tiếp tục được."),
    ("B09", "SKU sai hoặc vượt tồn", "Không tạo đơn sai; phản hồi chỉ rõ điều cần sửa."),
    ("B10", "Prompt injection và đơn mơ hồ", "Không lộ secret/xóa dữ liệu; hỏi mã đơn hoặc handoff."),
    ("B11", "Lỗi kết nối API", "Hiển thị lỗi dễ hiểu, không báo thành công; khôi phục cấu hình rồi thử lại được."),
    ("B12", "Tải lại trang", "Không crash/nhân đôi đơn; ghi rõ phiên còn hay tạo mới theo thiết kế."),
    ("B13", "Hai phiên trình duyệt", "Phiên thường và ẩn danh không đọc/sửa được đơn của nhau."),
    ("B14", "Desktop 1366x768", "6 màn hình không bị che nút/chồng chữ; nội dung và điều hướng đọc được."),
    ("B15", "Mobile 390x844", "Sidebar/form/chat/bảng dùng được; kiểm tra cuộn ngang và nút gửi."),
]


def template():
    return {"schema_version": 1, "test_type": "real_browser_manual", "tester": "", "tested_commit": "",
            "browser_version": "", "os": "", "provider": "", "tested_at": "",
            "notice": "not_run is not a pass; run again after the redesigned UI is integrated.",
            "cases": [{"id": cid, "name": name, "expected": expected, "status": "not_run",
                       "observed": "", "evidence": []} for cid, name, expected in SCENARIOS]}


def validate(data, complete=False, root=ROOT):
    if data.get("schema_version") != 1 or data.get("test_type") != "real_browser_manual":
        raise ValueError("Wrong acceptance format")
    ids = [case["id"] for case in data["cases"]]
    if len(set(ids)) != len(SCENARIOS) or set(ids) != {s[0] for s in SCENARIOS}:
        raise ValueError("All 15 browser scenarios must be present exactly once")
    ran = False
    for case in data["cases"]:
        status = case["status"]
        if status not in {"not_run", "pass", "fail", "blocked"}:
            raise ValueError("Invalid status: " + case["id"])
        if status != "not_run":
            ran = True
            if len(case.get("observed", "").strip()) < 10:
                raise ValueError("Describe what was actually observed: " + case["id"])
        if status in {"pass", "fail"}:
            if not case.get("evidence"):
                raise ValueError("Browser evidence is required: " + case["id"])
            for item in case["evidence"]:
                path = (root / item).resolve()
                if not path.is_relative_to(root.resolve()) or not path.is_file():
                    raise ValueError("Missing or external evidence file: " + str(item))
        if complete and status != "pass":
            raise ValueError("Acceptance is incomplete or failing: " + case["id"])
    if ran:
        for key in ["tester", "tested_commit", "browser_version", "os", "provider", "tested_at"]:
            if not isinstance(data.get(key), str) or not data[key].strip():
                raise ValueError("Missing environment field: " + key)
        datetime.fromisoformat(data["tested_at"].replace("Z", "+00:00"))
    return {status: sum(c["status"] == status for c in data["cases"]) for status in ["pass", "fail", "blocked", "not_run"]}


def render(data):
    counts = validate(data)
    lines = ["# Nghiệm thu trình duyệt thật", "", "Đây là bản ghi kiểm thử trực tiếp, tách khỏi AppTest.",
             "", f"Kết quả: {counts}. UI revision: {data['tested_commit'] or 'Chưa chạy'}.", "",
             "| Case | Kịch bản | Trạng thái | Quan sát | Evidence |", "|---|---|---|---|---|"]
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    for case in data["cases"]:
        lines.append("| " + " | ".join(map(cell, [case["id"], case["name"], case["status"], case["observed"], ", ".join(case["evidence"])])) + " |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "report"])
    parser.add_argument("file", type=Path)
    parser.add_argument("--complete", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "init":
            if args.file.exists():
                raise ValueError("Refusing to overwrite an existing acceptance record")
            args.file.parent.mkdir(parents=True, exist_ok=True)
            args.file.write_text(json.dumps(template(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("Created 15 NOT RUN scenarios")
        else:
            data = json.loads(args.file.read_text(encoding="utf-8-sig"))
            counts = validate(data, complete=args.complete)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(render(data), encoding="utf-8")
            print(json.dumps(counts))
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
