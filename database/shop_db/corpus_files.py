"""Đọc, chuẩn hóa LF/UTF-8, tính SHA-256 và phân tích cấu trúc Markdown cho Corpus (TV1).

Module này thuần xử lý file/chuỗi, không phụ thuộc kết nối SQLite.
"""
import hashlib
import re
from pathlib import Path

from .corpus_errors import CorpusFileIntegrityError

UTF8_BOM = b"\xef\xbb\xbf"

_SKU_TOKEN_RE = re.compile(r"\b[A-Z]{2,5}-[A-Z0-9]{1,10}-[A-Z0-9]{1,10}\b")
_HARDCODED_STOCK_RE = re.compile(
    r"\b(?:còn|tồn\s+kho|tồn)\s*:?\s*\d+"
    r"(?!\s*(?:ngày|giờ|tháng|năm|cm|mm|kg|g|gsm|inch|%|°c)\b)"
    r"(?:\s*(?:cái|chiếc|đôi|sản\s+phẩm|sp)\b|\b)",
    flags=re.IGNORECASE,
)
_SEPARATOR_CELL_RE = re.compile(r"^:?-{2,}:?$")


def read_normalized(path) -> tuple[str, bytes]:
    """Đọc file, từ chối UTF-8 BOM / byte lỗi / file rỗng, chuẩn hóa CRLF -> LF."""
    p = Path(path)
    if not p.is_file():
        raise CorpusFileIntegrityError(
            "Không tìm thấy file tài liệu corpus",
            code_detail="file_missing",
            path=str(path),
        )
    raw = p.read_bytes()
    if raw.startswith(UTF8_BOM):
        raise CorpusFileIntegrityError(
            "File chứa UTF-8 BOM (yêu cầu UTF-8 không BOM)",
            code_detail="file_has_bom",
            path=str(path),
        )
    norm_bytes = raw.replace(b"\r\n", b"\n")
    try:
        text = norm_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CorpusFileIntegrityError(
            "File không đúng chuẩn mã hóa UTF-8",
            code_detail="file_not_utf8",
            path=str(path),
        ) from exc
    if not text.strip():
        raise CorpusFileIntegrityError(
            "File rỗng hoặc chỉ chứa khoảng trắng",
            code_detail="file_empty",
            path=str(path),
        )
    return text, norm_bytes


def fingerprint(path) -> dict:
    """Tính SHA-256 và kích thước trên bytes đã chuẩn hóa LF."""
    _, norm_bytes = read_normalized(path)
    return {
        "content_sha256": hashlib.sha256(norm_bytes).hexdigest(),
        "file_size_bytes": len(norm_bytes),
    }


def _split_front_matter(text: str) -> tuple[dict, str]:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return {}, text
    meta: dict[str, str] = {}
    for line in lines[1:end_idx]:
        stripped = line.strip()
        if not stripped:
            continue
        key, sep, value = stripped.partition(":")
        if not sep or not key.strip():
            return {}, text
        meta[key.strip()] = value.strip()
    body = "\n".join(lines[end_idx + 1:])
    return meta, body


def parse_front_matter(text: str) -> dict:
    """Đọc khối front matter giữa hai dòng `---` ở đầu văn bản."""
    meta, _ = _split_front_matter(text)
    return meta


def section_titles(text: str) -> list[str]:
    """Liệt kê tiêu đề các mục bắt đầu bằng `## ` trong phần thân tài liệu."""
    _, body = _split_front_matter(text)
    titles = []
    for line in body.split("\n"):
        if line.startswith("## "):
            title = line[3:].strip()
            if title:
                titles.append(title)
    return titles


def find_sku_tokens(text: str) -> set[str]:
    """Tìm các token dạng SKU trong văn bản, bỏ qua mã tài liệu `DOC-*`."""
    return {tok for tok in _SKU_TOKEN_RE.findall(text) if not tok.startswith("DOC-")}


def _split_table_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [cell.strip() for cell in s.split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL_RE.match(c) for c in cells)


def parse_variant_table(text: str, heading: str) -> list[dict]:
    """Đọc bảng Markdown ngay trong section `## <heading>`.

    Trả về danh sách dict `{"sku", "color", "size", "price"}` (bảng active)
    hoặc `{"sku", "color", "size", "status"}` (bảng ngừng bán).
    Trả `[]` nếu không tìm thấy heading hoặc bảng; raise `ValueError` nếu bảng sai cấu trúc/giá.
    """
    target = heading[3:].strip() if heading.startswith("## ") else heading.strip()
    _, body = _split_front_matter(text)
    lines = body.split("\n")

    sec_start = None
    for idx, line in enumerate(lines):
        if line.startswith("## ") and line[3:].strip() == target:
            sec_start = idx + 1
            break
    if sec_start is None:
        return []

    table_lines = []
    in_table = False
    for line in lines[sec_start:]:
        if line.startswith("## "):
            break
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            in_table = True
            table_lines.append(stripped)
        elif in_table:
            break

    if len(table_lines) < 3:
        return []

    headers = _split_table_row(table_lines[0])
    sep_cells = _split_table_row(table_lines[1])
    if len(headers) != 4 or len(sep_cells) != 4 or not _is_separator_row(sep_cells):
        raise ValueError("Bảng biến thể phải có đúng 4 cột chuẩn Markdown")

    if headers[:3] != ["SKU", "Màu", "Size"]:
        raise ValueError("Ba cột đầu của bảng biến thể phải là SKU, Màu, Size")

    fourth = headers[3]
    is_price_col = fourth == "Giá tham khảo (VND)"
    is_status_col = fourth == "Trạng thái"
    if not (is_price_col or is_status_col):
        raise ValueError(f"Cột thứ 4 không hợp lệ: {fourth!r}")

    rows = []
    for raw_line in table_lines[2:]:
        cells = _split_table_row(raw_line)
        if len(cells) != 4:
            raise ValueError(f"Dòng bảng biến thể không đủ 4 cột: {raw_line!r}")
        sku, color, size, last_col = cells
        if not sku or not color or not size or not last_col:
            raise ValueError("Ô trong bảng biến thể không được để trống")
        if is_price_col:
            digits = last_col.replace(".", "")
            if not digits.isdigit():
                raise ValueError(f"Giá tham khảo không hợp lệ cho {sku}: {last_col!r}")
            rows.append({"sku": sku, "color": color, "size": size, "price": int(digits)})
        else:
            rows.append({"sku": sku, "color": color, "size": size, "status": last_col})
    return rows


def find_hardcoded_stock(text: str) -> list[str]:
    """Tìm cụm ghi cứng số lượng tồn kho, bỏ qua các dòng bảng biến thể chuẩn."""
    _, body = _split_front_matter(text)
    hits = []
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = _split_table_row(stripped)
            if len(cells) == 4 and (
                cells[:3] == ["SKU", "Màu", "Size"]
                or _is_separator_row(cells)
                or bool(_SKU_TOKEN_RE.fullmatch(cells[0]))
            ):
                continue
        for match in _HARDCODED_STOCK_RE.finditer(line):
            hits.append(match.group(0).strip())
    return hits

