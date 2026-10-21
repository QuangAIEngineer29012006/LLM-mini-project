import hashlib
import json
import re
import secrets
import time
import uuid

from database.shop_db import conversation_service as conversations
from database.shop_db.db import connect, migrate, transaction
from database.shop_db.seed import seed_catalog

from .errors import ApiProblem


SCHEMA = """
CREATE TABLE IF NOT EXISTS api_sessions (
    token_hash TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL UNIQUE,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    cart_id INTEGER REFERENCES orders(id),
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS api_receipts (
    owner_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    request_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response TEXT NOT NULL,
    PRIMARY KEY(owner_id, scope, request_key)
);
"""


def initialize(path):
    conn = connect(path)
    try:
        migrate(conn)
        with transaction(conn):
            if not conn.execute("SELECT 1 FROM products LIMIT 1").fetchone():
                seed_catalog(conn)
        conn.executescript(SCHEMA)
    finally:
        conn.close()


def new_session(conn, ttl):
    token = secrets.token_urlsafe(32)
    owner = uuid.uuid4().hex
    expiry = int(time.time()) + ttl
    with transaction(conn):
        conv = conversations.create_conversation(conn, owner)
        conn.execute(
            "INSERT INTO api_sessions(token_hash, owner_id, conversation_id, expires_at) VALUES (?,?,?,?)",
            (hashlib.sha256(token.encode()).hexdigest(), owner, conv["id"], expiry),
        )
    return {"token": token, "expires_at": expiry}


def authenticate(conn, authorization):
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not 20 <= len(token) <= 200:
        raise ApiProblem(401, "auth", "Cần phiên khách hàng hợp lệ.")
    row = conn.execute("SELECT * FROM api_sessions WHERE token_hash = ? AND expires_at > ?",
                       (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
    if row is None:
        raise ApiProblem(401, "auth", "Phiên đã hết hạn hoặc không hợp lệ. Hãy mở phiên mới.")
    return dict(row)


def request_key(value):
    if value is not None and not re.fullmatch(r"[A-Za-z0-9_.:-]{8,100}", value):
        raise ApiProblem(422, "validation", "Idempotency-Key phải dài 8-100 ký tự gồm chữ, số và _-:.")
    return value


def digest(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def replay(conn, owner, scope, key, payload):
    if not key:
        return None
    row = conn.execute("SELECT * FROM api_receipts WHERE owner_id=? AND scope=? AND request_key=?",
                       (owner, scope, key)).fetchone()
    if row is None:
        return None
    if row["request_hash"] != digest(payload):
        raise ApiProblem(409, "idempotency_conflict", "Khóa này đã được dùng cho nội dung khác.")
    return json.loads(row["response"])


def save_receipt(conn, owner, scope, key, payload, response):
    if key:
        conn.execute("INSERT INTO api_receipts VALUES (?,?,?,?,?)",
                     (owner, scope, key, digest(payload), json.dumps(response, ensure_ascii=False)))
