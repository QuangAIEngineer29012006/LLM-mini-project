"""Khởi tạo và reset dữ liệu Catalog + Corpus Metadata độc lập (TV1).

Không chỉnh sửa `seed.py` hay `db.py` cũ; tái sử dụng các hàm public sẵn có.
"""
import argparse
import sys

from .db import connect, migrate
from .seed import reset_and_seed, seed_catalog
from .sku_sync_service import REPO_ROOT, sync_from_manifest


def ensure_corpus_seeded(conn, manifest_path=None, repo_root=REPO_ROOT) -> dict:
    """Đảm bảo DB đã migrate v3, có catalog và có bản corpus active (idempotent)."""
    migrate(conn)
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        seed_catalog(conn)
    active_rel = conn.execute("SELECT release FROM corpus_releases WHERE is_active = 1").fetchone()
    if active_rel is not None:
        active_docs = conn.execute("SELECT COUNT(*) FROM corpus_documents WHERE is_active = 1").fetchone()[0]
        return {
            "corpus_release": active_rel["release"],
            "documents_active": active_docs,
            "already_seeded": True,
        }
    res = sync_from_manifest(conn, manifest_path=manifest_path, repo_root=repo_root)
    res["already_seeded"] = False
    return res


def reset_and_seed_all(conn, manifest_path=None, repo_root=REPO_ROOT) -> dict:
    """Reset toàn bộ catalog + corpus và nạp lại từ đầu."""
    catalog_summary = reset_and_seed(conn)
    corpus_summary = sync_from_manifest(conn, manifest_path=manifest_path, repo_root=repo_root)
    return {
        "catalog": catalog_summary,
        "corpus_release": corpus_summary["corpus_release"],
        "documents_active": corpus_summary["documents_active"],
    }


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Khởi tạo / reset Catalog + Corpus Metadata (TV1)")
    ap.add_argument("--db", help="Đường dẫn DB (mặc định SHOP_DB_PATH hoặc database/data/shop.db)")
    ap.add_argument("--manifest", help="Đường dẫn file manifest JSON")
    ap.add_argument("--reset", action="store_true", help="Xóa sạch và nạp lại cả catalog lẫn corpus")
    args = ap.parse_args(argv)

    conn = connect(args.db)
    try:
        if args.reset:
            out = reset_and_seed_all(conn, manifest_path=args.manifest)
            print("Đã reset và seed catalog + corpus:", out)
            return 0
        out = ensure_corpus_seeded(conn, manifest_path=args.manifest)
        print("Kết quả khởi tạo corpus:", out)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

