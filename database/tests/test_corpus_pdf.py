import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from shop_db import corpus_service as corpus
from shop_db.corpus_errors import CorpusAccessDenied, CorpusFileIntegrityError
from shop_db.corpus_files import (
    extract_sections,
    find_hardcoded_stock,
    find_sku_tokens,
    fingerprint,
    parse_front_matter,
    parse_variant_table,
    read_normalized,
    section_titles,
)
from shop_db.corpus_pdf import (
    REPO_ROOT,
    _ensure_fonts_registered,
    build_corpus_pdfs,
    check_corpus_pdfs,
    export_manifest_pdf,
    extract_markdown_from_pdf,
    main as pdf_cli_main,
    render_markdown_to_pdf_bytes,
)
from shop_db.db import connect, migrate
from shop_db.seed import seed_catalog
from shop_db.sku_sync_service import register_pdf_document, sync_from_manifest
from tests.corpus_helpers import MANIFEST_V1_0, MANIFEST_V1_1, copy_corpus_to_tmp


class CorpusPdfTests(unittest.TestCase):
    def test_01_deterministic_pdf_bytes_and_clean_visual_typography(self):
        md_sample = """---
doc_id: DOC-PRD-001
title: Áo thun basic cotton — thông số, biến thể và bảo quản
version: 1.0
access_level: public
author: TV1 - Database & Business Data
effective_date: 2026-10-01
data_notice: Dữ liệu mô phỏng cho mini-project, không phải dữ liệu thật.
---

## Tổng quan
Áo thun basic cotton giặt dưới 40°C, kích thước 1m58–1m68, trạng thái `pending_confirmation`.

## Biến thể và giá tham khảo
| SKU | Màu | Size | Giá tham khảo (VND) |
|---|---|---|---|
| TSH-BLK-M | Đen | M | 150.000 |
| TSH-WHT-L | Trắng | L | 150.000 |

## Bảo quản
- Không dùng chất tẩy mạnh làm phai màu Đen.
"""
        b1 = render_markdown_to_pdf_bytes(md_sample)
        b2 = render_markdown_to_pdf_bytes(md_sample.replace("\n", "\r\n"))
        self.assertTrue(b1.startswith(b"%PDF-"))
        self.assertEqual(b1, b2)

        # Kiểm tra trang hiển thị PDF thô sạch 100% cú pháp Markdown và có Bookmarks
        reader = PdfReader(io.BytesIO(b1))
        raw_page_text = "\n".join((pg.extract_text() or "") for pg in reader.pages)
        self.assertNotIn("## ", raw_page_text)
        self.assertNotIn("---", raw_page_text)
        self.assertNotIn("doc_id:", raw_page_text)
        self.assertNotIn("`", raw_page_text)
        self.assertGreaterEqual(len(reader.outline), 3)

        with tempfile.TemporaryDirectory() as tmp:
            pdf_file = Path(tmp) / "sample.pdf"
            pdf_file.write_bytes(b1)
            text, raw = read_normalized(pdf_file)
            self.assertEqual(raw, b1)
            self.assertEqual(fingerprint(pdf_file)["file_size_bytes"], len(b1))
            self.assertIn("Áo thun basic cotton", text)
            self.assertIn("40°C", text)
            self.assertIn("## Tổng quan", text)  # Tương thích trực tiếp với chunker RAG (TV2)
            self.assertEqual(parse_front_matter(text)["doc_id"], "DOC-PRD-001")
            self.assertEqual(
                section_titles(text),
                ["Tổng quan", "Biến thể và giá tham khảo", "Bảo quản"],
            )
            self.assertEqual(
                parse_variant_table(text, "Biến thể và giá tham khảo"),
                [
                    {"sku": "TSH-BLK-M", "color": "Đen", "size": "M", "price": 150000},
                    {"sku": "TSH-WHT-L", "color": "Trắng", "size": "L", "price": 150000},
                ],
            )

    def test_02_all_18_corpus_pdfs_valid_and_no_markdown_left_in_corpus_dir(self):
        corpus_dir = REPO_ROOT / "data_config" / "corpus"
        pdf_files = sorted(corpus_dir.rglob("*.pdf"))
        md_files = sorted(corpus_dir.rglob("*.md"))
        self.assertEqual(len(pdf_files), 18)
        self.assertEqual(md_files, [])

        chk = check_corpus_pdfs(repo_root=REPO_ROOT)
        self.assertTrue(chk["ok"], msg=chk["errors"])
        self.assertEqual(chk["checked_pairs"], 18)

        for pdf_path in pdf_files:
            recovered_md = extract_markdown_from_pdf(pdf_path)
            pdf_text, _ = read_normalized(pdf_path)
            self.assertEqual(parse_front_matter(recovered_md), parse_front_matter(pdf_text))
            self.assertEqual(section_titles(recovered_md), section_titles(pdf_text))
            self.assertEqual(find_sku_tokens(recovered_md), find_sku_tokens(pdf_text))
            self.assertEqual(find_hardcoded_stock(recovered_md), find_hardcoded_stock(pdf_text))

    def test_03_manifests_point_to_pdf_and_manifest_summary_pdfs_exist(self):
        for mpath in (MANIFEST_V1_0, MANIFEST_V1_1):
            mpdf = mpath.with_suffix(".pdf")
            self.assertTrue(mpdf.is_file(), msg=f"Thiếu báo cáo PDF cho {mpath.name}")
            pdf_text, _ = read_normalized(mpdf)
            self.assertIn("BÁO CÁO CORPUS METADATA MANIFEST", pdf_text)
            self.assertIn("DOC-PRD-001", pdf_text)
            self.assertIn("DOC-ADM-HR-POLICY", pdf_text)

    def test_04_invalid_or_empty_pdf_raises_integrity_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with self.assertRaises(CorpusFileIntegrityError) as ctx_miss:
                read_normalized(base / "missing.pdf")
            self.assertEqual(ctx_miss.exception.details["code_detail"], "file_missing")

            empty_pdf = base / "empty.pdf"
            empty_pdf.write_bytes(b"")
            with self.assertRaises(CorpusFileIntegrityError) as ctx_empty:
                read_normalized(empty_pdf)
            self.assertEqual(ctx_empty.exception.details["code_detail"], "file_empty")

            bad_pdf = base / "corrupt.pdf"
            bad_pdf.write_bytes(b"%PDF-1.4\nGARBAGE_STREAM_WITHOUT_EOF")
            with self.assertRaises(CorpusFileIntegrityError) as ctx_bad:
                read_normalized(bad_pdf)
            self.assertIn(
                ctx_bad.exception.details["code_detail"],
                ("file_invalid_pdf", "file_empty"),
            )

    def test_05_cli_build_and_check_roundtrip_in_temp_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = copy_corpus_to_tmp(tmp)
            target_pdf = tmp_root / "data_config" / "corpus" / "policies" / "pol_bao_hanh.pdf"
            md_src = extract_markdown_from_pdf(target_pdf)
            target_pdf.with_suffix(".md").write_text(md_src, encoding="utf-8")
            target_pdf.unlink()
            self.assertFalse(check_corpus_pdfs(repo_root=tmp_root)["ok"])

            res = build_corpus_pdfs(update_manifests=True, export_manifest_pdfs=True, repo_root=tmp_root)
            self.assertEqual(len(res["corpus_pdfs"]), 1)
            self.assertEqual(len(res["updated_manifests"]), 2)
            self.assertEqual(len(res["manifest_pdfs"]), 2)
            self.assertTrue(check_corpus_pdfs(repo_root=tmp_root)["ok"])

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = pdf_cli_main(["--check"])
            self.assertEqual(rc, 0)
            self.assertIn("[PASS]", buf.getvalue())

            out_pdf = export_manifest_pdf(tmp_root / "data_config" / "corpus_manifest_v1.1.json")
            self.assertTrue(out_pdf.is_file())

    def test_06_pdf_texts_and_sections_stored_directly_in_sqlite_db(self):
        conn = connect(":memory:")
        try:
            migrate(conn)
            seed_catalog(conn)
            res = sync_from_manifest(conn, MANIFEST_V1_0, repo_root=REPO_ROOT)
            self.assertEqual(res["sections_indexed"], 85)
            self.assertEqual(corpus.corpus_status(conn)["sections_active"], 85)

            # Toàn bộ 18 file PDF gốc vẫn giữ nguyên trên đĩa
            self.assertEqual(len(list((REPO_ROOT / "data_config" / "corpus").rglob("*.pdf"))), 18)

            # Đọc trực tiếp văn bản và các mục đã bóc từ SQLite DB (không cần mở lại PDF)
            bag_doc = corpus.get_document_text(conn, "DOC-PRD-006", role="customer")
            self.assertIn("Balo laptop", bag_doc["content_text"])
            self.assertIn("BAG-GRY-15", bag_doc["body_text"])
            war_doc = corpus.get_document_text(conn, "DOC-POL-WARRANTY", role="customer")
            self.assertIn("12 tháng", war_doc["body_text"])
            self.assertGreaterEqual(len(bag_doc["sections"]), 4)
            for sec in bag_doc["sections"]:
                self.assertEqual(
                    bag_doc["content_text"][sec["char_start"]:sec["char_end"]],
                    sec["section_text"],
                )

            # Kiểm tra phân quyền ngay trong truy vấn văn bản DB
            with self.assertRaises(CorpusAccessDenied):
                corpus.get_document_text(conn, "DOC-ADM-HR-POLICY", role="customer")
            with self.assertRaises(CorpusAccessDenied):
                corpus.list_document_sections(conn, role="customer", doc_id="DOC-INT-PROMO-RULES")

            cust_texts = corpus.list_corpus_texts(conn, role="customer")
            self.assertEqual(len(cust_texts), 12)
            self.assertTrue(all(d["content_text"].strip() and len(d["sections"]) >= 3 for d in cust_texts))

            # Nâng cấp lên v1.1: DB lưu cả text bản 1.0 lẫn 1.1 của DOC-POL-RETURN
            res_11 = sync_from_manifest(conn, MANIFEST_V1_1, repo_root=REPO_ROOT)
            self.assertEqual(res_11["sections_indexed"], 86)
            v10_txt = corpus.get_document_text(conn, "DOC-POL-RETURN", role="customer", version="1.0")
            v11_txt = corpus.get_document_text(conn, "DOC-POL-RETURN", role="customer", version="1.1")
            self.assertIn("7 ngày", v10_txt["body_text"])
            self.assertIn("14 ngày", v11_txt["body_text"])
        finally:
            conn.close()

    def test_07_external_arbitrary_pdf_auto_extracted_into_db_without_text_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = copy_corpus_to_tmp(tmp)
            font_reg, font_bold = _ensure_fonts_registered()

            # 1) PDF bên ngoài có đề mục kiểu văn bản hành chính ("Điều 1.", "Điều 2."), KHÔNG có front-matter
            ext_pdf = tmp_root / "data_config" / "corpus" / "guides" / "cam_nang_giat_ui_ngoai.pdf"
            buf = io.BytesIO()
            c = canvas.Canvas(buf)
            c.setFont(font_bold, 14)
            c.drawString(50, 780, "Cẩm nang bảo quản trang phục mùa mưa")
            c.setFont(font_bold, 12)
            c.drawString(50, 750, "Điều 1. Quy tắc phơi trang phục")
            c.setFont(font_reg, 11)
            c.drawString(50, 732, "Phơi nơi thoáng gió, tránh ánh nắng gắt trực tiếp lên sợi vải.")
            c.setFont(font_bold, 12)
            c.drawString(50, 704, "Điều 2. Quy tắc giặt và ngâm")
            c.setFont(font_reg, 11)
            c.drawString(50, 686, "Không ngâm chung quần áo màu đậm với áo trắng quá 15 phút.")
            c.save()
            ext_bytes = buf.getvalue()
            ext_pdf.write_bytes(ext_bytes)

            # 2) PDF bên ngoài dạng đoạn văn tự do hoàn toàn KHÔNG có bất kỳ tiêu đề mục nào
            plain_pdf = tmp_root / "data_config" / "corpus" / "guides" / "ghi_chu_dong_goi_ngoai.pdf"
            buf2 = io.BytesIO()
            c2 = canvas.Canvas(buf2)
            c2.setFont(font_reg, 11)
            c2.drawString(50, 780, "Mọi kiện hàng phụ kiện đều được bọc chống sốc hai lớp trước khi bàn giao bưu cục.")
            c2.save()
            plain_pdf.write_bytes(buf2.getvalue())

            mpath = tmp_root / "data_config" / "corpus_manifest_v1.1.json"
            reg = register_pdf_document(
                ext_pdf,
                mpath,
                doc_id="DOC-GDE-RAIN-CARE",
                title="Cẩm nang bảo quản trang phục mùa mưa",
                doc_type="guide",
                category="general",
                access_level="public",
                version="1.0",
                repo_root=tmp_root,
            )
            self.assertEqual(reg["sections_extracted"], 2)
            # File PDF gốc bên ngoài hoàn toàn không bị mất hay biến đổi byte nào
            self.assertEqual(ext_pdf.read_bytes(), ext_bytes)

            reg_plain = register_pdf_document(
                plain_pdf,
                mpath,
                doc_id="DOC-GDE-PACKING-NOTE",
                title="Ghi chú đóng gói phụ kiện",
                doc_type="guide",
                category="general",
                access_level="public",
                version="1.0",
                repo_root=tmp_root,
            )
            self.assertEqual(reg_plain["sections_extracted"], 1)

            conn = connect(":memory:")
            try:
                migrate(conn)
                seed_catalog(conn)
                sync_res = sync_from_manifest(conn, mpath, repo_root=tmp_root)
                self.assertEqual(sync_res["documents_active"], 19)

                ext_db = corpus.get_document(conn, "DOC-GDE-RAIN-CARE", role="customer", include_content=True)
                self.assertIn("thoáng gió", ext_db["body_text"])
                self.assertEqual(len(ext_db["sections"]), 2)
                self.assertEqual(parse_front_matter(ext_db["content_text"])["doc_id"], "DOC-GDE-RAIN-CARE")
                self.assertEqual(len(extract_sections(ext_db["content_text"])), 2)

                plain_db = corpus.get_document_text(conn, "DOC-GDE-PACKING-NOTE", role="customer")
                self.assertIn("chống sốc hai lớp", plain_db["body_text"])
                self.assertEqual(len(plain_db["sections"]), 1)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
