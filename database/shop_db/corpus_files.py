"""Đọc, chuẩn hóa LF/UTF-8 hoặc PDF, tính SHA-256 và phân tích cấu trúc tài liệu Corpus (TV1).

Module này thuần xử lý file/chuỗi (hỗ trợ song song `.pdf` và `.md`), không phụ thuộc kết nối SQLite.
"""
import hashlib
import io
import re
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from .corpus_errors import CorpusFileIntegrityError

UTF8_BOM = b"\xef\xbb\xbf"
PDF_MAGIC = b"%PDF-"

_SKU_TOKEN_RE = re.compile(r"\b[A-Z]{2,5}-[A-Z0-9]{1,10}-[A-Z0-9]{1,10}\b")
_HARDCODED_STOCK_RE = re.compile(
    r"\b(?:còn|tồn\s+kho|tồn)\s*:?\s*\d+"
    r"(?!\s*(?:ngày|giờ|tháng|năm|cm|mm|kg|g|gsm|inch|%|°c)\b)"
    r"(?:\s*(?:cái|chiếc|đôi|sản\s+phẩm|sp)\b|\b)",
    flags=re.IGNORECASE,
)
_SEPARATOR_CELL_RE = re.compile(r"^:?-{2,}:?$")
_PDF_TABLE_SPLIT_RE = re.compile(r"\s{2,}")
_NUMBERED_HEADING_RE = re.compile(r"^(\d+)\.\s+(\S.*)$")

_PDF_META_LABELS: tuple[tuple[str, str], ...] = (
    ("Mã tài liệu:", "doc_id"),
    ("Phiên bản:", "version"),
    ("Ngày hiệu lực:", "effective_date"),
    ("Phân quyền:", "access_level"),
    ("Đơn vị ban hành:", "author"),
    ("Lưu ý dữ liệu:", "data_notice"),
)
_PDF_BANNER_PREFIX = "HỆ THỐNG THƯƠNG MẠI ĐIỆN TỬ"


def read_pdf_text(path) -> tuple[str, bytes]:
    """Đọc file PDF nhị phân, kiểm tra tính hợp lệ và trích xuất văn bản chuẩn hóa LF."""
    p = Path(path)
    if not p.is_file():
        raise CorpusFileIntegrityError(
            "Không tìm thấy file tài liệu corpus",
            code_detail="file_missing",
            path=str(path),
        )
    raw = p.read_bytes()
    if not raw.strip():
        raise CorpusFileIntegrityError(
            "File PDF rỗng",
            code_detail="file_empty",
            path=str(path),
        )
    if not raw.startswith(PDF_MAGIC):
        raise CorpusFileIntegrityError(
            "File không đúng chuẩn định dạng PDF (%PDF-)",
            code_detail="file_invalid_pdf",
            path=str(path),
        )
    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
        if len(reader.pages) == 0:
            raise CorpusFileIntegrityError(
                "File PDF không có trang nào",
                code_detail="file_empty",
                path=str(path),
            )
        pages_text = [(page.extract_text() or "") for page in reader.pages]
    except CorpusFileIntegrityError:
        raise
    except (PdfReadError, PdfStreamError, ValueError, OSError, EOFError) as exc:
        raise CorpusFileIntegrityError(
            f"Không thể đọc cấu trúc file PDF: {exc}",
            code_detail="file_invalid_pdf",
            path=str(path),
        ) from exc

    raw_text = "\n".join(pages_text).replace("\r\n", "\n").replace("\r", "\n")
    if not raw_text.strip():
        raise CorpusFileIntegrityError(
            "File PDF rỗng hoặc không chứa văn bản trích xuất được",
            code_detail="file_empty",
            path=str(path),
        )
    # Chuẩn hóa đề mục đánh số của PDF ("1. Tổng quan") sang "## Tổng quan" trên chuỗi trả về
    # để tương thích trực tiếp với bộ chunker RAG (TV2) mà không làm bẩn giao diện file PDF gốc.
    norm_lines: list[str] = []
    for line in raw_text.split("\n"):
        m = _NUMBERED_HEADING_RE.match(line.strip())
        if m:
            norm_lines.append(f"## {m.group(2).strip()}")
        else:
            norm_lines.append(line)
    return "\n".join(norm_lines), raw


def read_normalized(path) -> tuple[str, bytes]:
    """Đọc tài liệu corpus (`.pdf` hoặc `.md`):
    - Với `.pdf`: kiểm tra cấu trúc PDF, trích xuất văn bản UTF-8 chuẩn hóa LF và trả `(text, raw_pdf_bytes)`.
    - Với `.md`: từ chối UTF-8 BOM / byte lỗi / file rỗng, chuẩn hóa CRLF -> LF và trả `(text, lf_utf8_bytes)`.
    """
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        return read_pdf_text(p)

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
    """Tính SHA-256 và kích thước chuẩn (binary gốc với `.pdf`, UTF-8 LF với `.md`)."""
    _, content_bytes = read_normalized(path)
    return {
        "content_sha256": hashlib.sha256(content_bytes).hexdigest(),
        "file_size_bytes": len(content_bytes),
    }


def _match_section_heading(stripped_line: str) -> str | None:
    if stripped_line.startswith("## "):
        title = stripped_line[3:].strip()
        return title or None
    m = _NUMBERED_HEADING_RE.match(stripped_line)
    if m:
        return m.group(2).strip() or None
    return None


def _parse_pdf_header_block(lines: list[str]) -> tuple[dict, str]:
    """Đọc khối thông tin văn bản chuẩn ở đầu trang PDF (không dùng cú pháp YAML `---`)."""
    sec_idx = None
    for idx, line in enumerate(lines):
        if _match_section_heading(line.strip()) is not None:
            sec_idx = idx
            break
    if sec_idx is None or sec_idx == 0:
        return {}, "\n".join(lines)

    header_lines = [l.strip() for l in lines[:sec_idx] if l.strip()]
    meta: dict[str, str] = {}
    title_parts: list[str] = []
    seen_meta_row = False

    for hline in header_lines:
        if hline.startswith(_PDF_BANNER_PREFIX):
            continue
        segments = [seg.strip() for seg in _PDF_TABLE_SPLIT_RE.split(hline) if seg.strip()]
        matched_any_label = False
        for seg in segments:
            for label, key in _PDF_META_LABELS:
                if seg.startswith(label):
                    val = seg[len(label):].strip()
                    # Cắt nhãn phân quyền hiển thị tiếng Việt nếu đi kèm dạng "public (Công khai)"
                    if key == "access_level" and " " in val:
                        val = val.split()[0].strip()
                    meta[key] = val
                    matched_any_label = True
                    seen_meta_row = True
                    break
        if not matched_any_label and not seen_meta_row:
            title_parts.append(hline)

    if not meta:
        return {}, "\n".join(lines)
    if title_parts and "title" not in meta:
        meta["title"] = " ".join(title_parts).strip()

    body = "\n".join(lines[sec_idx:])
    return meta, body


def _split_front_matter(text: str) -> tuple[dict, str]:
    lines = text.split("\n")
    start_idx = 0
    while start_idx < len(lines) and not lines[start_idx].strip():
        start_idx += 1
    if start_idx >= len(lines):
        return {}, text

    if lines[start_idx].strip() != "---":
        return _parse_pdf_header_block(lines[start_idx:])

    end_idx = None
    for idx in range(start_idx + 1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return {}, text
    meta: dict[str, str] = {}
    last_key: str | None = None
    for line in lines[start_idx + 1:end_idx]:
        stripped = line.strip()
        if not stripped:
            continue
        key, sep, value = stripped.partition(":")
        if sep and key.strip() and " " not in key.strip():
            last_key = key.strip()
            meta[last_key] = value.strip()
        elif last_key is not None and not sep:
            meta[last_key] = f"{meta[last_key]} {stripped}".strip()
        else:
            return {}, text
    body = "\n".join(lines[end_idx + 1:])
    return meta, body


def parse_front_matter(text: str) -> dict:
    """Đọc metadata đầu tài liệu (hỗ trợ cả YAML `---` của Markdown và bảng tiêu đề chuẩn của PDF)."""
    meta, _ = _split_front_matter(text)
    return meta


def section_titles(text: str) -> list[str]:
    """Liệt kê tiêu đề các mục chính (`## ...` trong Markdown hoặc `1. ...` trong PDF)."""
    _, body = _split_front_matter(text)
    titles = []
    for line in body.split("\n"):
        heading = _match_section_heading(line.strip())
        if heading:
            titles.append(heading)
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


def _validate_and_build_variant_rows(headers: list[str], raw_rows: list[list[str]]) -> list[dict]:
    if len(headers) != 4:
        raise ValueError("Bảng biến thể phải có đúng 4 cột chuẩn")
    if headers[:3] != ["SKU", "Màu", "Size"]:
        raise ValueError("Ba cột đầu của bảng biến thể phải là SKU, Màu, Size")

    fourth = headers[3]
    is_price_col = fourth == "Giá tham khảo (VND)"
    is_status_col = fourth == "Trạng thái"
    if not (is_price_col or is_status_col):
        raise ValueError(f"Cột thứ 4 không hợp lệ: {fourth!r}")

    rows = []
    for cells in raw_rows:
        if len(cells) != 4:
            raise ValueError(f"Dòng bảng biến thể không đủ 4 cột: {cells!r}")
        sku, color, size, last_col = [c.strip() for c in cells]
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


def parse_variant_table(text: str, heading: str) -> list[dict]:
    """Đọc bảng biến thể ngay trong section `<heading>` (hỗ trợ cả Markdown và văn bản PDF).

    Trả về danh sách dict `{"sku", "color", "size", "price"}` (bảng active)
    hoặc `{"sku", "color", "size", "status"}` (bảng ngừng bán).
    Trả `[]` nếu không tìm thấy heading hoặc bảng; raise `ValueError` nếu bảng sai cấu trúc/giá.
    """
    target = heading[3:].strip() if heading.startswith("## ") else heading.strip()
    _, body = _split_front_matter(text)
    lines = body.split("\n")

    sec_start = None
    for idx, line in enumerate(lines):
        sec_title = _match_section_heading(line.strip())
        if sec_title == target:
            sec_start = idx + 1
            break
    if sec_start is None:
        return []

    sec_lines: list[str] = []
    for line in lines[sec_start:]:
        if _match_section_heading(line.strip()) is not None:
            break
        sec_lines.append(line.strip())

    # 1. Thử đọc bảng Markdown chuẩn dạng `| ... |`
    pipe_lines: list[str] = []
    in_pipe_table = False
    for stripped in sec_lines:
        if stripped.startswith("|") and stripped.endswith("|"):
            in_pipe_table = True
            pipe_lines.append(stripped)
        elif in_pipe_table:
            break

    if len(pipe_lines) >= 3:
        headers = _split_table_row(pipe_lines[0])
        sep_cells = _split_table_row(pipe_lines[1])
        if len(headers) != 4 or len(sep_cells) != 4 or not _is_separator_row(sep_cells):
            raise ValueError("Bảng biến thể phải có đúng 4 cột chuẩn Markdown")
        raw_rows = [_split_table_row(rl) for rl in pipe_lines[2:]]
        return _validate_and_build_variant_rows(headers, raw_rows)

    # 2. Đọc bảng trích xuất từ PDF (các cột cách nhau từ 2 khoảng trắng trở lên)
    pdf_header_idx = None
    pdf_headers: list[str] = []
    for idx, stripped in enumerate(sec_lines):
        if not stripped:
            continue
        cols = [c.strip() for c in _PDF_TABLE_SPLIT_RE.split(stripped) if c.strip()]
        if len(cols) >= 3 and cols[:3] == ["SKU", "Màu", "Size"]:
            pdf_header_idx = idx
            pdf_headers = cols
            break

    if pdf_header_idx is None:
        return []

    pdf_rows: list[list[str]] = []
    for stripped in sec_lines[pdf_header_idx + 1:]:
        if not stripped:
            if pdf_rows:
                break
            continue
        cols = [c.strip() for c in _PDF_TABLE_SPLIT_RE.split(stripped) if c.strip()]
        if len(cols) < 2:
            if pdf_rows:
                break
            continue
        pdf_rows.append(cols)

    if not pdf_rows:
        return []

    return _validate_and_build_variant_rows(pdf_headers, pdf_rows)


def _is_variant_table_line(stripped: str) -> bool:
    if stripped.startswith("|") and stripped.endswith("|"):
        cells = _split_table_row(stripped)
        if len(cells) == 4 and (
            cells[:3] == ["SKU", "Màu", "Size"]
            or _is_separator_row(cells)
            or bool(_SKU_TOKEN_RE.fullmatch(cells[0]))
        ):
            return True
    cols = [c.strip() for c in _PDF_TABLE_SPLIT_RE.split(stripped) if c.strip()]
    if len(cols) == 4 and (
        cols[:3] == ["SKU", "Màu", "Size"] or bool(_SKU_TOKEN_RE.fullmatch(cols[0]))
    ):
        return True
    return False


def find_hardcoded_stock(text: str) -> list[str]:
    """Tìm cụm ghi cứng số lượng tồn kho, bỏ qua các dòng bảng biến thể chuẩn (Markdown & PDF)."""
    _, body = _split_front_matter(text)
    prose_lines = [line for line in body.split("\n") if not _is_variant_table_line(line.strip())]
    prose_text = "\n".join(prose_lines)
    return [" ".join(match.group(0).split()) for match in _HARDCODED_STOCK_RE.finditer(prose_text)]
