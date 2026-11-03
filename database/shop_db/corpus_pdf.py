"""Chuyển đổi tài liệu Corpus & Manifest Metadata sang định dạng PDF doanh nghiệp chuẩn Unicode (TV1).

Đặc điểm trình bày & kỹ thuật:
  - Loại bỏ hoàn toàn cú pháp thô của Markdown (`---`, `##`, `-`, `` ` ``, `|`) trên mặt trang PDF:
    + Khung tiêu chuẩn tài liệu (ISO Metadata Grid) tiếng Việt kèm nhãn màu phân quyền (`PUBLIC` / `STAFF` / `ADMIN`).
    + Đề mục đánh số thứ tự (`1.`, `2.`, ...) kèm thanh nhấn màu xanh đậm và PDF Bookmarks (Outline) tương tác.
    + Danh sách dấu chấm tròn (`•`) thụt lề treo chuẩn văn bản in ấn, căn đều hai biên (`TA_JUSTIFY`).
    + Bảng biến thể nền tiêu đề xanh đậm `#1E3A8A`, chữ trắng in đậm, căn giữa cột Size và căn phải cột Giá.
  - Sinh byte PDF tất định (`invariant=1`) để `content_sha256` bất biến giữa các lần build.
  - Văn bản trích xuất bằng `pypdf` tương thích 100% với đối soát SKU 5 lớp (TV1) và RAG Ingestion (TV2).
"""
import argparse
import io
import json
import os
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .corpus_errors import CorpusValidationError
from .corpus_files import (
    _is_separator_row,
    _split_front_matter,
    _split_table_row,
    fingerprint,
    parse_front_matter,
    parse_variant_table,
    read_normalized,
    section_titles,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_DIR = REPO_ROOT / "data_config" / "corpus"

_FONT_REG_NAME = "TV1CorpusSans"
_FONT_BOLD_NAME = "TV1CorpusSansBold"
_FONTS_REGISTERED = False

_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_INLINE_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")

_ACCESS_BADGE_THEME: dict[str, tuple[str, str, str]] = {
    "public": ("#DCFCE7", "#166534", "CÔNG KHAI • PUBLIC"),
    "staff": ("#FEF3C7", "#92400E", "NỘI BỘ • STAFF"),
    "admin": ("#FEE2E2", "#991B1B", "QUẢN TRỊ • ADMIN"),
}
_ACCESS_VN_LABEL: dict[str, str] = {
    "public": "public (Công khai)",
    "staff": "staff (Nội bộ nhân viên)",
    "admin": "admin (Quản trị viên)",
}

_CANDIDATE_FONT_PAIRS: tuple[tuple[str, str], ...] = (
    # Windows
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    ("C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/tahomabd.ttf"),
    # Linux
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ),
    ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/freefont/FreeSans.ttf", "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
    # macOS
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
)


def resolve_unicode_fonts() -> tuple[Path, Path]:
    """Tìm cặp font TrueType (Regular, Bold) hỗ trợ tiếng Việt trên hệ điều hành hiện tại."""
    env_reg = os.environ.get("CORPUS_PDF_FONT_PATH")
    env_bold = os.environ.get("CORPUS_PDF_BOLD_FONT_PATH")
    if env_reg:
        reg_p = Path(env_reg)
        bold_p = Path(env_bold) if env_bold else reg_p
        if reg_p.is_file() and bold_p.is_file():
            return reg_p, bold_p

    for reg_str, bold_str in _CANDIDATE_FONT_PAIRS:
        reg_p = Path(reg_str)
        bold_p = Path(bold_str)
        if reg_p.is_file():
            return reg_p, (bold_p if bold_p.is_file() else reg_p)

    raise CorpusValidationError(
        "Không tìm thấy font TrueType Unicode để xuất PDF tiếng Việt; "
        "hãy đặt biến môi trường CORPUS_PDF_FONT_PATH trỏ tới file .ttf"
    )


def _ensure_fonts_registered() -> tuple[str, str]:
    global _FONTS_REGISTERED
    if not _FONTS_REGISTERED:
        reg_path, bold_path = resolve_unicode_fonts()
        pdfmetrics.registerFont(TTFont(_FONT_REG_NAME, str(reg_path)))
        pdfmetrics.registerFont(TTFont(_FONT_BOLD_NAME, str(bold_path)))
        _FONTS_REGISTERED = True
    return _FONT_REG_NAME, _FONT_BOLD_NAME


def _format_inline_markdown(raw_text: str, font_bold: str) -> str:
    """Chuyển đổi định dạng inline Markdown (`code`, **bold**) sang rich text PDF sạch dấu backtick/`*`."""
    escaped = xml_escape(raw_text)
    escaped = _INLINE_BOLD_RE.sub(rf"<font name='{font_bold}'>\1</font>", escaped)
    escaped = _INLINE_CODE_RE.sub(
        rf"<font name='{font_bold}' color='#1E3A8A'>\1</font>",
        escaped,
    )
    return escaped


class _EnterpriseBannerBar(Flowable):
    """Thanh tiêu đề thương hiệu đầu trang kèm huy hiệu phân quyền màu sắc."""

    def __init__(self, access_level: str, width: float, font_reg: str, font_bold: str):
        super().__init__()
        self.access_level = access_level
        self.bar_width = width
        self.font_reg = font_reg
        self.font_bold = font_bold
        self.bar_height = 20.0

    def wrap(self, availWidth, availHeight):
        return min(self.bar_width, availWidth), self.bar_height

    def draw(self):
        canv = self.canv
        w = self.bar_width
        bg_hex, fg_hex, badge_text = _ACCESS_BADGE_THEME.get(
            self.access_level,
            ("#E2E8F0", "#334155", self.access_level.upper()),
        )

        canv.saveState()
        # Đường viền đỉnh màu xanh thương hiệu
        canv.setFillColor(colors.HexColor("#1E3A8A"))
        canv.rect(0, self.bar_height - 2.2, w, 2.2, stroke=0, fill=1)

        # Huy hiệu phân quyền góc phải
        badge_font_size = 7.5
        badge_w = pdfmetrics.stringWidth(badge_text, self.font_bold, badge_font_size) + 14.0
        badge_h = 14.0
        badge_x = w - badge_w
        badge_y = 1.0
        canv.setFillColor(colors.HexColor(bg_hex))
        canv.setStrokeColor(colors.HexColor(fg_hex))
        canv.setLineWidth(0.5)
        canv.roundRect(badge_x, badge_y, badge_w, badge_h, radius=7.0, stroke=1, fill=1)

        # Dòng chữ nhận diện hệ thống + huy hiệu trên cùng 1 dòng
        txt = canv.beginText()
        txt.setFont(self.font_bold, 7.5)
        txt.setFillColor(colors.HexColor("#475569"))
        txt.setTextOrigin(0, 5.0)
        txt.textOut("HỆ THỐNG THƯƠNG MẠI ĐIỆN TỬ AI LIVE COMMERCE — TÀI LIỆU NGHIỆP VỤ   ")
        txt.setFillColor(colors.HexColor(fg_hex))
        txt.setTextOrigin(badge_x + 7.0, 5.0)
        txt.textOut(badge_text)
        canv.drawText(txt)
        canv.restoreState()


class _DocumentMetadataGrid(Flowable):
    """Bảng thông tin chuẩn quản lý tài liệu (thay thế hoàn toàn khối YAML `---` thô)."""

    def __init__(self, fm: dict[str, str], width: float, font_reg: str, font_bold: str):
        super().__init__()
        self.fm = fm
        self.grid_width = width
        self.font_reg = font_reg
        self.font_bold = font_bold
        self.row_h = 18.5
        self.has_notice = bool(fm.get("data_notice"))
        self.total_h = self.row_h * (3 if self.has_notice else 2)

    def wrap(self, availWidth, availHeight):
        return min(self.grid_width, availWidth), self.total_h

    def draw(self):
        canv = self.canv
        w = self.grid_width
        h = self.total_h
        r = self.row_h

        c1_w = w * 0.36
        c2_w = w * 0.28

        canv.saveState()
        # Khung nền chung
        canv.setFillColor(colors.HexColor("#F8FAFC"))
        canv.setStrokeColor(colors.HexColor("#CBD5E1"))
        canv.setLineWidth(0.6)
        canv.roundRect(0, 0, w, h, radius=3.5, stroke=1, fill=1)

        # Dải nền nhẹ cho dòng ghi chú dữ liệu cuối khung
        if self.has_notice:
            canv.setFillColor(colors.HexColor("#F1F5F9"))
            canv.rect(0.5, 0.5, w - 1.0, r - 0.5, stroke=0, fill=1)

        # Đường kẻ ngang & dọc chia ô
        canv.setStrokeColor(colors.HexColor("#CBD5E1"))
        canv.setLineWidth(0.45)
        canv.line(0, h - r, w, h - r)
        if self.has_notice:
            canv.line(0, h - 2 * r, w, h - 2 * r)

        # Đường chia cột dòng 1 (3 ô) và dòng 2 (2 ô)
        canv.line(c1_w, h - r, c1_w, h)
        canv.line(c1_w + c2_w, h - r, c1_w + c2_w, h)
        canv.line(c1_w, h - 2 * r, c1_w, h - r)

        # Hàng 1: Mã tài liệu | Phiên bản | Ngày hiệu lực
        doc_id = self.fm.get("doc_id", "")
        ver = self.fm.get("version", "")
        eff = self.fm.get("effective_date", "")
        self._draw_cells(
            canv,
            y=h - r + 5.5,
            cells=[
                (8.0, "Mã tài liệu: ", doc_id, True),
                (c1_w + 8.0, "Phiên bản: ", ver, True),
                (c1_w + c2_w + 8.0, "Ngày hiệu lực: ", eff, False),
            ],
        )

        # Hàng 2: Phân quyền | Đơn vị ban hành
        acc_raw = self.fm.get("access_level", "")
        acc_disp = _ACCESS_VN_LABEL.get(acc_raw, acc_raw)
        author = self.fm.get("author", "")
        self._draw_cells(
            canv,
            y=h - 2 * r + 5.5,
            cells=[
                (8.0, "Phân quyền: ", acc_disp, False),
                (c1_w + 8.0, "Đơn vị ban hành: ", author, False),
            ],
        )

        # Hàng 3: Lưu ý dữ liệu
        if self.has_notice:
            self._draw_cells(
                canv,
                y=5.5,
                cells=[(8.0, "Lưu ý dữ liệu: ", self.fm.get("data_notice", ""), False)],
                value_color="#475569",
            )

        canv.restoreState()

    def _draw_cells(
        self,
        canv,
        y: float,
        cells: list[tuple[float, str, str, bool]],
        value_color: str = "#0F172A",
    ) -> None:
        txt = canv.beginText()
        font_sz = 8.3
        for idx, (x, label, val, bold_val) in enumerate(cells):
            txt.setTextOrigin(x, y)
            txt.setFont(self.font_bold, font_sz)
            txt.setFillColor(colors.HexColor("#475569"))
            txt.textOut(label)

            v_x = x + pdfmetrics.stringWidth(label, self.font_bold, font_sz)
            txt.setTextOrigin(v_x, y)
            txt.setFont(self.font_bold if bold_val else self.font_reg, font_sz)
            txt.setFillColor(colors.HexColor(value_color))
            sep = "   " if idx < len(cells) - 1 else ""
            txt.textOut(f"{val}{sep}")
        canv.drawText(txt)


class _SectionHeadingFlowable(Flowable):
    """Tiêu đề mục đánh số thứ tự chuẩn văn bản, thanh nhấn trái & gắn PDF Outline Bookmark."""

    def __init__(
        self,
        sec_num: int,
        title: str,
        width: float,
        font_bold: str,
    ):
        super().__init__()
        self.sec_num = sec_num
        self.title = title
        self.box_width = width
        self.font_bold = font_bold
        self.box_height = 20.0

    def wrap(self, availWidth, availHeight):
        return min(self.box_width, availWidth), self.box_height

    def draw(self):
        canv = self.canv
        w = self.box_width
        full_heading = f"{self.sec_num}. {self.title}"

        # Gắn bookmark vào cây mục lục của file PDF
        bm_key = f"sec_{self.sec_num}"
        canv.bookmarkPage(bm_key)
        canv.addOutlineEntry(full_heading, bm_key, level=0, closed=False)

        canv.saveState()
        # Thanh nhấn dọc màu xanh đậm bên trái
        canv.setFillColor(colors.HexColor("#1D4ED8"))
        canv.roundRect(0, 3.0, 3.2, 13.5, radius=1.2, stroke=0, fill=1)

        # Đường gạch mảnh phân tách dưới chân đề mục
        canv.setStrokeColor(colors.HexColor("#E2E8F0"))
        canv.setLineWidth(0.6)
        canv.line(0, 0.5, w, 0.5)

        txt = canv.beginText()
        txt.setFont(self.font_bold, 11.2)
        txt.setFillColor(colors.HexColor("#0F172A"))
        txt.setTextOrigin(9.5, 5.2)
        txt.textOut(full_heading)
        canv.drawText(txt)
        canv.restoreState()


class _CorpusTableFlowable(Flowable):
    """Bảng dữ liệu thương mại điện tử chuyên nghiệp, đồng thời xuất từng dòng liền mạch cho `pypdf`."""

    def __init__(
        self,
        headers: list[str],
        rows: list[list[str]],
        width: float,
        font_reg: str,
        font_bold: str,
    ):
        super().__init__()
        self.headers = headers
        self.rows = rows
        self.table_width = width
        self.font_reg = font_reg
        self.font_bold = font_bold
        self.font_size = 9.5
        self.header_h = 23.0
        self.row_h = 20.5
        self.col_widths = self._compute_col_widths(width, len(headers))
        self.total_h = self.header_h + len(rows) * self.row_h

    @staticmethod
    def _compute_col_widths(total_w: float, ncols: int) -> list[float]:
        if ncols == 4:
            ratios = (0.26, 0.24, 0.16, 0.34)
            return [total_w * r for r in ratios]
        if ncols <= 0:
            return []
        each = total_w / ncols
        return [each] * ncols

    def wrap(self, availWidth, availHeight):
        return min(self.table_width, availWidth), self.total_h

    def draw(self):
        canv = self.canv
        w = self.table_width
        h = self.total_h
        col_x = [0.0]
        for cw in self.col_widths[:-1]:
            col_x.append(col_x[-1] + cw)

        canv.saveState()
        # Nền tiêu đề xanh navy đậm
        canv.setFillColor(colors.HexColor("#1E3A8A"))
        canv.rect(0, h - self.header_h, w, self.header_h, stroke=0, fill=1)

        # Nền xen kẽ các dòng dữ liệu
        for r_idx in range(len(self.rows)):
            ry = h - self.header_h - (r_idx + 1) * self.row_h
            bg = "#FFFFFF" if r_idx % 2 == 0 else "#F8FAFC"
            canv.setFillColor(colors.HexColor(bg))
            canv.rect(0, ry, w, self.row_h, stroke=0, fill=1)

        # Viền bảng và lưới chia ô
        canv.setStrokeColor(colors.HexColor("#CBD5E1"))
        canv.setLineWidth(0.55)
        canv.rect(0, 0, w, h, stroke=1, fill=0)

        y_line = h - self.header_h
        for _ in range(len(self.rows) - 1):
            y_line -= self.row_h
            canv.line(0, y_line, w, y_line)

        for x in col_x[1:]:
            canv.line(x, 0, x, h - self.header_h)
            canv.setStrokeColor(colors.HexColor("#3B82F6"))
            canv.line(x, h - self.header_h, x, h)
            canv.setStrokeColor(colors.HexColor("#CBD5E1"))

        # Chữ dòng tiêu đề (trắng in đậm)
        self._draw_row_text(
            canv,
            self.headers,
            col_x,
            h - self.header_h + 7.2,
            is_header=True,
        )
        # Chữ các dòng dữ liệu
        for r_idx, row in enumerate(self.rows):
            ry = h - self.header_h - (r_idx + 1) * self.row_h + 6.2
            self._draw_row_text(canv, row, col_x, ry, is_header=False)

        canv.restoreState()

    def _draw_row_text(
        self,
        canv,
        cells: list[str],
        col_x: list[float],
        baseline_y: float,
        *,
        is_header: bool,
    ) -> None:
        txt = canv.beginText()
        ncols = len(cells)
        for idx, cell in enumerate(cells):
            cw = self.col_widths[idx]
            if is_header:
                fn = self.font_bold
                fg = "#FFFFFF"
            elif idx == 0:
                fn = self.font_bold
                fg = "#0F172A"
            elif idx == 3 and cell == "Ngừng bán":
                fn = self.font_bold
                fg = "#B91C1C"
            else:
                fn = self.font_reg
                fg = "#1E293B"

            text_w = pdfmetrics.stringWidth(cell, fn, self.font_size)
            # Căn giữa cột Size (idx==2), căn phải cột Giá số (idx==3 khi là số hoặc header giá)
            if ncols == 4 and idx == 2:
                x = col_x[idx] + max(6.0, (cw - text_w) / 2.0)
            elif ncols == 4 and idx == 3 and (
                cell.replace(".", "").isdigit() or (is_header and "VND" in cell)
            ):
                x = col_x[idx] + max(8.0, cw - text_w - 10.0)
            else:
                x = col_x[idx] + 9.0

            txt.setFont(fn, self.font_size)
            txt.setFillColor(colors.HexColor(fg))
            txt.setTextOrigin(x, baseline_y)
            sep = "   " if idx < ncols - 1 else ""
            txt.textOut(f"{cell}{sep}")
        canv.drawText(txt)


def _parse_body_blocks(body: str) -> list[tuple[str, object]]:
    """Tách thân Markdown thành danh sách block ngữ nghĩa."""
    lines = body.split("\n")
    blocks: list[tuple[str, object]] = []
    idx = 0
    n = len(lines)

    while idx < n:
        stripped = lines[idx].strip()
        if not stripped:
            idx += 1
            continue

        if stripped.startswith("## "):
            blocks.append(("h2", stripped[3:].strip()))
            idx += 1
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            t_lines: list[str] = []
            while idx < n and lines[idx].strip().startswith("|") and lines[idx].strip().endswith("|"):
                t_lines.append(lines[idx].strip())
                idx += 1
            if len(t_lines) >= 2:
                headers = _split_table_row(t_lines[0])
                second = _split_table_row(t_lines[1])
                start_row = 2 if _is_separator_row(second) else 1
                rows = [_split_table_row(tl) for tl in t_lines[start_row:]]
                blocks.append(("table", (headers, rows)))
            else:
                blocks.append(("p", " ".join(t_lines)))
            continue

        if stripped.startswith("- "):
            bullets: list[str] = []
            while idx < n and lines[idx].strip().startswith("- "):
                bullets.append(lines[idx].strip()[2:].strip())
                idx += 1
            blocks.append(("ul", bullets))
            continue

        para_lines: list[str] = []
        while idx < n:
            cur = lines[idx].strip()
            if (
                not cur
                or cur.startswith("## ")
                or cur.startswith("- ")
                or (cur.startswith("|") and cur.endswith("|"))
            ):
                break
            para_lines.append(cur)
            idx += 1
        blocks.append(("p", " ".join(para_lines)))

    return blocks


def _draw_subtle_page_frame(canv, doc) -> None:
    """Vẽ đường viền chân trang tinh tế mà không sinh chuỗi boilerplate gây nhiễu RAG."""
    canv.saveState()
    canv.setStrokeColor(colors.HexColor("#CBD5E1"))
    canv.setLineWidth(0.6)
    canv.line(doc.leftMargin, 28, A4[0] - doc.rightMargin, 28)
    canv.restoreState()


def render_markdown_to_pdf_bytes(md_text: str) -> bytes:
    """Render nội dung Markdown Corpus sang PDF doanh nghiệp tất định (`invariant=1`), sạch cú pháp `.md`."""
    font_reg, font_bold = _ensure_fonts_registered()
    norm_text = md_text.replace("\r\n", "\n")
    fm = parse_front_matter(norm_text)
    _, body = _split_front_matter(norm_text)

    left_margin = 44.0
    right_margin = 44.0
    content_width = A4[0] - left_margin - right_margin

    buf = io.BytesIO()
    doc_title = fm.get("title", "Tài liệu Corpus")
    doc_author = fm.get("author", "TV1 - Database & Business Data")
    doc_subject = f"{fm.get('doc_id', '')} v{fm.get('version', '')}".strip()

    pdf_doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=32.0,
        bottomMargin=36.0,
        title=doc_title,
        author=doc_author,
        subject=doc_subject,
        creator="TV1 Corpus PDF Builder",
        invariant=1,
    )

    h1_style = ParagraphStyle(
        "CorpusH1",
        fontName=font_bold,
        fontSize=14.5,
        leading=19.5,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=5.0,
        spaceAfter=7.0,
    )
    body_style = ParagraphStyle(
        "CorpusBody",
        fontName=font_reg,
        fontSize=9.8,
        leading=14.2,
        alignment=TA_JUSTIFY,
        textColor=colors.HexColor("#1E293B"),
        spaceBefore=2.0,
        spaceAfter=4.5,
    )
    bullet_style = ParagraphStyle(
        "CorpusBullet",
        fontName=font_reg,
        fontSize=9.8,
        leading=14.0,
        leftIndent=16.0,
        bulletIndent=4.0,
        bulletFontName=font_bold,
        bulletFontSize=10.0,
        bulletColor=colors.HexColor("#1D4ED8"),
        alignment=TA_JUSTIFY,
        textColor=colors.HexColor("#1E293B"),
        spaceBefore=1.0,
        spaceAfter=2.8,
    )

    story: list = []
    if fm:
        story.append(
            _EnterpriseBannerBar(fm.get("access_level", "public"), content_width, font_reg, font_bold)
        )
    if fm.get("title"):
        story.append(Paragraph(xml_escape(fm["title"]), h1_style))
    if fm:
        story.append(_DocumentMetadataGrid(fm, content_width, font_reg, font_bold))
        story.append(Spacer(1, 8.0))

    blocks = _parse_body_blocks(body)
    sec_counter = 0
    idx = 0
    while idx < len(blocks):
        btype, bval = blocks[idx]
        if btype == "h2":
            sec_counter += 1
            sec_flow = _SectionHeadingFlowable(sec_counter, str(bval), content_width, font_bold)
            if idx + 1 < len(blocks) and blocks[idx + 1][0] == "table":
                headers, rows = blocks[idx + 1][1]
                tbl = _CorpusTableFlowable(headers, rows, content_width, font_reg, font_bold)
                story.append(KeepTogether([Spacer(1, 6.0), sec_flow, Spacer(1, 5.0), tbl, Spacer(1, 6.0)]))
                idx += 2
                continue
            story.append(Spacer(1, 6.0))
            story.append(sec_flow)
            story.append(Spacer(1, 4.0))
        elif btype == "table":
            headers, rows = bval
            story.append(Spacer(1, 3.0))
            story.append(_CorpusTableFlowable(headers, rows, content_width, font_reg, font_bold))
            story.append(Spacer(1, 6.0))
        elif btype == "ul":
            for item in bval:
                formatted_item = _format_inline_markdown(str(item), font_bold)
                story.append(Paragraph(f"<bullet>&bull;</bullet>{formatted_item}", bullet_style))
            story.append(Spacer(1, 2.0))
        elif btype == "p":
            formatted_para = _format_inline_markdown(str(bval), font_bold)
            story.append(Paragraph(formatted_para, body_style))
        idx += 1

    pdf_doc.build(story, onFirstPage=_draw_subtle_page_frame, onLaterPages=_draw_subtle_page_frame)
    return buf.getvalue()


def render_markdown_file_to_pdf(md_path: str | Path, pdf_path: str | Path | None = None) -> Path:
    """Đọc một file `.md` chuẩn của Corpus và ghi ra file `.pdf` tương ứng."""
    src = Path(md_path)
    if src.suffix.lower() != ".md":
        raise CorpusValidationError("Nguồn chuyển đổi sang PDF phải là file .md", path=str(md_path))
    text, _ = read_normalized(src)
    out_path = Path(pdf_path) if pdf_path is not None else src.with_suffix(".pdf")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_bytes = render_markdown_to_pdf_bytes(text)
    out_path.write_bytes(pdf_bytes)
    return out_path


def render_manifest_to_pdf_bytes(manifest: dict) -> bytes:
    """Xuất báo cáo bảng tổng hợp Corpus Metadata Manifest (`v1.0`, `v1.1`) ra PDF."""
    if not isinstance(manifest, dict) or not isinstance(manifest.get("documents"), list):
        raise CorpusValidationError("Manifest đầu vào không hợp lệ để xuất PDF")

    font_reg, font_bold = _ensure_fonts_registered()
    buf = io.BytesIO()
    release = str(manifest.get("corpus_release", ""))
    pdf_doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=36.0,
        rightMargin=36.0,
        topMargin=34.0,
        bottomMargin=36.0,
        title=f"Corpus Metadata Manifest — Release {release}",
        author=str(manifest.get("created_by", "TV1")),
        subject=f"Corpus Manifest v{release}",
        creator="TV1 Corpus PDF Builder",
        invariant=1,
    )

    title_style = ParagraphStyle(
        "ManifestTitle",
        fontName=font_bold,
        fontSize=14.0,
        leading=18.5,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=4.0,
        spaceAfter=5.0,
    )
    meta_style = ParagraphStyle(
        "ManifestMeta",
        fontName=font_reg,
        fontSize=9.0,
        leading=13.0,
        textColor=colors.HexColor("#334155"),
        spaceAfter=2.5,
    )
    cell_style = ParagraphStyle(
        "ManifestCell",
        fontName=font_reg,
        fontSize=7.6,
        leading=10.5,
        textColor=colors.HexColor("#1E293B"),
    )
    cell_bold_style = ParagraphStyle(
        "ManifestCellBold",
        fontName=font_bold,
        fontSize=7.6,
        leading=10.5,
        textColor=colors.HexColor("#0F172A"),
    )
    head_style = ParagraphStyle(
        "ManifestHead",
        fontName=font_bold,
        fontSize=8.0,
        leading=10.5,
        textColor=colors.white,
    )

    docs = manifest["documents"]
    by_access = {"public": 0, "staff": 0, "admin": 0}
    linked_skus: set[str] = set()
    for d in docs:
        lvl = d.get("access_level")
        if lvl in by_access:
            by_access[lvl] += 1
        for s in d.get("skus", []):
            linked_skus.add(s)

    avail_w = A4[0] - 72.0
    story: list = [
        _EnterpriseBannerBar("admin", avail_w, font_reg, font_bold),
        Paragraph(xml_escape(f"BÁO CÁO CORPUS METADATA MANIFEST — RELEASE {release}"), title_style),
        Paragraph(
            xml_escape(
                f"Schema: v{manifest.get('manifest_schema_version', '')}   •   "
                f"Đơn vị phát hành: {manifest.get('created_by', '')}   •   "
                f"Nguồn đối soát catalog: {manifest.get('catalog_source', '')}"
            ),
            meta_style,
        ),
        Paragraph(
            xml_escape(
                f"Tổng số tài liệu: {len(docs)} "
                f"(Công khai: {by_access['public']}, Nội bộ: {by_access['staff']}, Quản trị: {by_access['admin']})   •   "
                f"Tổng biến thể SKU liên kết: {len(linked_skus)}"
            ),
            meta_style,
        ),
        Spacer(1, 8.0),
    ]

    table_data = [
        [
            Paragraph("Mã tài liệu", head_style),
            Paragraph("Ver", head_style),
            Paragraph("Quyền / Loại", head_style),
            Paragraph("Tiêu đề & Đường dẫn PDF", head_style),
            Paragraph("SKU liên kết", head_style),
            Paragraph("SHA-256 (12 ký tự)", head_style),
        ]
    ]
    for d in docs:
        skus_txt = ", ".join(d.get("skus") or []) or "—"
        sha_short = str(d.get("content_sha256", ""))[:12]
        size_kb = round(int(d.get("file_size_bytes", 0)) / 1024, 1)
        title_and_path = (
            f"<font name='{font_bold}'>{xml_escape(str(d.get('title', '')))}</font><br/>"
            f"<font color='#64748B'>{xml_escape(str(d.get('source_path', '')))}</font>"
        )
        table_data.append(
            [
                Paragraph(xml_escape(str(d.get("doc_id", ""))), cell_bold_style),
                Paragraph(xml_escape(str(d.get("version", ""))), cell_style),
                Paragraph(
                    xml_escape(f"{d.get('access_level', '')}\n({d.get('doc_type', '')})"),
                    cell_style,
                ),
                Paragraph(title_and_path, cell_style),
                Paragraph(xml_escape(skus_txt), cell_style),
                Paragraph(xml_escape(f"{sha_short}...\n({size_kb} KB)"), cell_style),
            ]
        )

    col_widths = [avail_w * r for r in (0.20, 0.06, 0.13, 0.33, 0.15, 0.13)]
    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
            ]
        )
    )
    story.append(tbl)
    pdf_doc.build(story, onFirstPage=_draw_subtle_page_frame, onLaterPages=_draw_subtle_page_frame)
    return buf.getvalue()


def export_manifest_pdf(manifest_path: str | Path, pdf_path: str | Path | None = None) -> Path:
    """Đọc file JSON manifest và xuất báo cáo tổng hợp metadata sang `.pdf`."""
    from .sku_sync_service import load_manifest

    mpath = Path(manifest_path)
    manifest = load_manifest(mpath)
    out = Path(pdf_path) if pdf_path is not None else mpath.with_suffix(".pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(render_manifest_to_pdf_bytes(manifest))
    return out


def extract_markdown_from_pdf(pdf_path: str | Path) -> str:
    """Khôi phục văn bản Markdown chuẩn từ file `.pdf` của Corpus (phục vụ biên tập lại hoặc kiểm thử)."""
    p = Path(pdf_path)
    text, _ = read_normalized(p)
    fm = parse_front_matter(text)
    _, body = _split_front_matter(text)

    fm_order = ("doc_id", "title", "version", "access_level", "author", "effective_date", "data_notice")
    fm_lines = ["---"]
    for k in fm_order:
        if k in fm:
            fm_lines.append(f"{k}: {fm[k]}")
    for k, v in fm.items():
        if k not in fm_order:
            fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")

    out_body: list[str] = []
    in_table = False
    for raw_line in body.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            in_table = False
            out_body.append("")
            continue
        if stripped.startswith("## "):
            in_table = False
            out_body.append(stripped)
            continue
        if stripped.startswith("•"):
            in_table = False
            out_body.append(f"- {stripped[1:].strip()}")
            continue
        cols = [c.strip() for c in re.split(r"\s{2,}", stripped) if c.strip()]
        if len(cols) == 4 and cols[:3] == ["SKU", "Màu", "Size"]:
            in_table = True
            out_body.append("| " + " | ".join(cols) + " |")
            out_body.append("|---|---|---|---|")
            continue
        if in_table and len(cols) == 4:
            out_body.append("| " + " | ".join(cols) + " |")
            continue
        in_table = False
        out_body.append(stripped)

    return "\n".join(fm_lines) + "\n\n" + "\n".join(out_body).strip() + "\n"


def verify_pdf_document(pdf_path: str | Path) -> list[str]:
    """Kiểm tra trực tiếp một file `.pdf` Corpus độc lập (không cần file `.md` đi kèm)."""
    from pypdf import PdfReader

    dst_pdf = Path(pdf_path)
    issues: list[str] = []
    if not dst_pdf.is_file():
        return [f"Thiếu file PDF: {dst_pdf}"]

    raw = dst_pdf.read_bytes()
    reader = PdfReader(io.BytesIO(raw), strict=False)
    raw_page_text = "\n".join((pg.extract_text() or "") for pg in reader.pages)
    if "## " in raw_page_text or "doc_id:" in raw_page_text or "---" in raw_page_text:
        issues.append(f"Trang hiển thị PDF vẫn còn cú pháp Markdown thô: {dst_pdf.name}")
    if not reader.outline:
        issues.append(f"File PDF thiếu mục lục Outline Bookmarks: {dst_pdf.name}")

    pdf_text, _ = read_normalized(dst_pdf)
    fm = parse_front_matter(pdf_text)
    for req_key in ("doc_id", "title", "version", "access_level", "author", "effective_date", "data_notice"):
        if not fm.get(req_key):
            issues.append(f"PDF thiếu trường metadata '{req_key}': {dst_pdf.name}")
    if len(section_titles(pdf_text)) < 3:
        issues.append(f"PDF có ít hơn 3 đề mục: {dst_pdf.name}")
    return issues


def verify_md_pdf_pair(md_path: str | Path, pdf_path: str | Path | None = None) -> list[str]:
    """Kiểm tra đối xứng 1-1 giữa file `.md` gốc và file `.pdf` đã xuất."""
    src_md = Path(md_path)
    dst_pdf = Path(pdf_path) if pdf_path is not None else src_md.with_suffix(".pdf")
    issues = verify_pdf_document(dst_pdf)
    if issues:
        return issues

    md_text, _ = read_normalized(src_md)
    expected_bytes = render_markdown_to_pdf_bytes(md_text)
    actual_bytes = dst_pdf.read_bytes()
    if actual_bytes != expected_bytes:
        issues.append(f"Bytes PDF lệch với bản build chuẩn từ Markdown: {dst_pdf.name}")

    pdf_text, _ = read_normalized(dst_pdf)
    if parse_front_matter(md_text) != parse_front_matter(pdf_text):
        issues.append(f"Metadata trích xuất từ PDF lệch với Markdown: {dst_pdf.name}")
    if section_titles(md_text) != section_titles(pdf_text):
        issues.append(f"Danh sách đề mục trong PDF lệch với Markdown: {dst_pdf.name}")

    for heading in ("Biến thể và giá tham khảo", "Thông tin nhận diện sản phẩm"):
        md_rows = parse_variant_table(md_text, heading)
        pdf_rows = parse_variant_table(pdf_text, heading)
        if md_rows != pdf_rows:
            issues.append(f"Bảng '{heading}' trong PDF lệch với Markdown: {dst_pdf.name}")

    return issues


def build_corpus_pdfs(
    corpus_dir: str | Path | None = None,
    *,
    manifest_paths: tuple[Path, ...] | list[Path] | None = None,
    update_manifests: bool = False,
    export_manifest_pdfs: bool = True,
    repo_root: Path = REPO_ROOT,
) -> dict:
    """Chuyển tài liệu `.md` (nếu có) hoặc tái xuất `.pdf` trong `data_config/corpus/` và đồng bộ manifest."""
    from .sku_sync_service import load_manifest

    root = Path(repo_root)
    cdir = Path(corpus_dir) if corpus_dir is not None else root / "data_config" / "corpus"
    md_files = sorted(cdir.rglob("*.md"))
    pdf_files = sorted(cdir.rglob("*.pdf"))
    if not md_files and not pdf_files:
        raise CorpusValidationError("Không tìm thấy file .md hoặc .pdf nào trong thư mục corpus", path=str(cdir))

    generated_pdfs: list[str] = []
    if md_files:
        for md_file in md_files:
            pdf_file = render_markdown_file_to_pdf(md_file)
            try:
                rel = pdf_file.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                rel = str(pdf_file)
            generated_pdfs.append(rel)
    else:
        for pdf_file in pdf_files:
            try:
                rel = pdf_file.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                rel = str(pdf_file)
            generated_pdfs.append(rel)

    target_manifests = (
        [Path(p) for p in manifest_paths]
        if manifest_paths is not None
        else [root / "data_config" / "corpus_manifest_v1.0.json", root / "data_config" / "corpus_manifest_v1.1.json"]
    )

    updated_manifests: list[str] = []
    exported_manifest_pdfs: list[str] = []

    for mpath in target_manifests:
        if not mpath.is_file():
            continue
        if update_manifests:
            manifest = load_manifest(mpath)
            for doc in manifest["documents"]:
                src_rel = str(doc.get("source_path", ""))
                if src_rel.endswith(".md"):
                    src_rel = src_rel[:-3] + ".pdf"
                pdf_full = root / src_rel
                fp = fingerprint(pdf_full)
                doc["source_path"] = src_rel
                doc["encoding"] = "pdf"
                doc["content_sha256"] = fp["content_sha256"]
                doc["file_size_bytes"] = fp["file_size_bytes"]
            mpath.write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            try:
                updated_manifests.append(mpath.resolve().relative_to(root.resolve()).as_posix())
            except ValueError:
                updated_manifests.append(str(mpath))

        if export_manifest_pdfs:
            mpdf = export_manifest_pdf(mpath)
            try:
                exported_manifest_pdfs.append(mpdf.resolve().relative_to(root.resolve()).as_posix())
            except ValueError:
                exported_manifest_pdfs.append(str(mpdf))

    return {
        "corpus_pdfs": generated_pdfs,
        "updated_manifests": updated_manifests,
        "manifest_pdfs": exported_manifest_pdfs,
    }


def check_corpus_pdfs(corpus_dir: str | Path | None = None, repo_root: Path = REPO_ROOT) -> dict:
    """Kiểm tra toàn bộ file `.pdf` trong thư mục corpus (kèm đối chiếu `.md` nếu có lưu song song)."""
    root = Path(repo_root)
    cdir = Path(corpus_dir) if corpus_dir is not None else root / "data_config" / "corpus"
    md_files = sorted(cdir.rglob("*.md"))
    pdf_files = sorted(cdir.rglob("*.pdf"))
    errors: list[str] = []

    if md_files:
        for md_file in md_files:
            errors.extend(verify_md_pdf_pair(md_file))
        checked = len(md_files)
    else:
        if not pdf_files:
            errors.append(f"Không tìm thấy file PDF nào trong {cdir}")
        for pdf_file in pdf_files:
            errors.extend(verify_pdf_document(pdf_file))
        checked = len(pdf_files)

    return {
        "ok": len(errors) == 0,
        "checked_pairs": checked,
        "errors": errors,
    }


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Chuyển đổi và kiểm tra tài liệu Corpus PDF (TV1)")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--build", action="store_true", help="Xuất toàn bộ tài liệu corpus .md sang .pdf")
    group.add_argument("--check", action="store_true", help="Kiểm tra tính nhất quán giữa .md và .pdf")
    ap.add_argument(
        "--update-manifests",
        action="store_true",
        help="Cập nhật source_path (.pdf), encoding, SHA-256 và file_size_bytes trong các file manifest",
    )
    ap.add_argument(
        "--no-manifest-pdf",
        action="store_true",
        help="Không xuất file PDF báo cáo tổng hợp cho corpus_manifest_*.json",
    )
    ap.add_argument("--json", action="store_true", help="In kết quả dạng JSON")
    args = ap.parse_args(argv)

    if args.check:
        res = check_corpus_pdfs(repo_root=REPO_ROOT)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            status = "PASS" if res["ok"] else "FAIL"
            print(f"[{status}] checked_pairs={res['checked_pairs']} errors={len(res['errors'])}")
            for err in res["errors"]:
                print(f"  ERROR: {err}")
        return 0 if res["ok"] else 1

    out = build_corpus_pdfs(
        update_manifests=args.update_manifests,
        export_manifest_pdfs=not args.no_manifest_pdf,
        repo_root=REPO_ROOT,
    )
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(
            f"Đã xuất {len(out['corpus_pdfs'])} file corpus PDF, "
            f"cập nhật {len(out['updated_manifests'])} manifest, "
            f"xuất {len(out['manifest_pdfs'])} báo cáo manifest PDF."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
