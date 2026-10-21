"""Verify Gemini -> validated extraction -> real SQLite reads and draft workflow."""
import json
import argparse
import sys
import tempfile
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from database.shop_db.db import connect
from src.prompts import PROMPT_VERSION


def run():
    settings = Settings.from_env()
    if settings.llm_provider != "gemini" or not settings.api_key:
        raise SystemExit("Cần cấu hình Gemini trong .env để kiểm tra live.")
    calls, results = [], []
    last_call = None
    original = requests.post
    target = ROOT / "sample_results/catalog_live_smoke.json"

    def observed(*args, **kwargs):
        nonlocal last_call
        if last_call is not None:
            time.sleep(max(0, 16 - (time.monotonic() - last_call)))
        last_call = time.monotonic()
        # Calls are real; the wrapper records only provider metadata, never credentials/prompts.
        start = time.monotonic()
        try:
            reply = original(*args, **kwargs)
        except requests.RequestException as err:
            calls.append({"transport_error": type(err).__name__})
            raise
        try:
            body = reply.json()
        except ValueError:
            body = {}
        calls.append({"http_status": reply.status_code, "model_version": body.get("modelVersion"),
                      "seconds": round(time.monotonic() - start, 2), "usage": body.get("usageMetadata"),
                      "retry_after": reply.headers.get("Retry-After")})
        return reply

    def save():
        target.write_text(json.dumps({"timestamp_utc": datetime.now(timezone.utc).isoformat(),
                                     "model": settings.model_id, "prompt_version": PROMPT_VERSION,
                                     "database": "temporary seeded SQLite", "mock_provider": False,
                                     "completed": len(results) == 8,
                                     "passed": len(results) == 8 and all(r["passed"] for r in results),
                                     "cases": results, "provider_calls": calls}, indent=2, ensure_ascii=False) + "\n")

    with tempfile.TemporaryDirectory() as folder, patch("src.llm_client.requests.post", side_effect=observed):
        path = folder + "/live.db"
        with TestClient(create_app(replace(settings, db_path=path, request_limit=1000, chat_limit=100))) as client:
            def session():
                return {"Authorization": "Bearer " + client.post("/api/session").json()["token"]}

            def check(name, message, headers, expected, predicate=lambda data: True):
                start = time.monotonic()
                reply = client.post("/api/chat", headers={**headers, "Idempotency-Key": f"live-catalog-{len(results):04d}"}, json={"message": message})
                data = reply.json()
                passed = reply.status_code == 200 and data.get("route") == expected and predicate(data)
                results.append({"name": name, "expected_route": expected, "actual_route": data.get("route"),
                                "interpretation_source": data.get("interpretation_source"),
                                "intent": data.get("intent"), "passed": passed, "error_type": data.get("error_type"),
                                "product_count": len(data.get("products", [])), "reply": data.get("reply"),
                                "latency_ms": round((time.monotonic() - start) * 1000, 2)})
                save()
                print(f"{'PASS' if passed else 'FAIL'}: {name}: {data.get('route')} ({results[-1]['latency_ms']} ms)", flush=True)
                if not passed:
                    raise SystemExit(f"Stopped at failed live check; see {target}")
                return data

            headers = session()
            check("Original screenshot question", "tôi muốn tham khảo sản phẩm, cửa hàng bạn bán những gì", headers,
                  "catalog_shown", lambda d: len(d["products"]) == 6 and d["order"] is None)
            check("Product details", "Cho tôi xem áo thun đen size M", headers, "catalog_shown",
                  lambda d: [v["sku"] for p in d["products"] for v in p["variants"]] == ["TSH-BLK-M"])
            check("Follow-up price", "Giá bao nhiêu?", headers, "price_checked", lambda d: "150,000" in d["reply"])
            check("Follow-up stock", "Mẫu này còn hàng không?", headers, "stock_checked", lambda d: "còn 25" in d["reply"])
            check("Explicit purchase after browsing", "Chốt 2 cái", headers, "ask_missing",
                  lambda d: set(d["missing_fields"]) == {"recipient_name", "phone", "address"})
            check("Collect delivery and create draft", "Tên Khách Demo, SĐT 0912345678, giao về 12 Đường Mẫu, Quận 7", headers,
                  "draft_created", lambda d: d["order"]["total"] == 300000 and d["order"]["items"][0]["sku"] == "TSH-BLK-M")
            check("Category, budget, stock filters", "Cho tôi xem giày dưới 800k còn hàng", session(), "catalog_shown",
                  lambda d: bool(d["products"]) and all(p["category"] == "Giày" and all(v["unit_price"] <= 800000 and v["stock"] > 0 for v in p["variants"]) for p in d["products"]))
            check("Unavailable product", "Cửa hàng có bán máy ảnh không?", session(), "catalog_empty", lambda d: d["products"] == [])
            with connect(path) as conn:
                assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
                assert conn.execute("SELECT quantity FROM inventory WHERE sku='TSH-BLK-M'").fetchone()[0] == 25
    print(f"PASS: {len(results)} live checks; {target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smoke test có thể dùng tối đa 8 lượt Gemini, trừ lượt xử lý local.")
    parser.add_argument("--allow-live", action="store_true", help="Cho phép gọi Google thật và sử dụng quota ngày")
    args = parser.parse_args()
    if not args.allow_live:
        raise SystemExit("Chưa gọi Google: cần --allow-live; các lượt gọi thật được tính vào ngân sách ngày của model.")
    run()
