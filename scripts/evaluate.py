"""Run the same workflow cases with offline rules or the configured Gemini client."""
import argparse
import json
import sys
import tempfile
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from database.shop_db.db import connect
from src.llm_client import LLMError, LLMResult
from src.llm_client import make_client
from src.prompts import PROMPT_VERSION


class FaultClient:
    model_id = "injected-failure"

    def __init__(self, fault):
        self.fault = fault

    def generate(self, *args):
        if self.fault == "timeout":
            raise LLMError("llm_timeout", 2)
        if self.fault == "rate_limit":
            raise LLMError("llm_rate_limit")
        return LLMResult("{" if self.fault == "invalid_json" else "")


class RecordedClient:
    def __init__(self, delegate, pace, clock):
        self.delegate, self.pace, self.clock = delegate, pace, clock
        self.model_id = delegate.model_id
        self.calls = []

    def generate(self, *args):
        if self.pace and self.clock[0] is not None:
            time.sleep(max(0, self.pace - (time.monotonic() - self.clock[0])))
        self.clock[0] = time.monotonic()
        try:
            result = self.delegate.generate(*args)
        except LLMError as err:
            self.calls.append({"error_type": err.code})
            raise
        try:
            extraction = json.loads(result.text)
            if isinstance(extraction, dict):
                customer = extraction.get("customer") or {}
                extraction["evidence"] = ["[omitted from evaluation log]"] if extraction.get("evidence") else []
                if isinstance(customer, dict):
                    extraction["customer"] = {k: "[PRESENT]" if v else None for k, v in customer.items()}
        except (ValueError, TypeError):
            extraction = "[invalid JSON]"
        self.calls.append({"extraction": extraction, "input_tokens": result.input_tokens,
                           "output_tokens": result.output_tokens, "retry_count": result.retry_count})
        return result


def evaluate(provider, output, case_ids=None, pace_seconds=0, case_file=None):
    base = Settings.from_env() if provider == "gemini" else Settings(db_path="unused")
    if provider == "gemini" and not base.api_key:
        raise SystemExit("Cần GEMINI_API_KEY trong .env để đánh giá Gemini.")
    cases = json.loads((case_file or ROOT / "tests/test_cases.json").read_text(encoding="utf-8-sig"))
    if case_ids:
        if set(case_ids) - {c["id"] for c in cases}:
            raise SystemExit("Case ID không có trong test set.")
        cases = [c for c in cases if c["id"] in case_ids]
    results = []
    clock = [None]
    for case in cases:
        with tempfile.TemporaryDirectory() as folder:
            settings = replace(base, db_path=folder + "/evaluation.db", llm_provider=provider,
                               request_limit=10000, session_limit=1000, chat_limit=1000)
            fault = FaultClient(case["fault"]) if "fault" in case else None
            recorded = RecordedClient(fault or make_client(settings), pace_seconds if provider == "gemini" and not fault else 0, clock)
            with TestClient(create_app(settings, llm_client=recorded)) as client:
                token = client.post("/api/session").json()["token"]
                headers = {"Authorization": "Bearer " + token}
                for setup in case.get("setup_orders", []):
                    added = client.post("/api/cart/items", headers=headers, json=setup)
                    if added.status_code != 200:
                        raise RuntimeError("Cannot prepare cart fixture")
                    created = client.post("/api/orders", headers=headers, json={"shipping": {
                        "recipient_name": "Khách Demo", "phone": "0912345678", "address": "12 Đường Mẫu, Quận 7"}})
                    if created.status_code != 200:
                        raise RuntimeError("Cannot prepare draft fixture")
                conn = connect(settings.db_path)
                stock_before = {r["sku"]: r["quantity"] for r in conn.execute("SELECT sku,quantity FROM inventory")}
                conn.close()
                start = time.monotonic()
                turns = []
                status = None
                for index, message in enumerate(case["messages"]):
                    reply = client.post("/api/chat", headers={**headers, "Idempotency-Key": f"eval-{case['id']}-{index:04d}"}, json={"message": message})
                    status = reply.status_code
                    turns.append(reply.json())
                actual = turns[-1]
                count = len(client.get("/api/orders", headers=headers).json()["orders"])
                order = actual.get("order")
                actual_items = sorted((i["sku"], i["quantity"]) for i in order["items"]) if order else []
                expected_items = sorted((i["sku"], i["quantity"]) for i in case.get("items", []))
                intents = case["intent"] if isinstance(case["intent"], list) else [case["intent"]]
                routes = case["route"] if isinstance(case["route"], list) else [case["route"]]
                intent_ok = actual.get("intent") in intents
                extraction_ok = actual_items == expected_items and set(case.get("missing", [])) <= set(actual.get("missing_fields", []))
                conn = connect(settings.db_path)
                stock_after = {r["sku"]: r["quantity"] for r in conn.execute("SELECT sku,quantity FROM inventory")}
                db_items = sorted((r["sku"], r["quantity"]) for r in conn.execute("SELECT sku,quantity FROM order_items"))
                states = [r[0] for r in conn.execute("SELECT status FROM orders")]
                conn.close()
                unchanged_items = "database_items" not in case or db_items == sorted((i["sku"], i["quantity"]) for i in case["database_items"])
                totals_ok = "total" not in case or (order and order["total"] == case["total"])
                validation_ok = status == 200 and count == case["order_count"] and bool(order) == bool(expected_items) and stock_before == stock_after and unchanged_items and totals_ok and all(s == "pending_confirmation" for s in states)
                routing_ok = actual.get("route") in routes and actual.get("error_type") == case.get("error_type")
                response_ok = bool(actual.get("reply")) and case.get("contains", "") in actual.get("reply", "")
                scores = dict(zip(["intent", "extraction", "validation", "routing", "response"],
                                  [2 if value else 0 for value in [intent_ok, extraction_ok, validation_ok, routing_ok, response_ok]]))
                results.append({"id": case["id"], "group": case["group"], "fault_injected": bool(fault),
                                "passed": all([intent_ok, extraction_ok, validation_ok, routing_ok, response_ok]),
                                "scores": scores, "expected_route": case["route"], "actual_route": actual.get("route"),
                                "http_status": status, "order_count": count, "items": actual_items,
                                "spec": case.get("spec"), "message_count": len(case["messages"]),
                                "stock_unchanged": stock_before == stock_after, "database_items": db_items,
                                "error_type": actual.get("error_type"), "interpretation_source": actual.get("interpretation_source"),
                                "turns": [{k: t.get(k) for k in ("intent", "route", "missing_fields", "error_type", "interpretation_source", "reply")} for t in turns],
                                "provider_calls": recorded.calls,
                                "reply": actual.get("reply"), "latency_ms": round((time.monotonic() - start) * 1000, 2)})
                print(f"{case['id']}: {'PASS' if results[-1]['passed'] else 'FAIL'} - {actual.get('route')} {actual.get('error_type') or ''}", flush=True)
    output.mkdir(parents=True, exist_ok=True)
    report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "provider": provider,
              "model_id": "fake-rules-v1" if provider == "fake" else base.model_id,
              "prompt_version": PROMPT_VERSION, "temperature": 0 if provider == "gemini" else None,
              "llm_max_retries": base.llm_max_retries, "llm_timeout_seconds": base.llm_timeout,
              "real_model_attempts": sum(len(r["provider_calls"]) for r in results if not r["fault_injected"]) if provider == "gemini" else 0,
              "scoring": "Automatic 0/2 proxy checks; human 0/1/2 review remains required for model-quality claims.",
              "passed": sum(r["passed"] for r in results), "total": len(results), "cases": results}
    (output / f"evaluation_{provider}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [f"# Evaluation: {report['model_id']}", "", f"Prompt: `{PROMPT_VERSION}`. UTC: {report['timestamp_utc']}.", "",
             f"Kết quả: {report['passed']}/{report['total']} case đạt các kiểm tra tự động.", "",
             "Đây là kiểm tra workflow bằng rule/fixture khi provider=fake, không phải benchmark Gemini. Các case F dùng lỗi chèn chủ động, kể cả khi chọn Gemini.", "",
             "Điểm 0/2 là proxy tự động cho rubric: intent, extraction, validation, routing, response. Cần người đọc chấm lại 0/1/2 để đánh giá chất lượng ngôn ngữ và groundedness đầy đủ.", "",
             "| Case | Nhóm | Route thực tế | Intent | Extract | Validate | Route | Reply | Pass |", "|---|---|---|---:|---:|---:|---:|---:|---|"]
    for r in results:
        s = r["scores"]
        lines.append(f"| {r['id']} | {r['group']} | {r['actual_route']} | {s['intent']} | {s['extraction']} | {s['validation']} | {s['routing']} | {s['response']} | {'PASS' if r['passed'] else 'FAIL'} |")
    (output / f"evaluation_{provider}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{provider}: {report['passed']}/{report['total']} passed; {output / f'evaluation_{provider}.md'}")
    return report["passed"] == report["total"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["fake", "gemini"], default="fake")
    parser.add_argument("--output", type=Path, default=ROOT / "sample_results")
    parser.add_argument("--case-id", action="append", help="Chọn từng case để giữ quota model")
    parser.add_argument("--pace-seconds", type=float, default=6, help="Giãn cách các lượt Gemini thật")
    parser.add_argument("--case-file", type=Path, help="Bộ case bổ sung theo đề bài")
    args = parser.parse_args()
    if args.provider == "gemini" and not args.case_id:
        parser.error("Chọn --case-id H01 khi gọi Gemini thật để chủ động kiểm soát quota.")
    raise SystemExit(0 if evaluate(args.provider, args.output, args.case_id, args.pace_seconds if args.provider == "gemini" else 0, args.case_file) else 1)
