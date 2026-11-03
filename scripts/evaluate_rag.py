"""Evaluate the PDF-backed RAG pipeline end-to-end.

The PDF is the source of truth. The runtime path under test is:
PDF -> manifest/hash -> SQLite extracted sections -> active index -> retrieval
-> selected context -> answer/citations.

Examples:
    python scripts/evaluate_rag.py --split dev
    python scripts/evaluate_rag.py --split test
    python scripts/evaluate_rag.py --split test --provider gemini --embedding gemini --pace 6 --timeout 25

Important:
- Tune only on --split dev.
- Run --split test only after freezing code/configuration.
- Citation label match is a relevance-label diagnostic, NOT semantic claim verification.
"""
import argparse
import hashlib
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
from database.shop_db import corpus_service  # noqa: E402
from database.shop_db.corpus_files import fingerprint  # noqa: E402
from database.shop_db.db import connect  # noqa: E402
from database.shop_db.text_utils import normalize  # noqa: E402
from src.rag.answer import GeminiGenerator  # noqa: E402
from src.rag.retriever import select_context  # noqa: E402

KEYS = {"demo_staff_key": "eval-staff-key", "demo_admin_key": "eval-admin-key"}
CASES_PATH = ROOT / "artifacts" / "evaluation_cases.jsonl"
JUDGMENTS_PATH = ROOT / "artifacts" / "relevance_judgments.jsonl"
# Relevance labels are authored against the deterministic fake index. Convert those IDs
# to (doc_id, section) so the same judgments can evaluate either PDF-backed index.
JUDGED_CHUNKS = ROOT / "artifacts" / "index" / "1.1.0-fake" / "chunks.jsonl"


class PacedClient:
    """Apply a minimum interval between router/generator provider calls."""

    def __init__(self, client, pace):
        self.client = client
        self.pace = pace
        self.last = None
        self.model_id = client.model_id

    def _wait(self):
        if self.last is not None:
            time.sleep(max(0.0, self.pace - (time.monotonic() - self.last)))
        self.last = time.monotonic()

    def generate(self, *args):
        self._wait()
        return self.client.generate(*args)

    def complete(self, *args):
        self._wait()
        return self.client.complete(*args)


def load_jsonl(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file đánh giá: {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_judgments():
    """Map labelled fake chunk IDs to PDF-derived (doc_id, section) identities."""
    section_by_chunk = {
        row["chunk_id"]: (row["doc_id"], row["section"])
        for row in load_jsonl(JUDGED_CHUNKS)
    }
    judgments = {}
    unknown = []
    for row in load_jsonl(JUDGMENTS_PATH):
        identity = section_by_chunk.get(row["chunk_id"])
        if identity is None:
            unknown.append(row["chunk_id"])
            continue
        judgments.setdefault(row["case_id"], {})[identity] = int(row["relevance"])
    if unknown:
        raise ValueError(
            "Relevance judgments trỏ tới chunk ID không còn trong index chuẩn 1.1.0-fake: "
            + ", ".join(unknown[:8])
        )
    return judgments


def validate_pdf_pipeline(app, db_path):
    """Fail fast if the active RAG bundle is not built from the active, intact PDF corpus."""
    knowledge = app.state.knowledge
    bundle = knowledge.bundle
    if bundle is None:
        raise RuntimeError(f"RAG index chưa sẵn sàng: {knowledge.problem}")

    manifest_path = knowledge.manifest_path
    if manifest_path is None or not Path(manifest_path).is_file():
        raise RuntimeError("Không tìm thấy manifest PDF của index active.")

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    release = manifest.get("corpus_release")
    if bundle.corpus_release != release:
        raise RuntimeError(
            f"Release không khớp: index={bundle.corpus_release}, manifest={release}"
        )

    conn = connect(db_path)
    try:
        active = conn.execute(
            "SELECT release FROM corpus_releases WHERE is_active = 1"
        ).fetchone()
        if active is None or active["release"] != release:
            raise RuntimeError(
                f"SQLite đang active release {active['release'] if active else None}, "
                f"nhưng index/manifest dùng {release}."
            )

        manifest_docs = {d["doc_id"]: d for d in manifest.get("documents", [])}
        if not manifest_docs:
            raise RuntimeError("Manifest không có documents.")

        for doc_id, entry in manifest_docs.items():
            source_rel = entry.get("source_path", "")
            source_path = ROOT / source_rel
            if Path(source_rel).suffix.lower() != ".pdf":
                raise RuntimeError(f"{doc_id}: source_path không phải PDF: {source_rel}")
            if not source_path.is_file():
                raise RuntimeError(f"{doc_id}: thiếu file PDF {source_rel}")
            actual_hash = fingerprint(source_path)["content_sha256"]
            if actual_hash != entry.get("content_sha256"):
                raise RuntimeError(f"{doc_id}: SHA-256 PDF không khớp manifest.")

            version = conn.execute(
                "SELECT id, content_sha256 FROM corpus_document_versions "
                "WHERE doc_id = ? AND version = ?",
                (doc_id, entry["version"]),
            ).fetchone()
            if version is None:
                raise RuntimeError(f"{doc_id}: chưa có bản trích xuất trong SQLite.")
            if version["content_sha256"] != entry["content_sha256"]:
                raise RuntimeError(f"{doc_id}: hash trong SQLite khác PDF manifest.")
            section_count = conn.execute(
                "SELECT COUNT(*) FROM corpus_document_sections WHERE version_id = ?",
                (version["id"],),
            ).fetchone()[0]
            if section_count < 1:
                raise RuntimeError(f"{doc_id}: SQLite không có section trích xuất từ PDF.")

        # Every active chunk must point to a document/version/path in the same PDF manifest.
        seen_ids = set()
        for level, chunks in bundle.chunks.items():
            for chunk in chunks:
                if chunk.chunk_id in seen_ids:
                    raise RuntimeError(f"Chunk ID bị trùng: {chunk.chunk_id}")
                seen_ids.add(chunk.chunk_id)
                entry = manifest_docs.get(chunk.doc_id)
                if entry is None:
                    raise RuntimeError(f"Chunk {chunk.chunk_id} không thuộc manifest active.")
                if chunk.version != entry["version"] or chunk.source != entry["source_path"]:
                    raise RuntimeError(f"Chunk {chunk.chunk_id} lệch version/source so với PDF.")
                if chunk.access_level != level or chunk.access_level != entry["access_level"]:
                    raise RuntimeError(f"Chunk {chunk.chunk_id} lệch phân quyền.")
        if len(seen_ids) != bundle.manifest.get("chunk_count"):
            raise RuntimeError("Tổng chunk trong bundle không khớp index manifest.")
    finally:
        conn.close()

    return {
        "corpus_release": release,
        "manifest": str(Path(manifest_path).relative_to(ROOT)),
        "pdf_documents": len(manifest_docs),
        "active_index_id": bundle.index_id,
        "active_chunk_count": len(seen_ids),
        "validation": "passed",
    }


def _owner_order_count(db_path, token):
    """Read the order count for the exact session created for this evaluation case."""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT owner_id FROM api_sessions WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Không tìm thấy session vừa tạo cho evaluation case.")
        owner_id = row["owner_id"]
        count = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE owner_id = ? AND status != 'cart'",
            (owner_id,),
        ).fetchone()[0]
        return count
    finally:
        conn.close()


def _citation_checks(app, db_path, role, citations):
    """Validate citation existence, active PDF hash/version and role access in SQLite."""
    bundle = app.state.knowledge.bundle
    levels = corpus_service.allowed_access_levels(role)
    conn = connect(db_path)
    resolved = []
    role_safe = []
    for citation in citations:
        chunk = bundle.chunk(citation["chunk_id"], levels)
        role_safe.append(chunk is not None)
        if chunk is None:
            resolved.append(False)
            continue
        try:
            source = corpus_service.resolve_citation(
                conn, citation["doc_id"], citation.get("version"), role=role, repo_root=ROOT
            )
            valid = bool(
                source["source_exists"]
                and source["sha256_matches"]
                and source["is_active_version"]
                and source["source"] == citation.get("source")
            )
        except Exception:
            valid = False
        resolved.append(valid)
    conn.close()
    return resolved, role_safe


def run_case(client, app, case, relevant, db_path):
    role = case["role"]
    headers = (
        {"X-Demo-Role": role, "X-Demo-Key": KEYS[f"demo_{role}_key"]}
        if role in {"staff", "admin"} else {}
    )
    session_response = client.post("/api/session", headers=headers)
    session_response.raise_for_status()
    token = session_response.json()["token"]
    auth = {"Authorization": "Bearer " + token}

    response = client.post("/api/chat", headers=auth, json={"message": case["query"]})
    response.raise_for_status()
    body = response.json()

    orders = _owner_order_count(db_path, token)
    route = body.get("route")
    expected_route = case["expected_route"]
    accepted_routes = case.get("acceptable_routes", [expected_route])
    if expected_route == "not_draft_created":
        route_ok = route != "draft_created"
    else:
        route_ok = route in accepted_routes

    knowledge = body.get("knowledge") or {}
    status = knowledge.get("status")
    accepted_statuses = case.get("acceptable_statuses", [case.get("expected_status")])
    status_ok = status in accepted_statuses

    # A catalog_empty result is a valid safe outcome for a no-evidence question when
    # the case explicitly accepts that route; it is not a missing/failed RAG answer.
    if case["type"] == "no_evidence" and route == "catalog_empty" and route_ok:
        status_ok = True

    orders_ok = "orders" not in case or orders == case["orders"]
    answer_text = knowledge.get("answer") or body.get("reply", "")
    normalized_answer = normalize(answer_text)
    evidence_ok = all(normalize(span) in normalized_answer for span in case.get("evidence_spans", []))

    citations = knowledge.get("citations", [])
    citation_resolved, citation_role_safe = _citation_checks(app, db_path, role, citations)
    citation_ids = [c["chunk_id"] for c in citations]
    citation_relevant = [
        (c["doc_id"], c["section"]) in relevant for c in citations
    ]

    retrieval = None
    if relevant:
        query = case.get("retrieval_query", case["query"])
        hits = app.state.knowledge.search(query, role, k=10)
        ranked = [(h.chunk.doc_id, h.chunk.section) for h in hits]
        first_rank = {}
        for rank, identity in enumerate(ranked, start=1):
            first_rank.setdefault(identity, rank)
        relevant_ranks = [
            first_rank[identity] for identity in relevant if identity in first_rank
        ]
        primary = [identity for identity, grade in relevant.items() if grade == 2]
        selected_context = select_context(
            hits[:5], query, app.state.knowledge.min_score
        )
        context_ids = {(h.chunk.doc_id, h.chunk.section) for h in selected_context}
        retrieval = {
            "top5_chunk_ids": [h.chunk.chunk_id for h in hits[:5]],
            "hit_at_3": any(rank <= 3 for rank in relevant_ranks),
            "recall_at_5": (
                sum(rank <= 5 for rank in relevant_ranks) / len(relevant)
                if relevant else None
            ),
            "mrr": 1 / min(relevant_ranks) if relevant_ranks else 0.0,
            "evidence_coverage": (
                sum(identity in context_ids for identity in primary) / len(primary)
                if primary else None
            ),
            "retrieved_sections": [
                {"doc_id": h.chunk.doc_id, "section": h.chunk.section, "rank": h.rank}
                for h in hits[:10]
            ],
            "selected_context_sections": [
                {"doc_id": h.chunk.doc_id, "section": h.chunk.section}
                for h in selected_context
            ],
        }

    citations_all_resolved = all(citation_resolved)
    citations_role_safe = all(citation_role_safe)
    # Do not fail a case solely because a legitimate supporting citation is outside
    # the hand-labelled relevant set. The label set is not exhaustive claim-level truth.
    contract_passed = (
        route_ok and status_ok and orders_ok and evidence_ok
        and citations_all_resolved and citations_role_safe
    )
    # Keep a strict, legacy-comparable pass flag, but expose its limitation:
    # section-level relevance labels are not exhaustive claim-level support judgments.
    strict_label_passed = contract_passed and all(citation_relevant)

    return {
        "id": case["id"],
        "split": case["split"],
        "type": case["type"],
        "role": role,
        "query": case["query"],
        "route": route,
        "expected_route": case["expected_route"],
        "accepted_routes": accepted_routes,
        "route_ok": route_ok,
        "status": status,
        "expected_status": case.get("expected_status"),
        "accepted_statuses": accepted_statuses,
        "status_ok": status_ok,
        "orders": orders,
        "orders_ok": orders_ok,
        "evidence_spans_ok": evidence_ok,
        "citations": citation_ids,
        "citation_sources_resolved": citation_resolved,
        "citation_role_safe": citation_role_safe,
        "citation_label_matches": citation_relevant,
        "citation_label_match_count": sum(citation_relevant),
        "citation_count": len(citations),
        "answer": answer_text,
        "retrieval": retrieval,
        "contract_passed": contract_passed,
        "strict_relevance_label_passed": strict_label_passed,
    }


def _rate(values):
    values = list(values)
    return round(sum(values) / len(values), 3) if values else None


def summarize(results):
    retrieval = [row["retrieval"] for row in results if row["retrieval"] is not None]
    answerable = [row for row in results if row["expected_status"] == "answered"]
    no_evidence = [row for row in results if row["type"] == "no_evidence"]
    access_denied = [row for row in results if row["type"] == "access_denied"]
    all_citations = [row for row in results if row["citation_count"]]
    total_citations = sum(row["citation_count"] for row in results)

    return {
        "cases": len(results),
        "contract_passed": sum(row["contract_passed"] for row in results),
        "strict_relevance_label_passed": sum(
            row["strict_relevance_label_passed"] for row in results
        ),
        "hit_at_3": _rate(row["hit_at_3"] for row in retrieval),
        "recall_at_5": _rate(row["recall_at_5"] for row in retrieval),
        "mrr": _rate(row["mrr"] for row in retrieval),
        "evidence_coverage_multi": _rate(
            row["retrieval"]["evidence_coverage"]
            for row in results
            if row["type"] == "multi" and row["retrieval"]
            and row["retrieval"]["evidence_coverage"] is not None
        ),
        "citation_source_valid_rate": (
            round(
                sum(sum(row["citation_sources_resolved"]) for row in all_citations)
                / total_citations, 3
            ) if total_citations else None
        ),
        "citation_role_safe_rate": (
            round(
                sum(sum(row["citation_role_safe"]) for row in all_citations)
                / total_citations, 3
            ) if total_citations else None
        ),
        # Diagnostic only: relevance labels are section-level and not exhaustive.
        "citation_label_match_rate": (
            round(
                sum(row["citation_label_match_count"] for row in results)
                / total_citations, 3
            ) if total_citations else None
        ),
        "answer_evidence_span_rate": _rate(row["evidence_spans_ok"] for row in answerable),
        "no_evidence_safe_rate": _rate(
            row["status_ok"] and not row["citations"] and row["route_ok"]
            for row in no_evidence
        ),
        "false_refusal_rate": _rate(
            row["status"] != "answered" for row in answerable
        ),
        "access_denied_rate": _rate(
            row["status"] == "access_denied"
            and not row["citations"]
            and all(row["citation_role_safe"])
            for row in access_denied
        ),
        "mixed_route_action_rate": _rate(
            row["route_ok"] and row["orders_ok"] and row["status_ok"]
            for row in results if row["type"] == "mixed"
        ),
        "route_accuracy": _rate(row["route_ok"] for row in results),
        "safety_pass_rate": _rate(
            row["contract_passed"] for row in results if row["type"] == "safety"
        ),
        "claim_support_rate": None,
        "claim_support_note": (
            "Chưa tự động đo semantic entailment. Cần người đánh giá đối chiếu từng claim "
            "trong answer với đúng PDF section/citation."
        ),
    }


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--provider", choices=["fake", "gemini"], default="fake",
                        help="LLM router + answer generator")
    parser.add_argument("--embedding", choices=["fake", "gemini"], default="fake",
                        help="Embedding/index provider")
    parser.add_argument("--label", default="", help="Output suffix, e.g. baseline / improved")
    parser.add_argument("--pace", type=float, default=0,
                        help="Minimum seconds between router/generator provider calls")
    parser.add_argument("--timeout", type=float,
                        help="Override LLM_TIMEOUT_SECONDS (1-120)")
    parser.add_argument("--unweighted", action="store_true",
                        help="Disable IDF weighting for the fake extractive generator")
    args = parser.parse_args(argv)

    cases = [
        case for case in load_jsonl(CASES_PATH)
        if args.split == "all" or case["split"] == args.split
    ]
    judgments = load_judgments()

    with tempfile.TemporaryDirectory() as folder:
        db_path = str(Path(folder) / "evaluation.db")
        base_settings = (
            Settings.from_env()
            if "gemini" in (args.provider, args.embedding)
            else Settings(db_path=db_path)
        )
        settings = replace(
            base_settings,
            db_path=db_path,
            llm_provider=args.provider,
            rag_embedding_provider=args.embedding,
            request_limit=10000,
            session_limit=1000,
            chat_limit=1000,
            **KEYS,
        )
        if args.timeout is not None:
            if not 1 <= args.timeout <= 120:
                parser.error("--timeout phải nằm trong khoảng 1-120 giây")
            settings = replace(settings, llm_timeout=args.timeout)

        app = create_app(settings)
        app.state.knowledge.weighted_extraction = not args.unweighted
        if args.provider == "gemini" and args.pace:
            app.state.llm_client = PacedClient(app.state.llm_client, args.pace)
            app.state.knowledge.llm = GeminiGenerator(app.state.llm_client)

        with TestClient(app) as client:
            corpus_validation = validate_pdf_pipeline(app, db_path)
            results = [
                run_case(client, app, case, judgments.get(case["id"], {}), db_path)
                for case in cases
            ]

    summary = summarize(results)
    suffix = f"_{args.label}" if args.label else ""
    output_name = (
        f"evaluation_results_{args.split}_{args.provider}"
        f"{'_gemini-embedding' if args.embedding == 'gemini' else ''}{suffix}.json"
    )
    output_path = ROOT / "artifacts" / output_name
    output_path.write_text(
        json.dumps(
            {
                "run": {
                    "split": args.split,
                    "provider": args.provider,
                    "embedding": args.embedding,
                    "weighted_extraction": not args.unweighted,
                    "corpus_validation": corpus_validation,
                    "test_split_policy": (
                        "Held-out only if no tuning or code/config changes were made "
                        "after inspecting this split."
                    ),
                },
                "summary": summary,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(
        {"summary": summary, "corpus_validation": corpus_validation,
         "output": str(output_path.relative_to(ROOT))},
        ensure_ascii=False, indent=2
    ))
    for row in results:
        if not row["contract_passed"]:
            print(
                f"FAIL {row['id']} route={row['route']} "
                f"status={row['status']} orders={row['orders']} "
                f"evidence={row['evidence_spans_ok']} "
                f"citation_resolved={row['citation_sources_resolved']}"
            )


if __name__ == "__main__":
    main()
