"""Evaluate retrieval, answers, citations, safety and routing on artifacts/evaluation_cases.jsonl.

python scripts/evaluate_rag.py --split dev            (fake LLM, offline)
python scripts/evaluate_rag.py --split test --provider gemini   (uses quota)
"""
import argparse
import json
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.config import Settings  # noqa: E402
from backend.main import create_app  # noqa: E402
from database.shop_db.db import connect  # noqa: E402
from database.shop_db.text_utils import normalize  # noqa: E402
from src.rag.answer import GeminiGenerator  # noqa: E402
from src.rag.retriever import retrieve, select_context  # noqa: E402

KEYS = {"demo_staff_key": "eval-staff-key", "demo_admin_key": "eval-admin-key"}


class PacedClient:
    """Keeps at least `pace` seconds between provider calls so a run stays under the per-minute limit."""

    def __init__(self, client, pace):
        self.client, self.pace, self.last = client, pace, None
        self.model_id = client.model_id

    def _wait(self):
        if self.last is not None:
            time.sleep(max(0, self.pace - (time.monotonic() - self.last)))
        self.last = time.monotonic()

    def generate(self, *args):
        self._wait()
        return self.client.generate(*args)

    def complete(self, *args):
        self._wait()
        return self.client.complete(*args)


def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def run_case(client, app, case, relevant, db_path):
    headers = {"X-Demo-Role": case["role"], "X-Demo-Key": KEYS[f"demo_{case['role']}_key"]} if case["role"] != "customer" else {}
    token = client.post("/api/session", headers=headers).json()["token"]
    auth = {"Authorization": "Bearer " + token}
    body = client.post("/api/chat", headers=auth, json={"message": case["query"]}).json()
    knowledge = body.get("knowledge")
    conn = connect(db_path)
    try:
        owner = conn.execute("SELECT owner_id FROM api_sessions WHERE token_hash = (SELECT token_hash FROM api_sessions ORDER BY rowid DESC LIMIT 1)").fetchone()[0]
        orders = conn.execute("SELECT COUNT(*) FROM orders WHERE owner_id=? AND status != 'cart'", (owner,)).fetchone()[0]
    finally:
        conn.close()
    route = body.get("route")
    expected = case["expected_route"]
    if expected == "not_draft_created":
        route_ok = route != "draft_created"
    else:
        route_ok = route in case.get("acceptable_routes", [expected])
    status = knowledge["status"] if knowledge else None
    status_ok = status in case.get("acceptable_statuses", [case["expected_status"]])
    orders_ok = "orders" not in case or orders == case["orders"]
    text = normalize(body.get("reply", ""))
    evidence_ok = all(normalize(span) in text for span in case["evidence_spans"])
    citations = knowledge["citations"] if knowledge else []
    bundle = app.state.knowledge.bundle
    resolved = [c for c in citations if bundle.chunk(c["chunk_id"], ("public", "staff", "admin")) and (ROOT / c["source"]).is_file()]
    supported = [c for c in citations if c["chunk_id"] in relevant]

    retrieval = None
    if relevant:
        query = case.get("retrieval_query", case["query"])
        hits = retrieve(bundle, app.state.knowledge.embedder, query, case["role"], k=10)
        ranked = [h.chunk.chunk_id for h in hits]
        ranks = [ranked.index(cid) + 1 for cid in relevant if cid in ranked]
        primary = [cid for cid, grade in relevant.items() if grade == 2]
        context = [h.chunk.chunk_id for h in select_context(hits[:5], query, app.state.knowledge.embedder.min_score)]
        retrieval = {"top5": ranked[:5], "hit@3": any(r <= 3 for r in ranks),
                     "recall@5": sum(r <= 5 for r in ranks) / len(relevant),
                     "mrr": 1 / min(ranks) if ranks else 0.0,
                     "evidence_coverage": sum(cid in context for cid in primary) / len(primary)}
    return {"id": case["id"], "split": case["split"], "type": case["type"], "role": case["role"], "query": case["query"],
            "route": route, "expected_route": expected, "route_ok": route_ok,
            "status": status, "expected_status": case["expected_status"], "status_ok": status_ok,
            "orders": orders, "orders_ok": orders_ok, "evidence_ok": evidence_ok,
            "citations": [c["chunk_id"] for c in citations], "citations_resolved": len(resolved),
            "citations_supported": len(supported), "answer": body.get("reply", ""), "retrieval": retrieval,
            "passed": route_ok and status_ok and orders_ok and evidence_ok and len(supported) == len(citations)}


def summarize(results):
    def rate(items):
        return round(sum(items) / len(items), 3) if items else None
    retrieval = [r["retrieval"] for r in results if r["retrieval"]]
    knowledge_answerable = [r for r in results if r["expected_status"] == "answered"]
    cited = sum(len(r["citations"]) for r in results)
    return {
        "cases": len(results), "passed": sum(r["passed"] for r in results),
        "hit@3": rate([x["hit@3"] for x in retrieval]), "recall@5": rate([x["recall@5"] for x in retrieval]),
        "mrr": rate([x["mrr"] for x in retrieval]),
        "evidence_coverage_multi": rate([r["retrieval"]["evidence_coverage"] for r in results if r["type"] == "multi"]),
        "citation_resolve_rate": round(sum(r["citations_resolved"] for r in results) / cited, 3) if cited else None,
        "citation_support_rate": round(sum(r["citations_supported"] for r in results) / cited, 3) if cited else None,
        "answer_evidence_span_rate": rate([r["evidence_ok"] for r in knowledge_answerable]),
        "no_evidence_safe_rate": rate([r["status_ok"] and not r["citations"] for r in results if r["type"] == "no_evidence"]),
        "false_refusal_rate": rate([r["status"] != "answered" for r in knowledge_answerable]),
        "access_denied_rate": rate([r["status"] == "access_denied" and not r["citations"] for r in results if r["type"] == "access_denied"]),
        "mixed_route_action_rate": rate([r["route_ok"] and r["orders_ok"] and r["status_ok"] for r in results if r["type"] == "mixed"]),
        "route_accuracy": rate([r["route_ok"] for r in results]),
        "safety_pass_rate": rate([r["passed"] for r in results if r["type"] == "safety"]),
    }


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--provider", choices=["fake", "gemini"], default="fake", help="Router + answer generator")
    parser.add_argument("--embedding", choices=["fake", "gemini"], default="fake", help="Index/embedding provider")
    parser.add_argument("--label", default="", help="Suffix for the output file, e.g. baseline / improved")
    parser.add_argument("--pace", type=float, default=0, help="Minimum seconds between provider calls (Gemini)")
    parser.add_argument("--timeout", type=float, help="Override LLM_TIMEOUT_SECONDS for this run (1-30)")
    parser.add_argument("--unweighted", action="store_true",
                        help="Baseline: plain term-overlap sentence selection instead of IDF weighting")
    args = parser.parse_args(argv)
    cases = [c for c in load_jsonl(ROOT / "artifacts/evaluation_cases.jsonl") if args.split == "all" or c["split"] == args.split]
    judgments = {}
    for row in load_jsonl(ROOT / "artifacts/relevance_judgments.jsonl"):
        judgments.setdefault(row["case_id"], {})[row["chunk_id"]] = row["relevance"]
    with tempfile.TemporaryDirectory() as folder:
        db_path = str(Path(folder) / "eval.db")
        base = Settings.from_env() if "gemini" in (args.provider, args.embedding) else Settings(db_path=db_path)
        settings = replace(base, db_path=db_path, llm_provider=args.provider, rag_embedding_provider=args.embedding,
                           request_limit=10000, session_limit=1000, chat_limit=1000, **KEYS)
        if args.timeout:
            settings = replace(settings, llm_timeout=args.timeout)
        app = create_app(settings)
        app.state.knowledge.weighted_extraction = not args.unweighted
        if args.provider == "gemini" and args.pace:
            app.state.llm_client = PacedClient(app.state.llm_client, args.pace)
            app.state.knowledge.llm = GeminiGenerator(app.state.llm_client)
        with TestClient(app) as client:
            results = [run_case(client, app, case, judgments.get(case["id"], {}), db_path) for case in cases]
    summary = summarize(results)
    embedding = "" if args.embedding == "fake" else "_gemini-embedding"
    name = f"evaluation_results_{args.split}_{args.provider}{embedding}{'_' + args.label if args.label else ''}.json"
    (ROOT / "artifacts" / name).write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for r in results:
        if not r["passed"]:
            print(f"FAIL {r['id']} route={r['route']} (exp {r['expected_route']}) status={r['status']} (exp {r['expected_status']}) "
                  f"orders={r['orders']} evidence={r['evidence_ok']} cites={r['citations']}")


if __name__ == "__main__":
    main()
