import os
import tempfile
import unittest
from pathlib import Path

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


SAMPLE_MD = """---
doc_id: DOC-PRD-001
title: Áo thun basic cotton — thông số, biến thể và bảo quản
version: 1.0
access_level: public
author: TV1 - Database & Business Data
effective_date: 2026-10-01
data_notice: Dữ liệu mô phỏng cho mini-project, không phải dữ liệu thật.
---

## Tổng quan
Áo thun basic cotton phù hợp mặc hằng ngày, tham khảo thêm chính sách tại DOC-POL-RETURN.

## Biến thể và giá tham khảo
| SKU | Màu | Size | Giá tham khảo (VND) |
|---|---|---|---|
| TSH-BLK-M | Đen | M | 150.000 |
| TSH-WHT-L | Trắng | L | 150.000 |

## Bảo quản
Sản phẩm đổi trả khi còn nguyên tem mác, chưa qua giặt ủi.
"""


class CorpusFilesTests(unittest.TestCase):
    def test_crlf_and_lf_produce_identical_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            lf_path = Path(tmp) / "lf.md"
            crlf_path = Path(tmp) / "crlf.md"
            lf_bytes = SAMPLE_MD.replace("\r\n", "\n").encode("utf-8")
            crlf_bytes = lf_bytes.replace(b"\n", b"\r\n")
            lf_path.write_bytes(lf_bytes)
            crlf_path.write_bytes(crlf_bytes)

            self.assertEqual(fingerprint(lf_path), fingerprint(crlf_path))
            text, norm = read_normalized(crlf_path)
            self.assertNotIn("\r", text)
            self.assertNotIn(b"\r", norm)

    def test_rejects_missing_bom_empty_and_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with self.assertRaises(CorpusFileIntegrityError) as ctx_missing:
                read_normalized(base / "missing.md")
            self.assertEqual(ctx_missing.exception.details["code_detail"], "file_missing")

            bom_file = base / "bom.md"
            bom_file.write_bytes(b"\xef\xbb\xbf## Xin chao\nNoi dung")
            with self.assertRaises(CorpusFileIntegrityError) as ctx_bom:
                read_normalized(bom_file)
            self.assertEqual(ctx_bom.exception.details["code_detail"], "file_has_bom")

            empty_file = base / "empty.md"
            empty_file.write_bytes(b"   \n\t\r\n  ")
            with self.assertRaises(CorpusFileIntegrityError) as ctx_empty:
                read_normalized(empty_file)
            self.assertEqual(ctx_empty.exception.details["code_detail"], "file_empty")

            bad_utf8 = base / "latin.md"
            bad_utf8.write_bytes(b"## Tieu de\n\xff\xfe khong phai utf8")
            with self.assertRaises(CorpusFileIntegrityError) as ctx_utf8:
                read_normalized(bad_utf8)
            self.assertEqual(ctx_utf8.exception.details["code_detail"], "file_not_utf8")

    def test_front_matter_and_sections(self):
        fm = parse_front_matter(SAMPLE_MD)
        self.assertEqual(fm["doc_id"], "DOC-PRD-001")
        self.assertEqual(fm["version"], "1.0")
        self.assertEqual(fm["access_level"], "public")
        self.assertEqual(
            section_titles(SAMPLE_MD),
            ["Tổng quan", "Biến thể và giá tham khảo", "Bảo quản"],
        )

    def test_find_sku_tokens_ignores_doc_ids_and_finds_skus(self):
        tokens = find_sku_tokens(SAMPLE_MD)
        self.assertEqual(tokens, {"TSH-BLK-M", "TSH-WHT-L"})
        self.assertNotIn("DOC-PRD-001", tokens)
        self.assertNotIn("DOC-POL-RETURN", tokens)

    def test_parse_variant_table_active_and_discontinued(self):
        rows = parse_variant_table(SAMPLE_MD, "Biến thể và giá tham khảo")
        self.assertEqual(
            rows,
            [
                {"sku": "TSH-BLK-M", "color": "Đen", "size": "M", "price": 150000},
                {"sku": "TSH-WHT-L", "color": "Trắng", "size": "L", "price": 150000},
            ],
        )

        discontinued_md = """---
doc_id: DOC-PRD-007
---
## Thông tin nhận diện sản phẩm
| SKU | Màu | Size | Trạng thái |
|---|---|---|---|
| JKT-NVY-L | Xanh navy | L | Ngừng bán |
"""
        disc_rows = parse_variant_table(discontinued_md, "Thông tin nhận diện sản phẩm")
        self.assertEqual(
            disc_rows,
            [{"sku": "JKT-NVY-L", "color": "Xanh navy", "size": "L", "status": "Ngừng bán"}],
        )

    def test_find_hardcoded_stock_catches_numeric_stock_only(self):
        self.assertEqual(find_hardcoded_stock(SAMPLE_MD), [])
        bad_text = SAMPLE_MD + "\nHiện kho còn 25 cái màu đen và tồn kho: 3 chiếc màu trắng.\n"
        hits = find_hardcoded_stock(bad_text)
        self.assertIn("còn 25 cái", hits)
        self.assertTrue(any("tồn kho: 3" in h for h in hits))


if __name__ == "__main__":
    unittest.main()

