"""Lưu hội thoại và ngữ cảnh theo phiên (chat workflow dùng).

- context là dict JSON (các slot đã thu thập: items, tên, SĐT, địa chỉ, đơn mục tiêu...).
- Context có thể chứa thông tin giao nhận vì workflow cần dùng lại; thông tin này KHÔNG được chép sang audit.
- Service không kiểm tra chủ sở hữu: Minh (TV1) kiểm tra owner_id trước khi gọi.
- STATES có thể chỉnh theo thiết kế thống nhất với TV1.
"""
import json
import uuid

from .db import NOW_SQL, transaction
from .errors import ConversationNotFound, ValidationError
from .order_common import fetch_order

STATES = ("idle", "collecting_info", "awaiting_confirmation", "handoff")
ROLES = ("user", "assistant", "system")
MAX_CONTEXT_BYTES = 8192
MAX_MESSAGE_CHARS = 2000
MAX_MESSAGES_PER_CONVERSATION = 200

_UNSET = object()


def _dump_context(ctx) -> str:
    if not isinstance(ctx, dict):
        raise ValidationError("context phải là object", field="context")
    try:
        raw = json.dumps(ctx, ensure_ascii=False)
    except (TypeError, ValueError):
        raise ValidationError("context phải serialize được sang JSON", field="context")
    if len(raw.encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ValidationError(f"context vượt quá {MAX_CONTEXT_BYTES} byte", field="context")
    return raw


def _to_dict(r) -> dict:
    return {"id": r["id"], "owner_id": r["owner_id"], "state": r["state"],
            "pending_intent": r["pending_intent"], "context": json.loads(r["context"]),
            "last_order_id": r["last_order_id"], "created_at": r["created_at"], "updated_at": r["updated_at"]}


def _fetch(conn, conversation_id):
    r = conn.execute("SELECT * FROM conversations WHERE id = ?", (str(conversation_id)[:64],)).fetchone()
    if r is None:
        raise ConversationNotFound("Không tìm thấy hội thoại", conversation_id=str(conversation_id)[:64])
    return r


def _check_state(state):
    if state not in STATES:
        raise ValidationError(f"state phải thuộc {STATES}", field="state")


def create_conversation(conn, owner_id) -> dict:
    if not isinstance(owner_id, str) or not (1 <= len(owner_id.strip()) <= 100):
        raise ValidationError("owner_id không hợp lệ", field="owner_id")
    cid = uuid.uuid4().hex
    conn.execute("INSERT INTO conversations (id, owner_id) VALUES (?, ?)", (cid, owner_id.strip()))
    return get_conversation(conn, cid)


def get_conversation(conn, conversation_id) -> dict:
    return _to_dict(_fetch(conn, conversation_id))


def get_or_create_conversation(conn, owner_id, conversation_id=None) -> dict:
    if conversation_id is not None:
        return get_conversation(conn, conversation_id)
    return create_conversation(conn, owner_id)


def get_latest_conversation(conn, owner_id):
    r = conn.execute("SELECT * FROM conversations WHERE owner_id = ? ORDER BY updated_at DESC, rowid DESC LIMIT 1",
                     (owner_id,)).fetchone()
    return _to_dict(r) if r else None


def update_conversation(conn, conversation_id, *, context=_UNSET, merge=None, state=_UNSET,
                        pending_intent=_UNSET, last_order_id=_UNSET) -> dict:
    with transaction(conn):
        row = _fetch(conn, conversation_id)
        sets, params = [], []
        if context is not _UNSET and merge is not None:
            raise ValidationError("Chỉ dùng context hoặc merge, không dùng cả hai")
        if context is not _UNSET:
            sets.append("context = ?"); params.append(_dump_context(context))
        if merge is not None:
            if not isinstance(merge, dict):
                raise ValidationError("merge phải là object", field="merge")
            current = json.loads(row["context"])
            for k, v in merge.items():
                if v is None:
                    current.pop(k, None)
                else:
                    current[k] = v
            sets.append("context = ?"); params.append(_dump_context(current))
        if state is not _UNSET:
            _check_state(state)
            sets.append("state = ?"); params.append(state)
        if pending_intent is not _UNSET:
            if pending_intent is not None and (not isinstance(pending_intent, str) or len(pending_intent) > 50):
                raise ValidationError("pending_intent không hợp lệ", field="pending_intent")
            sets.append("pending_intent = ?"); params.append(pending_intent)
        if last_order_id is not _UNSET:
            if last_order_id is not None:
                fetch_order(conn, last_order_id)
            sets.append("last_order_id = ?"); params.append(last_order_id)
        sets.append(f"updated_at = {NOW_SQL}")
        conn.execute(f"UPDATE conversations SET {', '.join(sets)} WHERE id = ?", (*params, row["id"]))
        return get_conversation(conn, row["id"])


def reset_conversation(conn, conversation_id) -> dict:
    return update_conversation(conn, conversation_id, context={}, state="idle",
                               pending_intent=None, last_order_id=None)


def add_message(conn, conversation_id, role, content) -> dict:
    if role not in ROLES:
        raise ValidationError(f"role phải thuộc {ROLES}", field="role")
    if not isinstance(content, str) or not content.strip():
        raise ValidationError("Nội dung tin nhắn rỗng", field="content")
    with transaction(conn):
        _fetch(conn, conversation_id)
        cur = conn.execute("INSERT INTO conversation_messages (conversation_id, role, content) VALUES (?,?,?)",
                           (str(conversation_id), role, content.strip()[:MAX_MESSAGE_CHARS]))
        conn.execute(f"DELETE FROM conversation_messages WHERE conversation_id = ? AND id NOT IN ("
                     "SELECT id FROM conversation_messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?)",
                     (str(conversation_id), str(conversation_id), MAX_MESSAGES_PER_CONVERSATION))
        conn.execute(f"UPDATE conversations SET updated_at = {NOW_SQL} WHERE id = ?", (str(conversation_id),))
        r = conn.execute("SELECT * FROM conversation_messages WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(r)


def get_messages(conn, conversation_id, limit: int = 20) -> list:
    _fetch(conn, conversation_id)
    limit = max(1, min(int(limit), MAX_MESSAGES_PER_CONVERSATION))
    rows = conn.execute("SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
                        (str(conversation_id), limit)).fetchall()
    return [dict(r) for r in reversed(rows)]
