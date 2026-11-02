import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from shop_db.corpus_errors import CorpusFileIntegrityError
from shop_db.corpus_files import (
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
    build_corpus_pdfs,
    check_corpus_pdfs,
    export_manifest_pdf,
    extract_markdown_from_pdf,
    main as pdf_cli_main,
    render_markdown_to_pdf_bytes,
)
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


if __name__ == "__main__":
    unittest.main()
