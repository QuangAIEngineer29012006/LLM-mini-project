"""Audit log. log_event KHÔNG tự mở transaction: ghi cùng transaction với thao tác đơn.

actor_id phải là ID nội bộ/ID phiên đã băm - KHÔNG truyền token/secret thật.
"""
import json
import re
from dataclasses import dataclass
from typing import Optional

ACTOR_TYPES = ("customer", "staff", "chat", "system")

_REDACT_KEYS = {"password", "passwd", "token", "access_token", "refresh_token", "secret",
                "api_key", "apikey", "authorization", "cookie", "session", "session_id",
                "address", "customer_name", "email", "card_number"}
_PHONE_KEYS = {"phone", "phone_number", "sdt"}
_PHONE_RE = re.compile(r"(?<![\w])\+?\d[\d .\-]{7,}\d(?![\w])")
_MAX_STR = 200


@dataclass(frozen=True)
class Ctx:
    actor_type: str
    actor_id: str
    request_id: Optional[str] = None

    def __post_init__(self):
        if self.actor_type not in ACTOR_TYPES:
            raise ValueError(f"actor_type phải thuộc {ACTOR_TYPES}")
        if not isinstance(self.actor_id, str) or not self.actor_id:
            raise ValueError("actor_id không được rỗng")


SYSTEM = Ctx("system", "system")


def _mask_phone(text: str) -> str:
    def repl(m):
        digits = re.sub(r"\D", "", m.group(0))
        return "***" + digits[-3:] if len(digits) >= 9 else m.group(0)
    return _PHONE_RE.sub(repl, text)


def sanitize(value, depth: int = 0):
    if depth > 5:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        out = {}
        for k, v in list(value.items())[:50]:
            key = str(k)[:50]
            low = key.lower()
            if low in _REDACT_KEYS:
                out[key] = "[REDACTED]"
            elif low in _PHONE_KEYS and isinstance(v, str):
                out[key] = _mask_phone(v) if _PHONE_RE.search(v) else "[REDACTED]"
            else:
                out[key] = sanitize(v, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [sanitize(x, depth + 1) for x in list(value)[:50]]
    if isinstance(value, str):
        return _mask_phone(value)[:_MAX_STR]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:_MAX_STR]


def log_event(conn, ctx: Ctx, action: str, order_id=None, old_status=None, new_status=None, details=None) -> int:
    if not isinstance(action, str) or not action or len(action) > 50:
        raise ValueError("action không hợp lệ")
    payload = json.dumps(sanitize(details), ensure_ascii=False) if details is not None else None
    cur = conn.execute(
        "INSERT INTO audit_logs (actor_type, actor_id, request_id, order_id, action, old_status, new_status, details)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (ctx.actor_type, ctx.actor_id[:100], (ctx.request_id or None) and ctx.request_id[:100],
         order_id, action, old_status, new_status, payload))
    return cur.lastrowid


def list_events(conn, order_id=None, request_id=None, limit: int = 100) -> list:
    sql, params = "SELECT * FROM audit_logs WHERE 1=1", []
    if order_id is not None:
        sql += " AND order_id = ?"
        params.append(order_id)
    if request_id is not None:
        sql += " AND request_id = ?"
        params.append(request_id)
    sql += " ORDER BY id ASC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    out = []
    for r in conn.execute(sql, params):
        d = dict(r)
        d["details"] = json.loads(d["details"]) if d["details"] else None
        out.append(d)
    return out
