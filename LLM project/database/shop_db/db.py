import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "shop.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_TABLES = ["conversation_messages", "conversations", "audit_logs", "order_items", "orders", "product_aliases",
           "inventory", "product_variants", "products"]

NOW_SQL = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"


def get_db_path() -> str:
    return os.environ.get("SHOP_DB_PATH", str(DEFAULT_DB_PATH))


def connect(path=None) -> sqlite3.Connection:
    path = str(path or get_db_path())
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, timeout=10)  # tự quản lý transaction
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def _migration_files() -> list:
    return sorted((int(p.name.split("_", 1)[0]), p) for p in MIGRATIONS_DIR.glob("[0-9]*_*.sql"))


def latest_version() -> int:
    files = _migration_files()
    return files[-1][0] if files else 1


def migrate(conn: sqlite3.Connection, target_version=None) -> int:
    target = target_version or latest_version()
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == 0:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.execute("PRAGMA user_version = 1")
        version = 1
    for ver, path in _migration_files():
        if version < ver <= target:
            conn.executescript("BEGIN;\n" + path.read_text(encoding="utf-8") + "\nCOMMIT;")
            conn.execute(f"PRAGMA user_version = {ver}")
            version = ver
    return version


def drop_all(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = OFF")
    for t in _TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.execute("PRAGMA user_version = 0")
    conn.execute("PRAGMA foreign_keys = ON")
