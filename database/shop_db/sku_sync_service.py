"""Kiểm tra toàn vẹn manifest, đối soát đồng bộ SKU với SQLite Catalog và đồng bộ dữ liệu (TV1).

Quy tắc kiến trúc:
  - Manifest JSON là nguồn chuẩn duy nhất (Single Source of Truth) của corpus metadata.
  - Bảng SQLite `products` / `product_variants` là nguồn chuẩn duy nhất của catalog & giá.
  - Phiên bản `(doc_id, version)` là bất biến sau khi đã đồng bộ.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from .audit_service import sanitize
from .corpus_errors import (
    CorpusFileIntegrityError,
    CorpusValidationError,
    CorpusVersionConflict,
    SkuSyncMismatch,
)
from .corpus_files import (
    find_hardcoded_stock,
    find_sku_tokens,
    fingerprint,
    parse_front_matter,
    parse_variant_table,
    read_normalized,
    section_titles,
)
from .db import NOW_SQL, connect, get_db_path, migrate, transaction
from .seed import seed_catalog

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_REL = "data_config/corpus_manifest_v1.0.json"

DOC_TYPES = ("product_spec", "policy", "guide", "faq", "sop_internal", "admin_ops")
ACCESS_LEVELS = ("public", "staff", "admin")
CATALOG_STATUSES = ("active", "discontinued", "not_applicable")
CATEGORIES = ("Áo", "Giày", "Phụ kiện", "general", "internal")
SYNC_ACTOR_TYPES = ("staff", "admin", "system")

REQUIRED_MANIFEST_KEYS = (
    "manifest_schema_version",
    "corpus_release",
    "created_by",
    "catalog_source",
    "documents",
)
REQUIRED_DOC_KEYS = (
    "doc_id",
    "title",
    "doc_type",
    "category",
    "access_level",
    "version",
    "author",
    "source_path",
    "effective_date",
    "encoding",
    "content_sha256",
    "file_size_bytes",
    "catalog_status",
    "product_ids",
    "skus",
    "change_note",
)
FRONT_MATTER_SYNC_KEYS = (
    "doc_id",
    "title",
    "version",
    "access_level",
    "author",
    "effective_date",
)
REQUIRED_FRONT_MATTER_KEYS = FRONT_MATTER_SYNC_KEYS + ("data_notice",)

_DOC_ID_RE = re.compile(r"^DOC-[A-Z0-9-]{3,40}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def get_default_manifest_path(repo_root: Path = REPO_ROOT) -> Path:
    env_path = os.environ.get("CORPUS_MANIFEST_PATH")
    if env_path:
        return Path(env_path)
    return Path(repo_root) / DEFAULT_MANIFEST_REL


def load_manifest(path) -> dict:
    """Đọc và kiểm tra cấu trúc khung của file manifest JSON."""
    p = Path(path)
    if not p.is_file():
        raise CorpusValidationError("Không tìm thấy file manifest corpus", path=str(path))
    try:
        raw = p.read_bytes().replace(b"\r\n", b"\n")
        if raw.startswith(b"\xef\xbb\xbf"):
            raise CorpusValidationError("Manifest không được chứa UTF-8 BOM", path=str(path))
        data = json.loads(raw.decode("utf-8", errors="strict"))
    except CorpusValidationError:
        raise
    except Exception as exc:
        raise CorpusValidationError(f"Manifest không phải JSON UTF-8 hợp lệ: {exc}", path=str(path)) from exc

    if not isinstance(data, dict):
        raise CorpusValidationError("Manifest gốc phải là JSON object", path=str(path))
    missing = [k for k in REQUIRED_MANIFEST_KEYS if k not in data]
    if missing:
        raise CorpusValidationError("Manifest thiếu trường bắt buộc ở cấp gốc", missing=missing)
    if not isinstance(data["documents"], list) or not data["documents"]:
        raise CorpusValidationError("Trường 'documents' phải là danh sách không rỗng")
    if not all(isinstance(item, dict) for item in data["documents"]):
        raise CorpusValidationError("Mỗi phần tử trong 'documents' phải là object")
    if not isinstance(data["corpus_release"], str) or not data["corpus_release"].strip():
        raise CorpusValidationError("Trường 'corpus_release' không hợp lệ")
    return data


def _err(errors: list, code: str, doc_id, detail: str, sku=None) -> None:
    errors.append({"code": code, "doc_id": doc_id, "sku": sku, "detail": detail})


def _warn(warnings: list, code: str, doc_id, detail: str) -> None:
    warnings.append({"code": code, "doc_id": doc_id, "detail": detail})


def _is_valid_source_path(source_path, repo_root: Path) -> bool:
    if not isinstance(source_path, str) or not source_path:
        return False
    if "\\" in source_path or source_path.startswith("/"):
        return False
    parts = source_path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return False
    if not source_path.startswith("data_config/corpus/") or not source_path.endswith(".md"):
        return False
    corpus_root = (Path(repo_root) / "data_config" / "corpus").resolve()
    resolved = (Path(repo_root) / source_path).resolve()
    try:
        resolved.relative_to(corpus_root)
    except ValueError:
        return False
    return True


def _validate_manifest_internal(manifest: dict, repo_root: Path) -> tuple[dict, dict[str, str]]:
    if not isinstance(manifest, dict) or any(k not in manifest for k in REQUIRED_MANIFEST_KEYS):
        raise CorpusValidationError("Cấu trúc manifest không hợp lệ")
    if not isinstance(manifest["documents"], list) or not manifest["documents"]:
        raise CorpusValidationError("Danh sách 'documents' trong manifest đang trống hoặc sai kiểu")

    errors: list[dict] = []
    warnings: list[dict] = []
    loaded_texts: dict[str, str] = {}
    seen_doc_ids: set[str] = set()
    total_sections = 0
    public_sections = 0
    linked_skus: set[str] = set()

    for idx, doc in enumerate(manifest["documents"]):
        if not isinstance(doc, dict):
            _err(errors, "missing_field", f"index:{idx}", "Mục tài liệu không phải object")
            continue

        raw_id = doc.get("doc_id")
        doc_label = raw_id if isinstance(raw_id, str) and raw_id else f"index:{idx}"

        missing_keys = [k for k in REQUIRED_DOC_KEYS if k not in doc or doc[k] is None]
        for k in ("doc_id", "title", "doc_type", "category", "access_level", "version",
                  "author", "source_path", "effective_date", "encoding", "content_sha256",
                  "catalog_status"):
            if k in doc and doc[k] is not None and (not isinstance(doc[k], str) or not doc[k].strip()):
                if k not in missing_keys:
                    missing_keys.append(k)
        if "change_note" in doc and doc["change_note"] is not None and not isinstance(doc["change_note"], str):
            missing_keys.append("change_note")
        if "product_ids" in doc and not isinstance(doc.get("product_ids"), list):
            missing_keys.append("product_ids")
        if "skus" in doc and not isinstance(doc.get("skus"), list):
            missing_keys.append("skus")

        if missing_keys:
            _err(errors, "missing_field", doc_label, f"Thiếu hoặc rỗng trường: {', '.join(sorted(missing_keys))}")
            continue

        doc_id = doc["doc_id"]
        if not _DOC_ID_RE.match(doc_id):
            _err(errors, "invalid_doc_id", doc_id, f"doc_id không khớp mẫu chuẩn: {doc_id!r}")
        if doc_id in seen_doc_ids:
            _err(errors, "duplicate_doc_id", doc_id, f"Trùng lặp doc_id trong manifest: {doc_id}")
        seen_doc_ids.add(doc_id)

        if (doc["doc_type"] not in DOC_TYPES
                or doc["access_level"] not in ACCESS_LEVELS
                or doc["catalog_status"] not in CATALOG_STATUSES
                or doc["category"] not in CATEGORIES
                or doc["encoding"] != "utf-8"
                or not _DATE_RE.match(doc["effective_date"])):
            _err(errors, "invalid_enum", doc_id, "Giá trị enum/encoding/effective_date không hợp lệ")

        if doc["doc_type"] == "product_spec" and doc["catalog_status"] == "not_applicable":
            _err(errors, "catalog_status_not_applicable", doc_id,
                 "Tài liệu product_spec bắt buộc khai báo catalog_status là active hoặc discontinued")
        elif doc["doc_type"] != "product_spec" and doc["catalog_status"] != "not_applicable":
            _err(errors, "catalog_status_not_applicable", doc_id,
                 "Tài liệu không phải product_spec phải đặt catalog_status = 'not_applicable'")

        for sku in doc["skus"]:
            if isinstance(sku, str):
                linked_skus.add(sku)

        source_path = doc["source_path"]
        if not _is_valid_source_path(source_path, repo_root):
            _err(errors, "invalid_source_path", doc_id, f"Đường dẫn source_path không hợp lệ: {source_path!r}")
            continue

        full_path = Path(repo_root) / source_path
        try:
            text, norm_bytes = read_normalized(full_path)
        except CorpusFileIntegrityError as exc:
            _err(errors, exc.details.get("code_detail", "file_missing"), doc_id, exc.message)
            continue

        loaded_texts[doc_id] = text
        actual_sha = hashlib.sha256(norm_bytes).hexdigest()
        actual_size = len(norm_bytes)
        if doc["content_sha256"] != actual_sha:
            _err(errors, "hash_mismatch", doc_id,
                 f"SHA-256 lệch: manifest={doc['content_sha256'][:12]}..., thực tế={actual_sha[:12]}...")
        expected_size = doc["file_size_bytes"]
        if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size <= 0 or expected_size != actual_size:
            _err(errors, "size_mismatch", doc_id,
                 f"Kích thước bytes lệch: manifest={expected_size}, thực tế={actual_size}")

        fm = parse_front_matter(text)
        missing_fm = [k for k in REQUIRED_FRONT_MATTER_KEYS if not fm.get(k)]
        mismatched_fm = [k for k in FRONT_MATTER_SYNC_KEYS if fm.get(k) != str(doc[k])]
        if missing_fm or mismatched_fm:
            _err(errors, "front_matter_mismatch", doc_id,
                 f"Front matter thiếu {missing_fm} hoặc lệch manifest ở {mismatched_fm}")

        secs = section_titles(text)
        total_sections += len(secs)
        if doc["access_level"] == "public":
            public_sections += len(secs)
        if len(secs) < 3:
            _warn(warnings, "few_sections", doc_id, f"Tài liệu chỉ có {len(secs)} section (< 3)")

        declared_skus = {s for s in doc["skus"] if isinstance(s, str)}
        for tok in sorted(find_sku_tokens(text) - declared_skus):
            _err(errors, "undeclared_sku_in_text", doc_id,
                 f"Văn bản nhắc tới SKU {tok} nhưng chưa khai báo trong manifest.skus", sku=tok)

        stock_hits = find_hardcoded_stock(text)
        if stock_hits:
            _err(errors, "hardcoded_stock", doc_id,
                 f"Phát hiện cụm ghi cứng số lượng tồn kho: {stock_hits}")

    if public_sections < 30:
        _warn(warnings, "low_public_sections", None,
              f"Tổng số section public mới đạt {public_sections} (< 30)")

    report = {
        "ok": len(errors) == 0,
        "corpus_release": manifest.get("corpus_release"),
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "documents": len(manifest["documents"]),
            "sections": total_sections,
            "public_sections": public_sections,
            "skus_linked": len(linked_skus),
        },
    }
    return report, loaded_texts


def validate_manifest(manifest: dict, repo_root: Path = REPO_ROOT) -> dict:
    """Kiểm tra độc lập manifest và toàn bộ file Markdown (không cần SQLite)."""
    report, _ = _validate_manifest_internal(manifest, Path(repo_root))
    return report


def verify_catalog_sync(conn, manifest: dict, repo_root: Path = REPO_ROOT) -> dict:
    """Kiểm tra toàn diện manifest + nội dung file đối chiếu với catalog SQLite."""
    root = Path(repo_root)
    report, loaded_texts = _validate_manifest_internal(manifest, root)
    errors = report["errors"]

    db_products = {
        r["id"]: dict(r)
        for r in conn.execute("SELECT id, name, category, is_active FROM products").fetchall()
    }
    db_variants = {
        r["sku"]: dict(r)
        for r in conn.execute(
            "SELECT sku, product_id, variant_name, color, size, price, is_active FROM product_variants"
        ).fetchall()
    }
    skus_by_product: dict[int, list[str]] = {pid: [] for pid in db_products}
    for sku, v in db_variants.items():
        skus_by_product.setdefault(v["product_id"], []).append(sku)

    product_sellable = {
        pid: bool(prod["is_active"] == 1 and any(db_variants[s]["is_active"] == 1 for s in skus_by_product.get(pid, [])))
        for pid, prod in db_products.items()
    }

    covered_sellable_products: set[int] = set()

    for doc in manifest["documents"]:
        if not isinstance(doc, dict) or "doc_id" not in doc or not isinstance(doc.get("product_ids"), list) or not isinstance(doc.get("skus"), list):
            continue
        doc_id = doc["doc_id"]
        pids = doc["product_ids"]
        skus = doc["skus"]

        valid_pids: set[int] = set()
        for pid in pids:
            if isinstance(pid, bool) or not isinstance(pid, int) or pid not in db_products:
                _err(errors, "unknown_product_id", doc_id, f"product_id không tồn tại trong DB: {pid!r}")
            else:
                valid_pids.add(pid)

        reported_unknown_skus: set[str] = set()
        for sku in skus:
            if not isinstance(sku, str) or sku not in db_variants:
                _err(errors, "unknown_sku", doc_id, f"SKU không tồn tại trong DB: {sku!r}", sku=sku if isinstance(sku, str) else None)
                if isinstance(sku, str):
                    reported_unknown_skus.add(sku)
            else:
                v_pid = db_variants[sku]["product_id"]
                if v_pid not in valid_pids:
                    _err(errors, "sku_product_mismatch", doc_id,
                         f"SKU {sku} thuộc product_id={v_pid}, không khớp product_ids={pids}", sku=sku)

        text = loaded_texts.get(doc_id)
        if text is not None:
            for tok in sorted(find_sku_tokens(text)):
                if tok not in db_variants and tok not in reported_unknown_skus:
                    _err(errors, "unknown_sku", doc_id, f"Token SKU trong văn bản không có trong DB: {tok}", sku=tok)
                    reported_unknown_skus.add(tok)

        if doc.get("doc_type") == "product_spec":
            if len(pids) != 1 or len(valid_pids) != 1:
                _err(errors, "product_spec_sku_set_mismatch", doc_id,
                     "Tài liệu product_spec bắt buộc gắn với đúng 1 product_id hợp lệ")
                continue

            pid = next(iter(valid_pids))
            prod = db_products[pid]
            expected_skus = set(skus_by_product.get(pid, []))
            if len(skus) != len(set(skus)) or set(skus) != expected_skus:
                _err(errors, "product_spec_sku_set_mismatch", doc_id,
                     f"Tập SKU của {doc_id} ({sorted(skus)}) không bằng đúng tập SKU DB ({sorted(expected_skus)})")

            sellable = product_sellable[pid]
            cat_status = doc.get("catalog_status")
            if cat_status == "active" and not sellable:
                _err(errors, "catalog_status_mismatch", doc_id,
                     f"Sản phẩm id={pid} hiện không bán được trong DB nhưng tài liệu khai báo active")
            elif cat_status == "discontinued" and sellable:
                _err(errors, "catalog_status_mismatch", doc_id,
                     f"Sản phẩm id={pid} đang mở bán trong DB nhưng tài liệu khai báo discontinued")

            if cat_status == "active" and doc.get("access_level") == "public":
                covered_sellable_products.add(pid)

            if text is None:
                continue

            if prod["name"] not in text:
                _err(errors, "product_name_missing", doc_id,
                     f"Văn bản thiếu tên chuẩn của sản phẩm từ DB: {prod['name']!r}")

            if doc.get("category") != prod["category"]:
                _err(errors, "variant_table_mismatch", doc_id,
                     f"Nhóm hàng manifest ({doc.get('category')!r}) khác DB ({prod['category']!r})")

            heading = "Biến thể và giá tham khảo" if cat_status == "active" else "Thông tin nhận diện sản phẩm"
            try:
                table_rows = parse_variant_table(text, heading)
            except ValueError as exc:
                _err(errors, "variant_table_mismatch", doc_id, str(exc))
                continue

            if not table_rows:
                _err(errors, "variant_table_missing", doc_id, f"Thiếu bảng biến thể dưới mục '## {heading}'")
                continue

            table_skus = [r["sku"] for r in table_rows]
            if len(table_skus) != len(set(table_skus)) or set(table_skus) != expected_skus:
                _err(errors, "variant_table_mismatch", doc_id,
                     f"Tập SKU trong bảng Markdown ({table_skus}) không khớp tập SKU sản phẩm ({sorted(expected_skus)})")

            for row in table_rows:
                r_sku = row["sku"]
                if r_sku not in db_variants:
                    continue
                v = db_variants[r_sku]
                if row["color"] != (v["color"] or "") or row["size"] != (v["size"] or ""):
                    _err(errors, "variant_table_mismatch", doc_id,
                         f"Màu/size của {r_sku} trong bảng ({row['color']}/{row['size']}) khác DB ({v['color']}/{v['size']})",
                         sku=r_sku)
                if cat_status == "active":
                    if "price" not in row:
                        _err(errors, "variant_table_mismatch", doc_id,
                             f"Bảng active của {doc_id} thiếu cột giá tham khảo", sku=r_sku)
                    elif row["price"] != v["price"]:
                        _err(errors, "price_mismatch", doc_id,
                             f"Giá tham khảo của {r_sku} ({row['price']}) khác giá DB ({v['price']})",
                             sku=r_sku)
                elif cat_status == "discontinued":
                    if row.get("status") != "Ngừng bán":
                        _err(errors, "variant_table_mismatch", doc_id,
                             f"Trạng thái bảng ngừng bán của {r_sku} phải là 'Ngừng bán'", sku=r_sku)

    for pid, prod in sorted(db_products.items()):
        if product_sellable[pid] and pid not in covered_sellable_products:
            _err(errors, "missing_catalog_coverage", None,
                 f"Sản phẩm đang bán id={pid} ({prod['name']}) chưa có tài liệu product_spec public active")

    report["ok"] = len(errors) == 0
    return report


def _log_sync_event(conn, actor_type: str, actor_id: str, event_type: str, corpus_release, details: dict) -> None:
    payload = json.dumps(sanitize(details), ensure_ascii=False)
    conn.execute(
        "INSERT INTO corpus_sync_events (actor_type, actor_id, event_type, corpus_release, details)"
        " VALUES (?,?,?,?,?)",
        (actor_type, actor_id[:100], event_type,
         str(corpus_release)[:50] if corpus_release is not None else None, payload),
    )


def _manifest_rel_and_hash(manifest_path: Path, repo_root: Path) -> tuple[str, str]:
    raw_norm = manifest_path.read_bytes().replace(b"\r\n", b"\n")
    sha = hashlib.sha256(raw_norm).hexdigest()
    try:
        rel = manifest_path.resolve().relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        rel = manifest_path.name
    return rel, sha


def sync_from_manifest(
    conn,
    manifest_path=None,
    *,
    actor_type: str = "system",
    actor_id: str = "tv1-sync",
    repo_root: Path = REPO_ROOT,
) -> dict:
    """Đồng bộ nguyên tử toàn bộ metadata corpus từ manifest JSON vào SQLite."""
    if actor_type not in SYNC_ACTOR_TYPES:
        raise CorpusValidationError("actor_type không hợp lệ", actor_type=actor_type)
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise CorpusValidationError("actor_id không được rỗng")

    root = Path(repo_root)
    mpath = Path(manifest_path) if manifest_path is not None else get_default_manifest_path(root)
    manifest = load_manifest(mpath)
    manifest_rel, manifest_sha = _manifest_rel_and_hash(mpath, root)

    report = verify_catalog_sync(conn, manifest, repo_root=root)
    release = manifest["corpus_release"]

    if not report["ok"]:
        with transaction(conn):
            _log_sync_event(
                conn,
                actor_type,
                actor_id.strip(),
                "sync_rejected",
                release,
                {
                    "error_codes": sorted({e["code"] for e in report["errors"]}),
                    "doc_ids": sorted({e["doc_id"] for e in report["errors"] if e["doc_id"]}),
                    "error_count": len(report["errors"]),
                },
            )
        raise SkuSyncMismatch(
            "Đồng bộ corpus bị từ chối do kiểm tra manifest/SKU không đạt",
            corpus_release=release,
            report=report,
        )

    activated: list[str] = []
    deactivated: list[str] = []
    versions_changed: list[dict] = []
    manifest_doc_ids: set[str] = set()

    with transaction(conn):
        for doc in manifest["documents"]:
            doc_id = doc["doc_id"]
            ver = doc["version"]
            manifest_doc_ids.add(doc_id)

            prev_doc = conn.execute(
                "SELECT active_version, is_active FROM corpus_documents WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()

            existing_ver = conn.execute(
                "SELECT id, content_sha256 FROM corpus_document_versions WHERE doc_id = ? AND version = ?",
                (doc_id, ver),
            ).fetchone()
            if existing_ver is not None and existing_ver["content_sha256"] != doc["content_sha256"]:
                raise CorpusVersionConflict(
                    f"Phiên bản ({doc_id}, {ver}) đã tồn tại với SHA-256 khác; hãy phát hành version mới",
                    doc_id=doc_id,
                    version=ver,
                )

            conn.execute(
                f"""
                INSERT INTO corpus_documents
                    (doc_id, title, doc_type, category, access_level, declared_catalog_status,
                     active_version, is_active, updated_at)
                VALUES (?,?,?,?,?,?,?,1,{NOW_SQL})
                ON CONFLICT(doc_id) DO UPDATE SET
                    title = excluded.title,
                    doc_type = excluded.doc_type,
                    category = excluded.category,
                    access_level = excluded.access_level,
                    declared_catalog_status = excluded.declared_catalog_status,
                    active_version = excluded.active_version,
                    is_active = 1,
                    updated_at = {NOW_SQL}
                """,
                (
                    doc_id,
                    doc["title"],
                    doc["doc_type"],
                    doc["category"],
                    doc["access_level"],
                    doc["catalog_status"],
                    ver,
                ),
            )

            conn.execute(
                "UPDATE corpus_document_versions SET is_active = 0 WHERE doc_id = ? AND version != ?",
                (doc_id, ver),
            )
            if existing_ver is None:
                conn.execute(
                    """
                    INSERT INTO corpus_document_versions
                        (doc_id, version, source_path, author, content_sha256, file_size_bytes,
                         effective_date, change_note, first_release, is_active)
                    VALUES (?,?,?,?,?,?,?,?,?,1)
                    """,
                    (
                        doc_id,
                        ver,
                        doc["source_path"],
                        doc["author"],
                        doc["content_sha256"],
                        doc["file_size_bytes"],
                        doc["effective_date"],
                        doc["change_note"],
                        release,
                    ),
                )
            else:
                conn.execute(
                    "UPDATE corpus_document_versions SET is_active = 1 WHERE id = ?",
                    (existing_ver["id"],),
                )

            conn.execute("DELETE FROM corpus_document_products WHERE doc_id = ?", (doc_id,))
            for pid in doc["product_ids"]:
                conn.execute(
                    "INSERT INTO corpus_document_products (doc_id, product_id) VALUES (?,?)",
                    (doc_id, pid),
                )

            conn.execute("DELETE FROM corpus_document_skus WHERE doc_id = ?", (doc_id,))
            for sku in doc["skus"]:
                conn.execute(
                    "INSERT INTO corpus_document_skus (doc_id, sku) VALUES (?,?)",
                    (doc_id, sku),
                )

            activated.append(f"{doc_id}@{ver}")
            if prev_doc is None or prev_doc["is_active"] == 0 or prev_doc["active_version"] != ver:
                versions_changed.append({
                    "doc_id": doc_id,
                    "from_version": prev_doc["active_version"] if prev_doc else None,
                    "to_version": ver,
                })

        active_in_db = [
            r["doc_id"]
            for r in conn.execute("SELECT doc_id FROM corpus_documents WHERE is_active = 1").fetchall()
        ]
        for stale_id in active_in_db:
            if stale_id not in manifest_doc_ids:
                conn.execute(
                    "UPDATE corpus_document_versions SET is_active = 0 WHERE doc_id = ?",
                    (stale_id,),
                )
                conn.execute(
                    f"UPDATE corpus_documents SET is_active = 0, active_version = NULL, updated_at = {NOW_SQL}"
                    " WHERE doc_id = ?",
                    (stale_id,),
                )
                deactivated.append(stale_id)

        conn.execute("UPDATE corpus_releases SET is_active = 0 WHERE is_active = 1")
        conn.execute(
            f"""
            INSERT INTO corpus_releases (release, manifest_path, manifest_sha256, is_active, synced_at)
            VALUES (?,?,?,1,{NOW_SQL})
            ON CONFLICT(release) DO UPDATE SET
                manifest_path = excluded.manifest_path,
                manifest_sha256 = excluded.manifest_sha256,
                is_active = 1,
                synced_at = {NOW_SQL}
            """,
            (release, manifest_rel, manifest_sha),
        )

        _log_sync_event(
            conn,
            actor_type,
            actor_id.strip(),
            "sync_applied",
            release,
            {
                "release": release,
                "documents": len(manifest["documents"]),
                "activated": activated,
                "deactivated": deactivated,
            },
        )

    return {
        "corpus_release": release,
        "documents_active": len(manifest["documents"]),
        "versions_changed": versions_changed,
        "report": report,
    }


def _print_fingerprints(manifest_arg, repo_root: Path) -> int:
    entries = []
    if manifest_arg and Path(manifest_arg).is_file():
        manifest = load_manifest(manifest_arg)
        for doc in manifest["documents"]:
            p = repo_root / doc["source_path"]
            fp = fingerprint(p)
            entries.append({
                "doc_id": doc["doc_id"],
                "version": doc["version"],
                "source_path": doc["source_path"],
                **fp,
            })
    else:
        corpus_dir = repo_root / "data_config" / "corpus"
        for p in sorted(corpus_dir.rglob("*.md")):
            text, _ = read_normalized(p)
            fm = parse_front_matter(text)
            fp = fingerprint(p)
            entries.append({
                "doc_id": fm.get("doc_id", ""),
                "version": fm.get("version", ""),
                "source_path": p.relative_to(repo_root).as_posix(),
                **fp,
            })
    print(json.dumps(entries, ensure_ascii=False, indent=2))
    return 0


def _open_check_conn(db_arg) -> tuple:
    if db_arg:
        p = Path(db_arg)
        if p.is_file():
            conn = connect(p)
            migrate(conn)
            if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] > 0:
                return conn, True
            conn.close()
    else:
        default_p = Path(get_db_path())
        if default_p.is_file():
            conn = connect(default_p)
            migrate(conn)
            if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] > 0:
                return conn, True
            conn.close()

    conn = connect(":memory:")
    migrate(conn)
    seed_catalog(conn)
    return conn, True


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Kiểm tra và đồng bộ Corpus Metadata & SKU (TV1)")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Kiểm tra manifest và đối soát SKU với catalog")
    group.add_argument("--sync", action="store_true", help="Đồng bộ manifest vào SQLite")
    group.add_argument("--fingerprints", action="store_true", help="In SHA-256 và kích thước chuẩn hóa của các file")
    ap.add_argument("--manifest", help="Đường dẫn file manifest JSON")
    ap.add_argument("--db", help="Đường dẫn SQLite DB")
    ap.add_argument("--json", action="store_true", help="In report dạng JSON đầy đủ")
    args = ap.parse_args(argv)

    if args.fingerprints:
        return _print_fingerprints(args.manifest, REPO_ROOT)

    mpath = Path(args.manifest) if args.manifest else get_default_manifest_path(REPO_ROOT)

    if args.check:
        manifest = load_manifest(mpath)
        conn, should_close = _open_check_conn(args.db)
        try:
            report = verify_catalog_sync(conn, manifest, repo_root=REPO_ROOT)
        finally:
            if should_close:
                conn.close()
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            status = "PASS" if report["ok"] else "FAIL"
            print(f"[{status}] release={report['corpus_release']} stats={report['stats']} "
                  f"errors={len(report['errors'])} warnings={len(report['warnings'])}")
            for err in report["errors"]:
                print(f"  ERROR {err['code']} (doc={err['doc_id']}, sku={err['sku']}): {err['detail']}")
            for warn in report["warnings"]:
                print(f"  WARN  {warn['code']} (doc={warn['doc_id']}): {warn['detail']}")
        return 0 if report["ok"] else 1

    conn = connect(args.db)
    try:
        migrate(conn)
        if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            seed_catalog(conn)
        result = sync_from_manifest(conn, mpath, repo_root=REPO_ROOT)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Đã đồng bộ release {result['corpus_release']}: "
                  f"{result['documents_active']} tài liệu active, "
                  f"{len(result['versions_changed'])} thay đổi version.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

