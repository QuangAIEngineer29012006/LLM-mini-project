"""Run the corpus 1.0.0 -> 1.1.0 -> rollback scenario through the real API on a temporary DB/index.

python scripts/reindex_demo.py   (writes artifacts/reindex_evidence.json)
"""
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.config import Settings  # noqa: E402
from backend.main import create_app  # noqa: E402
from database.shop_db.db import connect  # noqa: E402
from src.rag.embedder import FakeEmbedder  # noqa: E402
from src.rag.index import IndexBundle, activate, build_bundle  # noqa: E402

KEYS = {"demo_staff_key": "reindex-staff-key", "demo_admin_key": "reindex-admin-key"}
VERIFY = ["Đổi size hoặc màu do đổi ý được hỗ trợ trong bao lâu?",
          "Nón lưỡi trai CAP-NVY-F có được đổi do đổi ý không?"]


def section_diff(old_bundle, new_bundle, doc_id):
    def sections(bundle):
        return {c.section: (c.chunk_id, hashlib.sha256(c.text.split("\n", 1)[1].encode()).hexdigest()[:12])
                for c in bundle.chunks["public"] if c.doc_id == doc_id}
    old, new = sections(old_bundle), sections(new_bundle)
    return {"added": [{"section": s, "chunk_id": new[s][0]} for s in new if s not in old],
            "removed": [{"section": s, "chunk_id": old[s][0]} for s in old if s not in new],
            "changed": [{"section": s, "old": old[s][0], "new": new[s][0]} for s in new if s in old and old[s][1] != new[s][1]],
            "unchanged": sorted(s for s in new if s in old and old[s][1] == new[s][1])}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    evidence = {}
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        index_root = folder / "artifacts/index"
        pointer = folder / "artifacts/index_manifest.json"
        bundles = {}
        for release, manifest in (("1.0.0", "corpus_manifest_v1.0.json"), ("1.1.0", "corpus_manifest_v1.1.json")):
            path, meta = build_bundle(ROOT / "data_config" / manifest, FakeEmbedder(), out_root=index_root)
            committed = ROOT / "artifacts/index" / path.name / "index_manifest.json"
            same = committed.is_file() and json.loads(committed.read_text(encoding="utf-8"))["files"] == meta["files"]
            bundles[release] = {"index_id": meta["index_id"], "chunk_count": meta["chunk_count"],
                                "chunks_by_access": meta["chunks_by_access"], "files": meta["files"],
                                "matches_committed_bundle": same}
        evidence["snapshots"] = bundles
        evidence["diff_DOC-POL-RETURN"] = section_diff(IndexBundle(index_root / "1.0.0-fake"),
                                                        IndexBundle(index_root / "1.1.0-fake"), "DOC-POL-RETURN")
        activate(index_root / "1.0.0-fake", pointer)
        settings = Settings(db_path=str(folder / "shop.db"), rag_index_pointer=str(pointer),
                            request_limit=10000, session_limit=1000, chat_limit=1000, **KEYS)
        app = create_app(settings)
        with TestClient(app) as client:
            def session(role=None):
                headers = {"X-Demo-Role": role, "X-Demo-Key": KEYS[f"demo_{role}_key"]} if role else {}
                return {"Authorization": "Bearer " + client.post("/api/session", headers=headers).json()["token"]}

            customer, admin = session(), session("admin")

            def ask(label):
                rows = []
                for question in VERIFY:
                    body = client.post("/api/knowledge", headers=customer, json={"question": question}).json()
                    rows.append({"question": question, "status": body["status"], "answer": body["answer"],
                                 "citations": [c["chunk_id"] for c in body["citations"]]})
                state = client.get("/api/admin/index", headers=admin).json()
                return {"step": label, "index_id": state["index"]["index_id"], "index_release": state["index"]["corpus_release"],
                        "db_release": state["corpus"]["active_release"], "ready": state["index"]["ready"],
                        "cache_entries_after_queries": state["index"]["cache_entries"], "answers": rows}

            steps = [ask("start on 1.0.0")]
            for release, label in (("1.1.0", "activate 1.1.0"), ("1.0.0", "rollback to 1.0.0"), ("1.1.0", "re-activate 1.1.0")):
                reply = client.post("/api/admin/reindex", headers=admin, json={"action": "activate", "release": release}).json()
                step = ask(label)
                step["cache_entries_right_after_activate"] = reply["result"]["cache_entries"]
                steps.append(step)
            evidence["steps"] = steps
            active = app.state.knowledge.bundle
            evidence["active_index_versions_of_DOC-POL-RETURN"] = sorted(
                {c.version for level in active.chunks.values() for c in level if c.doc_id == "DOC-POL-RETURN"})

            leaks, probes = [], 0
            for level in ("staff", "admin"):
                for chunk in active.chunks[level]:
                    probes += 1
                    result = app.state.knowledge.answer(None, chunk.text.split("\n", 1)[1][:400], "customer")
                    debug = result["debug"]
                    seen = [r["chunk_id"] for r in debug.get("retrieval", [])] + debug.get("context", []) + \
                           [c["chunk_id"] for c in result["citations"]]
                    leaks += [cid for cid in seen if cid.startswith(("DOC-INT", "DOC-ADM"))]
            cached = [cid for (index_id, role, _), value in app.state.knowledge.cache.items() if role == "customer"
                      for cid in [r["chunk_id"] for r in value["debug"].get("retrieval", [])] + [c["chunk_id"] for c in value["citations"]]]
            evidence["customer_isolation"] = {"internal_chunks_probed": probes, "internal_ids_in_candidates_context_citations": leaks,
                                              "internal_ids_in_customer_cache": [c for c in cached if c.startswith(("DOC-INT", "DOC-ADM"))]}

        conn = connect(settings.db_path)
        try:
            sync_events = [dict(r) for r in conn.execute(
                "SELECT event_type, actor_type, corpus_release FROM corpus_sync_events ORDER BY id")]
            audit = [r["details"] or "" for r in conn.execute("SELECT details FROM audit_logs")]
            actions = [r[0] for r in conn.execute("SELECT action FROM audit_logs ORDER BY id")]
        finally:
            conn.close()
        internal_sentence = active.chunks["admin"][0].text.split("\n", 1)[1][:60]
        evidence["logs"] = {
            "corpus_sync_events": sync_events,
            "audit_actions": sorted(set(actions)),
            "audit_contains_internal_text": any(internal_sentence in d for d in audit),
            "audit_contains_demo_key": any(k in d for d in audit for k in KEYS.values()),
            "audit_contains_phone_number": any(re.search(r"0\d{9}", d) for d in audit),
        }
    out = ROOT / "artifacts/reindex_evidence.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"steps": [(s["step"], s["index_release"], s["db_release"], s["answers"][0]["citations"]) for s in evidence["steps"]],
                      "isolation": evidence["customer_isolation"], "logs": evidence["logs"]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
