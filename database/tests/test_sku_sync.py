import contextlib
import io
import json
import tempfile
import unittest

from shop_db.corpus_errors import SkuSyncMismatch
from shop_db.corpus_files import fingerprint
from shop_db.sku_sync_service import (
    REPO_ROOT,
    load_manifest,
    main as sync_cli_main,
    sync_from_manifest,
    validate_manifest,
    verify_catalog_sync,
)
from tests.corpus_helpers import MANIFEST_V1_0, MANIFEST_V1_1, CorpusTestCase, copy_corpus_to_tmp


class SkuSyncTests(CorpusTestCase):
    def test_01_both_v1_0_and_v1_1_manifests_pass_cleanly(self):
        for mpath in (MANIFEST_V1_0, MANIFEST_V1_1):
            manifest = load_manifest(mpath)
            rep = verify_catalog_sync(self.conn, manifest, repo_root=REPO_ROOT)
            self.assertTrue(rep["ok"], msg=rep["errors"])
            self.assertEqual(rep["errors"], [])
            self.assertEqual(rep["warnings"], [])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = sync_cli_main(["--check", "--manifest", str(mpath)])
            self.assertEqual(rc, 0)
            self.assertIn("[PASS]", buf.getvalue())

    def test_02_all_skus_exist_and_missing_product_coverage_detected(self):
        linked = {
            r["sku"] for r in self.conn.execute("SELECT DISTINCT sku FROM corpus_document_skus").fetchall()
        }
        all_db_skus = {
            r["sku"] for r in self.conn.execute("SELECT sku FROM product_variants").fetchall()
        }
        self.assertEqual(linked, all_db_skus)

        manifest = load_manifest(MANIFEST_V1_0)
        manifest["documents"] = [d for d in manifest["documents"] if d["doc_id"] != "DOC-PRD-004"]
        rep = verify_catalog_sync(self.conn, manifest, repo_root=REPO_ROOT)
        self.assertFalse(rep["ok"])
        codes = {e["code"] for e in rep["errors"]}
        self.assertIn("missing_catalog_coverage", codes)

    def test_03_unknown_sku_rejected_without_mutating_db_and_logs_rejection(self):
        before_events = self.count("corpus_sync_events")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = copy_corpus_to_tmp(tmp)
            mpath = tmp_root / "data_config" / "corpus_manifest_v1.0.json"
            manifest = load_manifest(mpath)
            manifest["corpus_release"] = "9.9.9"
            for doc in manifest["documents"]:
                if doc["doc_id"] == "DOC-POL-WARRANTY":
                    doc["skus"].append("NOPE-SKU-99")
                    doc["product_ids"].append(999)
            mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            with self.assertRaises(SkuSyncMismatch) as ctx:
                sync_from_manifest(self.conn, mpath, repo_root=tmp_root)
            err_codes = {e["code"] for e in ctx.exception.details["report"]["errors"]}
            self.assertIn("unknown_sku", err_codes)
            self.assertIn("unknown_product_id", err_codes)

        active_rel = self.conn.execute(
            "SELECT release FROM corpus_releases WHERE is_active = 1"
        ).fetchone()["release"]
        self.assertEqual(active_rel, "1.0.0")
        self.assertEqual(self.count("corpus_sync_events"), before_events + 1)
        last_ev = self.conn.execute(
            "SELECT event_type, corpus_release, details FROM corpus_sync_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(last_ev["event_type"], "sync_rejected")
        self.assertEqual(last_ev["corpus_release"], "9.9.9")

    def test_04_cross_product_sku_in_manifest_or_markdown_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = copy_corpus_to_tmp(tmp)
            prd1_path = tmp_root / "data_config" / "corpus" / "products" / "prd_01_ao_thun_basic_cotton.md"
            prd1_path.write_text(
                prd1_path.read_text(encoding="utf-8") + "\nTham chiếu nhầm mã HOD-GRY-M ở đây.\n",
                encoding="utf-8",
            )
            new_fp = fingerprint(prd1_path)
            manifest = load_manifest(tmp_root / "data_config" / "corpus_manifest_v1.0.json")
            for doc in manifest["documents"]:
                if doc["doc_id"] == "DOC-PRD-001":
                    doc.update(new_fp)

            rep_undeclared = verify_catalog_sync(self.conn, manifest, repo_root=tmp_root)
            self.assertIn("undeclared_sku_in_text", {e["code"] for e in rep_undeclared["errors"]})

            for doc in manifest["documents"]:
                if doc["doc_id"] == "DOC-PRD-001":
                    doc["skus"].append("HOD-GRY-M")
            rep_cross = verify_catalog_sync(self.conn, manifest, repo_root=tmp_root)
            cross_codes = {e["code"] for e in rep_cross["errors"]}
            self.assertIn("sku_product_mismatch", cross_codes)
            self.assertIn("product_spec_sku_set_mismatch", cross_codes)

    def test_05_discontinued_doc_marked_active_is_rejected(self):
        manifest = load_manifest(MANIFEST_V1_0)
        for doc in manifest["documents"]:
            if doc["doc_id"] == "DOC-PRD-007":
                doc["catalog_status"] = "active"
        rep = verify_catalog_sync(self.conn, manifest, repo_root=REPO_ROOT)
        self.assertIn("catalog_status_mismatch", {e["code"] for e in rep["errors"]})

    def test_06_and_07_live_sellable_view_and_product_deactivation_detection(self):
        jkt_var = self.conn.execute(
            "SELECT is_active FROM product_variants WHERE sku = 'JKT-NVY-L'"
        ).fetchone()
        jkt_prod = self.conn.execute("SELECT is_active FROM products WHERE id = 7").fetchone()
        self.assertEqual((jkt_var["is_active"], jkt_prod["is_active"]), (1, 0))

        jkt_view = self.conn.execute(
            "SELECT live_sellable, declared_catalog_status FROM v_corpus_sku_status"
            " WHERE doc_id = 'DOC-PRD-007' AND sku = 'JKT-NVY-L'"
        ).fetchone()
        self.assertEqual((jkt_view["live_sellable"], jkt_view["declared_catalog_status"]), (0, "discontinued"))

        self.conn.execute("UPDATE products SET is_active = 0 WHERE id = 5")
        cap_rows = self.conn.execute(
            "SELECT sku, live_sellable FROM v_corpus_sku_status WHERE doc_id = 'DOC-PRD-005'"
        ).fetchall()
        self.assertEqual({r["sku"] for r in cap_rows}, {"CAP-NVY-F", "CAP-BLK-F"})
        self.assertTrue(all(r["live_sellable"] == 0 for r in cap_rows))

        manifest = load_manifest(MANIFEST_V1_0)
        rep = verify_catalog_sync(self.conn, manifest, repo_root=REPO_ROOT)
        cap_errs = [e for e in rep["errors"] if e["doc_id"] == "DOC-PRD-005"]
        self.assertTrue(any(e["code"] == "catalog_status_mismatch" for e in cap_errs))

    def test_08_db_price_change_triggers_price_mismatch(self):
        self.conn.execute("UPDATE product_variants SET price = 160000 WHERE sku = 'TSH-BLK-M'")
        manifest = load_manifest(MANIFEST_V1_0)
        rep = verify_catalog_sync(self.conn, manifest, repo_root=REPO_ROOT)
        self.assertFalse(rep["ok"])
        price_errs = [e for e in rep["errors"] if e["code"] == "price_mismatch"]
        self.assertEqual(len(price_errs), 1)
        self.assertEqual((price_errs[0]["doc_id"], price_errs[0]["sku"]), ("DOC-PRD-001", "TSH-BLK-M"))

    def test_09_file_and_metadata_corruptions_produce_exact_error_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = copy_corpus_to_tmp(tmp)
            base_manifest = load_manifest(tmp_root / "data_config" / "corpus_manifest_v1.0.json")

            # 1) hash_mismatch + size_mismatch khi sửa nội dung mà không đổi manifest
            faq_file = tmp_root / "data_config" / "corpus" / "guides" / "faq_khach_hang.md"
            orig_faq = faq_file.read_text(encoding="utf-8")
            faq_file.write_text(orig_faq + "\nThêm dòng mới.\n", encoding="utf-8")
            r_hash = validate_manifest(base_manifest, repo_root=tmp_root)
            self.assertIn("hash_mismatch", {e["code"] for e in r_hash["errors"]})
            faq_file.write_text(orig_faq, encoding="utf-8")

            # 2) file_empty
            faq_file.write_text("   \n", encoding="utf-8")
            r_empty = validate_manifest(base_manifest, repo_root=tmp_root)
            self.assertIn("file_empty", {e["code"] for e in r_empty["errors"]})

            # 3) file_missing
            faq_file.unlink()
            r_missing = validate_manifest(base_manifest, repo_root=tmp_root)
            self.assertIn("file_missing", {e["code"] for e in r_missing["errors"]})

            # Khôi phục rồi kiểm tra hardcoded_stock + front_matter_mismatch
            faq_file.write_text(
                orig_faq.replace("version: 1.0", "version: 2.5") + "\nKho hiện còn 15 cái sẵn.\n",
                encoding="utf-8",
            )
            fp_mut = fingerprint(faq_file)
            mut_manifest = json.loads(json.dumps(base_manifest))
            for d in mut_manifest["documents"]:
                if d["doc_id"] == "DOC-FAQ-PUBLIC":
                    d.update(fp_mut)
            r_fm_stock = validate_manifest(mut_manifest, repo_root=tmp_root)
            codes_fm = {e["code"] for e in r_fm_stock["errors"]}
            self.assertIn("front_matter_mismatch", codes_fm)
            self.assertIn("hardcoded_stock", codes_fm)

            # 4) duplicate_doc_id & missing_field
            dup_manifest = json.loads(json.dumps(base_manifest))
            faq_file.write_text(orig_faq, encoding="utf-8")
            dup_doc = dict(dup_manifest["documents"][0])
            dup_manifest["documents"].append(dup_doc)
            bad_doc = dict(dup_manifest["documents"][1])
            bad_doc["doc_id"] = "DOC-BAD-AUTHOR"
            bad_doc["author"] = ""
            dup_manifest["documents"].append(bad_doc)
            r_dup = validate_manifest(dup_manifest, repo_root=tmp_root)
            codes_dup = {e["code"] for e in r_dup["errors"]}
            self.assertIn("duplicate_doc_id", codes_dup)
            self.assertIn("missing_field", codes_dup)

    def test_10_path_traversal_or_backslash_in_source_path_rejected(self):
        for bad_path in (
            "data_config/corpus/../corpus_manifest_v1.0.json",
            "data_config\\corpus\\guides\\faq_khach_hang.md",
            "docs/API.md",
            "/data_config/corpus/guides/faq_khach_hang.md",
        ):
            manifest = load_manifest(MANIFEST_V1_0)
            manifest["documents"][0]["source_path"] = bad_path
            rep = validate_manifest(manifest, repo_root=REPO_ROOT)
            self.assertIn("invalid_source_path", {e["code"] for e in rep["errors"]}, msg=bad_path)


if __name__ == "__main__":
    unittest.main()
