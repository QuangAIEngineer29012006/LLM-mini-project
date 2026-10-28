import json
import sqlite3
import tempfile
import unittest

from shop_db import conversation_service as conv
from shop_db import corpus_service as corpus
from shop_db import order_service as orders
from shop_db.corpus_errors import (
    CorpusAccessDenied,
    CorpusNotFound,
    CorpusValidationError,
    CorpusVersionConflict,
)
from shop_db.corpus_files import fingerprint
from shop_db.corpus_seed import ensure_corpus_seeded, reset_and_seed_all
from shop_db.db import connect, latest_version, migrate
from shop_db.seed import reset_and_seed, seed_catalog
from shop_db.sku_sync_service import REPO_ROOT, load_manifest, sync_from_manifest
from tests.corpus_helpers import MANIFEST_V1_0, MANIFEST_V1_1, CorpusTestCase, copy_corpus_to_tmp
from tests.helpers import CTX, DELIVERY


class CorpusMetadataTests(CorpusTestCase):
    def test_01_schema_version_tables_and_views(self):
        self.assertEqual(latest_version(), 3)
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 3)

        tables = {
            r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for expected_table in (
            "corpus_releases",
            "corpus_documents",
            "corpus_document_versions",
            "corpus_document_products",
            "corpus_document_skus",
            "corpus_sync_events",
        ):
            self.assertIn(expected_table, tables)

        views = {
            r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='view'")
        }
        self.assertIn("v_corpus_active_documents", views)
        self.assertIn("v_corpus_sku_status", views)

    def test_02_upgrade_v2_to_v3_preserves_orders_and_conversations(self):
        conn = connect(":memory:")
        try:
            self.assertEqual(migrate(conn, target_version=2), 2)
            seed_catalog(conn)
            draft = orders.create_draft_order(
                conn, CTX, "owner-v2", [{"sku": "TSH-BLK-M", "quantity": 2}], DELIVERY
            )
            c = conv.create_conversation(conn, "owner-v2")
            conv.add_message(conn, c["id"], "user", "Cho tôi hỏi áo thun đen size M")

            self.assertEqual(migrate(conn), 3)
            self.assertEqual(orders.get_order(conn, draft["id"])["total_amount"], 300000)
            self.assertEqual(len(conv.get_messages(conn, c["id"])), 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM products").fetchone()[0], 7)
        finally:
            conn.close()

    def test_03_legacy_reset_and_seed_twice_keeps_working_and_clears_corpus(self):
        self.assertEqual(self.count("corpus_documents"), 17)
        first = reset_and_seed(self.conn)
        second = reset_and_seed(self.conn)
        self.assertEqual(first, second)
        self.assertEqual(self.count("corpus_documents"), 0)
        self.assertEqual(self.count("corpus_releases"), 0)

    def test_04_v1_0_sync_and_idempotent_ensure_seeded(self):
        status = corpus.corpus_status(self.conn)
        self.assertEqual(status["active_release"], "1.0.0")
        self.assertEqual(
            status["documents_by_access"],
            {"public": 12, "staff": 3, "admin": 2},
        )
        self.assertGreaterEqual(self.sync_result["report"]["stats"]["public_sections"], 30)

        again = ensure_corpus_seeded(self.conn, manifest_path=MANIFEST_V1_0)
        self.assertTrue(again["already_seeded"])
        self.assertEqual(again["corpus_release"], "1.0.0")

        full_reset = reset_and_seed_all(self.conn, manifest_path=MANIFEST_V1_0)
        self.assertEqual(full_reset["corpus_release"], "1.0.0")
        self.assertEqual(full_reset["documents_active"], 17)

    def test_05_role_filtering_in_sql_and_invalid_roles(self):
        cust_docs = corpus.list_documents(self.conn, "customer")
        pub_docs = corpus.list_documents(self.conn, "public")
        staff_docs = corpus.list_documents(self.conn, "staff")
        admin_docs = corpus.list_documents(self.conn, "admin")

        cust_ids = {d["doc_id"] for d in cust_docs}
        staff_ids = {d["doc_id"] for d in staff_docs}
        admin_ids = {d["doc_id"] for d in admin_docs}

        self.assertEqual(cust_ids, {d["doc_id"] for d in pub_docs})
        self.assertEqual(len(cust_ids), 12)
        self.assertFalse(any(i.startswith(("DOC-INT-", "DOC-ADM-")) for i in cust_ids))

        self.assertEqual(len(staff_ids), 15)
        self.assertTrue(any(i.startswith("DOC-INT-") for i in staff_ids))
        self.assertFalse(any(i.startswith("DOC-ADM-") for i in staff_ids))

        self.assertEqual(len(admin_ids), 17)
        self.assertIn("DOC-ADM-HR-POLICY", admin_ids)

        ao_docs = corpus.list_documents(self.conn, "customer", doc_type="product_spec", category="Áo")
        self.assertEqual({d["doc_id"] for d in ao_docs}, {"DOC-PRD-001", "DOC-PRD-002", "DOC-PRD-007"})

        for bad_role in ("guest", "", None, 123):
            with self.assertRaises(CorpusValidationError):
                corpus.allowed_access_levels(bad_role)

    def test_06_check_document_access_distinguishes_denied_not_found_and_inactive(self):
        denied_adm = corpus.check_document_access(self.conn, "DOC-ADM-HR-POLICY", "customer")
        self.assertEqual(denied_adm, {"allowed": False, "reason": "access_denied"})

        denied_staff = corpus.check_document_access(self.conn, "DOC-ADM-HR-POLICY", "staff")
        self.assertEqual(denied_staff, {"allowed": False, "reason": "access_denied"})

        missing = corpus.check_document_access(self.conn, "DOC-NOPE-999", "customer")
        self.assertEqual(missing, {"allowed": False, "reason": "not_found"})

        with self.assertRaises(CorpusAccessDenied):
            corpus.get_document(self.conn, "DOC-INT-PROMO-RULES", "customer")
        with self.assertRaises(CorpusNotFound):
            corpus.get_document(self.conn, "DOC-NOPE-999", "admin")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = copy_corpus_to_tmp(tmp)
            mpath = tmp_root / "data_config" / "corpus_manifest_v1.0.json"
            manifest = load_manifest(mpath)
            manifest["corpus_release"] = "1.0.1"
            manifest["documents"] = [
                d for d in manifest["documents"] if d["doc_id"] != "DOC-FAQ-PUBLIC"
            ]
            mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            sync_from_manifest(self.conn, mpath, repo_root=tmp_root)

            inactive_chk = corpus.check_document_access(self.conn, "DOC-FAQ-PUBLIC", "customer")
            self.assertEqual(inactive_chk, {"allowed": False, "reason": "inactive"})

    def test_07_resolve_citation_verifies_source_and_permissions(self):
        cit = corpus.resolve_citation(self.conn, "DOC-POL-WARRANTY", role="customer")
        self.assertEqual(cit["doc_id"], "DOC-POL-WARRANTY")
        self.assertEqual(cit["version"], "1.0")
        self.assertEqual(cit["source"], "data_config/corpus/policies/pol_bao_hanh.md")
        self.assertTrue(cit["is_active_version"])
        self.assertTrue(cit["source_exists"])
        self.assertTrue(cit["sha256_matches"])

        with self.assertRaises(CorpusAccessDenied):
            corpus.resolve_citation(self.conn, "DOC-INT-SOP-SUPPORT", role="customer")
        with self.assertRaises(CorpusNotFound):
            corpus.resolve_citation(self.conn, "DOC-POL-WARRANTY", version="9.9", role="customer")

    def test_08_and_09_upgrade_v1_1_and_rollback_to_v1_0(self):
        before_cap_docs = {d["doc_id"] for d in corpus.documents_for_sku(self.conn, "CAP-BLK-F", "customer")}
        self.assertNotIn("DOC-POL-RETURN", before_cap_docs)

        up = sync_from_manifest(self.conn, MANIFEST_V1_1, actor_type="admin", actor_id="adm-1")
        self.assertEqual(up["corpus_release"], "1.1.0")
        self.assertEqual(corpus.corpus_status(self.conn)["active_release"], "1.1.0")

        pol_v11 = corpus.get_document(self.conn, "DOC-POL-RETURN", "customer")
        self.assertEqual(pol_v11["version"], "1.1")
        self.assertIn("CAP-BLK-F", pol_v11["skus"])

        old_cit = corpus.resolve_citation(self.conn, "DOC-POL-RETURN", version="1.0", role="customer")
        self.assertFalse(old_cit["is_active_version"])
        self.assertTrue(old_cit["source_exists"])

        cap_docs_v11 = {d["doc_id"] for d in corpus.documents_for_sku(self.conn, "CAP-BLK-F", "customer")}
        self.assertIn("DOC-POL-RETURN", cap_docs_v11)

        with self.assertRaises(CorpusAccessDenied):
            corpus.list_versions(self.conn, "DOC-POL-RETURN", role="staff")
        versions = corpus.list_versions(self.conn, "DOC-POL-RETURN", role="admin")
        self.assertEqual([(v["version"], v["is_active"]) for v in versions], [("1.0", 0), ("1.1", 1)])

        rb = sync_from_manifest(self.conn, MANIFEST_V1_0, actor_type="admin", actor_id="adm-1")
        self.assertEqual(rb["corpus_release"], "1.0.0")
        self.assertEqual(corpus.get_document(self.conn, "DOC-POL-RETURN", "customer")["version"], "1.0")
        versions_after = corpus.list_versions(self.conn, "DOC-POL-RETURN", role="admin")
        self.assertEqual([(v["version"], v["is_active"]) for v in versions_after], [("1.0", 1), ("1.1", 0)])
        cap_docs_after = {d["doc_id"] for d in corpus.documents_for_sku(self.conn, "CAP-BLK-F", "customer")}
        self.assertNotIn("DOC-POL-RETURN", cap_docs_after)

    def test_10_partial_unique_index_blocks_two_active_versions_or_releases(self):
        sync_from_manifest(self.conn, MANIFEST_V1_1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE corpus_document_versions SET is_active = 1"
                " WHERE doc_id = 'DOC-POL-RETURN' AND version = '1.0'"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE corpus_releases SET is_active = 1 WHERE release = '1.0.0'"
            )

    def test_11_version_immutability_blocks_content_change_under_same_version(self):
        before_sha = corpus.get_document(self.conn, "DOC-FAQ-PUBLIC", "customer")["content_sha256"]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = copy_corpus_to_tmp(tmp)
            faq_path = tmp_root / "data_config" / "corpus" / "guides" / "faq_khach_hang.md"
            faq_path.write_text(
                faq_path.read_text(encoding="utf-8") + "\n## Mục bổ sung trái quy tắc\nNội dung khác.\n",
                encoding="utf-8",
            )
            new_fp = fingerprint(faq_path)
            mpath = tmp_root / "data_config" / "corpus_manifest_v1.0.json"
            manifest = load_manifest(mpath)
            manifest["corpus_release"] = "1.0.9"
            for doc in manifest["documents"]:
                if doc["doc_id"] == "DOC-FAQ-PUBLIC":
                    doc.update(new_fp)
            mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            with self.assertRaises(CorpusVersionConflict):
                sync_from_manifest(self.conn, mpath, repo_root=tmp_root)

        self.assertEqual(
            corpus.get_document(self.conn, "DOC-FAQ-PUBLIC", "customer")["content_sha256"],
            before_sha,
        )
        self.assertEqual(corpus.corpus_status(self.conn)["active_release"], "1.0.0")

    def test_12_sync_events_are_append_only_and_free_of_document_body(self):
        ev = self.conn.execute("SELECT id, details FROM corpus_sync_events LIMIT 1").fetchone()
        self.assertIsNotNone(ev)
        self.assertNotIn("30.000", ev["details"])
        self.assertNotIn("150.000", ev["details"])

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE corpus_sync_events SET actor_id = 'hacked' WHERE id = ?", (ev["id"],))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM corpus_sync_events WHERE id = ?", (ev["id"],))


if __name__ == "__main__":
    unittest.main()

