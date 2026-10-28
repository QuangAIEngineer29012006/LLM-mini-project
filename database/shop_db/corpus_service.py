"""Dịch vụ truy vấn Corpus Metadata chỉ-đọc (read-only) theo phân quyền & liên kết SKU (TV1).

Mọi hàm nhận `conn: sqlite3.Connection` làm tham số đầu tiên.
Không hàm nào trong module này sửa đổi dữ liệu DB; việc đồng bộ chỉ đi qua `sku_sync_service.sync_from_manifest`.
"""
import json
from pathlib import Path

from .corpus_errors import (
    CorpusAccessDenied,
    CorpusFileIntegrityError,
    CorpusNotFound,
    CorpusValidationError,
)
from .corpus_files import fingerprint
from .errors import SkuNotFound
from .sku_sync_service import REPO_ROOT
from .validation import normalize_sku

ROLE_ACCESS: dict[str, tuple[str, ...]] = {
    "public": ("public",),
    "customer": ("public",),
    "staff": ("public", "staff"),
    "admin": ("public", "staff", "admin"),
}


def allowed_access_levels(role: str) -> tuple[str, ...]:
    """Trả về tuple các mức `access_level` được phép truy cập của `role`."""
    if not isinstance(role, str) or role not in ROLE_ACCESS:
        raise CorpusValidationError("Role không hợp lệ", field="role", role=role)
    return ROLE_ACCESS[role]


def _validate_doc_id(doc_id) -> str:
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise CorpusValidationError("doc_id phải là chuỗi không rỗng", field="doc_id")
    return doc_id.strip()


def _attach_links(conn, rows) -> list[dict]:
    if not rows:
        return []
    doc_ids = [r["doc_id"] for r in rows]
    placeholders = ",".join("?" for _ in doc_ids)

    prod_map: dict[str, list[int]] = {d: [] for d in doc_ids}
    for r in conn.execute(
        f"SELECT doc_id, product_id FROM corpus_document_products"
        f" WHERE doc_id IN ({placeholders}) ORDER BY product_id",
        doc_ids,
    ):
        prod_map[r["doc_id"]].append(r["product_id"])

    sku_map: dict[str, list[str]] = {d: [] for d in doc_ids}
    for r in conn.execute(
        f"SELECT doc_id, sku FROM corpus_document_skus"
        f" WHERE doc_id IN ({placeholders}) ORDER BY sku",
        doc_ids,
    ):
        sku_map[r["doc_id"]].append(r["sku"])

    out = []
    for r in rows:
        item = dict(r)
        item["product_ids"] = prod_map[r["doc_id"]]
        item["skus"] = sku_map[r["doc_id"]]
        out.append(item)
    return out


def list_documents(
    conn,
    role: str,
    *,
    doc_type: str | None = None,
    category: str | None = None,
    product_id: int | None = None,
    sku: str | None = None,
) -> list[dict]:
    """Liệt kê tài liệu active được phép truy cập theo `role` ngay trong câu SQL."""
    levels = allowed_access_levels(role)
    lvl_placeholders = ",".join("?" for _ in levels)
    sql = f"SELECT * FROM v_corpus_active_documents WHERE access_level IN ({lvl_placeholders})"
    params: list = list(levels)

    if doc_type is not None:
        if not isinstance(doc_type, str) or not doc_type.strip():
            raise CorpusValidationError("doc_type không hợp lệ", field="doc_type")
        sql += " AND doc_type = ?"
        params.append(doc_type.strip())

    if category is not None:
        if not isinstance(category, str) or not category.strip():
            raise CorpusValidationError("category không hợp lệ", field="category")
        sql += " AND category = ?"
        params.append(category.strip())

    if product_id is not None:
        if isinstance(product_id, bool) or not isinstance(product_id, int):
            raise CorpusValidationError("product_id phải là số nguyên", field="product_id")
        sql += (
            " AND EXISTS (SELECT 1 FROM corpus_document_products dp"
            " WHERE dp.doc_id = v_corpus_active_documents.doc_id AND dp.product_id = ?)"
        )
        params.append(product_id)

    if sku is not None:
        norm_sku = normalize_sku(sku)
        sql += (
            " AND EXISTS (SELECT 1 FROM corpus_document_skus ds"
            " WHERE ds.doc_id = v_corpus_active_documents.doc_id AND ds.sku = ?)"
        )
        params.append(norm_sku)

    sql += " ORDER BY doc_id ASC"
    rows = conn.execute(sql, params).fetchall()
    return _attach_links(conn, rows)


def check_document_access(conn, doc_id: str, role: str) -> dict:
    """Kiểm tra quyền truy cập tài liệu; không bao giờ lộ tiêu đề hay nội dung khi bị từ chối."""
    levels = allowed_access_levels(role)
    clean_id = _validate_doc_id(doc_id)
    row = conn.execute(
        "SELECT doc_id, access_level, is_active FROM corpus_documents WHERE doc_id = ?",
        (clean_id,),
    ).fetchone()
    if row is None:
        return {"allowed": False, "reason": "not_found"}
    if row["access_level"] not in levels:
        return {"allowed": False, "reason": "access_denied"}
    if row["is_active"] == 0:
        return {"allowed": False, "reason": "inactive"}
    return {"allowed": True, "reason": "ok"}


def get_document(conn, doc_id: str, role: str) -> dict:
    """Đọc chi tiết metadata của một tài liệu active theo `role`."""
    clean_id = _validate_doc_id(doc_id)
    chk = check_document_access(conn, clean_id, role)
    if not chk["allowed"]:
        if chk["reason"] == "access_denied":
            raise CorpusAccessDenied("Không có quyền truy cập tài liệu này", doc_id=clean_id, role=role)
        raise CorpusNotFound("Tài liệu không tồn tại hoặc không còn hoạt động",
                             doc_id=clean_id, reason=chk["reason"])
    row = conn.execute(
        "SELECT * FROM v_corpus_active_documents WHERE doc_id = ?",
        (clean_id,),
    ).fetchone()
    return _attach_links(conn, [row])[0]


def resolve_citation(
    conn,
    doc_id: str,
    version: str | None = None,
    role: str = "customer",
    repo_root: Path = REPO_ROOT,
) -> dict:
    """Tra cứu và xác thực metadata citation từ `doc_id` và `version`."""
    levels = allowed_access_levels(role)
    clean_id = _validate_doc_id(doc_id)

    doc_row = conn.execute(
        "SELECT doc_id, title, access_level, active_version, is_active FROM corpus_documents WHERE doc_id = ?",
        (clean_id,),
    ).fetchone()
    if doc_row is None:
        raise CorpusNotFound("Không tìm thấy tài liệu của citation", doc_id=clean_id)
    if doc_row["access_level"] not in levels:
        raise CorpusAccessDenied("Không có quyền truy cập nguồn tài liệu citation", doc_id=clean_id, role=role)

    target_version = version.strip() if isinstance(version, str) and version.strip() else doc_row["active_version"]
    if version is not None and (not isinstance(version, str) or not version.strip()):
        raise CorpusValidationError("version không hợp lệ", field="version")
    if not target_version:
        raise CorpusNotFound("Tài liệu hiện không có phiên bản đang hoạt động", doc_id=clean_id)

    ver_row = conn.execute(
        "SELECT version, source_path, content_sha256, is_active"
        " FROM corpus_document_versions WHERE doc_id = ? AND version = ?",
        (clean_id, target_version),
    ).fetchone()
    if ver_row is None:
        raise CorpusNotFound("Không tìm thấy phiên bản tài liệu citation",
                             doc_id=clean_id, version=target_version)

    full_path = Path(repo_root) / ver_row["source_path"]
    source_exists = full_path.is_file()
    sha256_matches = False
    if source_exists:
        try:
            fp = fingerprint(full_path)
            sha256_matches = fp["content_sha256"] == ver_row["content_sha256"]
        except CorpusFileIntegrityError:
            sha256_matches = False

    return {
        "doc_id": doc_row["doc_id"],
        "title": doc_row["title"],
        "source": ver_row["source_path"],
        "version": ver_row["version"],
        "access_level": doc_row["access_level"],
        "is_active_version": bool(doc_row["is_active"] == 1 and ver_row["is_active"] == 1),
        "source_exists": source_exists,
        "sha256_matches": sha256_matches,
    }


def documents_for_sku(conn, sku: str, role: str = "customer") -> list[dict]:
    """Lấy các tài liệu active liên kết trực tiếp với `sku` hoặc với `product_id` của `sku`."""
    levels = allowed_access_levels(role)
    norm_sku = normalize_sku(sku)
    v_row = conn.execute(
        "SELECT product_id FROM product_variants WHERE sku = ?",
        (norm_sku,),
    ).fetchone()
    if v_row is None:
        raise SkuNotFound("SKU không tồn tại trong hệ thống", sku=norm_sku)

    lvl_placeholders = ",".join("?" for _ in levels)
    rows = conn.execute(
        f"""
        SELECT * FROM v_corpus_active_documents
        WHERE access_level IN ({lvl_placeholders})
          AND (
              EXISTS (SELECT 1 FROM corpus_document_skus ds
                      WHERE ds.doc_id = v_corpus_active_documents.doc_id AND ds.sku = ?)
              OR EXISTS (SELECT 1 FROM corpus_document_products dp
                         WHERE dp.doc_id = v_corpus_active_documents.doc_id AND dp.product_id = ?)
          )
        ORDER BY doc_id ASC
        """,
        (*levels, norm_sku, v_row["product_id"]),
    ).fetchall()
    return _attach_links(conn, rows)


def list_versions(conn, doc_id: str, role: str = "admin") -> list[dict]:
    """Liệt kê lịch sử phiên bản của một tài liệu (chỉ dành cho `admin`)."""
    allowed_access_levels(role)
    if role != "admin":
        raise CorpusAccessDenied("Chỉ quản trị viên được xem lịch sử phiên bản tài liệu", role=role)
    clean_id = _validate_doc_id(doc_id)
    exists = conn.execute("SELECT 1 FROM corpus_documents WHERE doc_id = ?", (clean_id,)).fetchone()
    if exists is None:
        raise CorpusNotFound("Tài liệu không tồn tại", doc_id=clean_id)
    rows = conn.execute(
        "SELECT id, doc_id, version, source_path, author, content_sha256, file_size_bytes,"
        " effective_date, change_note, first_release, is_active, created_at"
        " FROM corpus_document_versions WHERE doc_id = ? ORDER BY id ASC",
        (clean_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def corpus_status(conn) -> dict:
    """Trạng thái tổng quan của bản phát hành corpus đang kích hoạt trong SQLite."""
    rel = conn.execute(
        "SELECT release, manifest_path, synced_at FROM corpus_releases WHERE is_active = 1"
    ).fetchone()

    counts = {"public": 0, "staff": 0, "admin": 0}
    for r in conn.execute(
        "SELECT access_level, COUNT(*) AS cnt FROM corpus_documents WHERE is_active = 1 GROUP BY access_level"
    ):
        counts[r["access_level"]] = r["cnt"]

    ev = conn.execute(
        "SELECT id, created_at, actor_type, actor_id, event_type, corpus_release, details"
        " FROM corpus_sync_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    last_event = None
    if ev is not None:
        last_event = dict(ev)
        last_event["details"] = json.loads(last_event["details"]) if last_event["details"] else {}

    return {
        "active_release": rel["release"] if rel else None,
        "manifest_path": rel["manifest_path"] if rel else None,
        "synced_at": rel["synced_at"] if rel else None,
        "documents_by_access": counts,
        "last_event": last_event,
    }

