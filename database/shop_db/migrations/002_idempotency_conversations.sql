-- Mỗi (owner_id, idempotency_key) chỉ tạo tối đa 1 đơn. request_hash phát hiện cùng key nhưng nội dung khác.
ALTER TABLE orders ADD COLUMN idempotency_key TEXT;
ALTER TABLE orders ADD COLUMN request_hash TEXT;
CREATE UNIQUE INDEX idx_orders_idem ON orders(owner_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE TABLE conversations (
    id             TEXT    PRIMARY KEY,
    owner_id       TEXT    NOT NULL,
    state          TEXT    NOT NULL DEFAULT 'idle',
    pending_intent TEXT,
    context        TEXT    NOT NULL DEFAULT '{}',
    last_order_id  INTEGER REFERENCES orders(id),
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX idx_conv_owner ON conversations(owner_id, updated_at);

CREATE TABLE conversation_messages (
    id              INTEGER PRIMARY KEY,
    conversation_id TEXT    NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT    NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX idx_msg_conv ON conversation_messages(conversation_id, id);
