CREATE TABLE products (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    description TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);
CREATE INDEX idx_products_category ON products(category);

CREATE TABLE product_variants (
    sku          TEXT    PRIMARY KEY,
    product_id   INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    variant_name TEXT    NOT NULL,
    color        TEXT,
    size         TEXT,
    price        INTEGER NOT NULL CHECK (price >= 0),
    is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);
CREATE INDEX idx_variants_product ON product_variants(product_id);

CREATE TABLE inventory (
    sku        TEXT    PRIMARY KEY REFERENCES product_variants(sku) ON DELETE CASCADE,
    quantity   INTEGER NOT NULL CHECK (quantity >= 0),
    updated_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Alias dùng cho tìm kiếm/mapping của chat. sku = NULL: alias của cả sản phẩm.
CREATE TABLE product_aliases (
    id               INTEGER PRIMARY KEY,
    product_id       INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    sku              TEXT    REFERENCES product_variants(sku) ON DELETE CASCADE,
    alias            TEXT    NOT NULL,
    alias_normalized TEXT    NOT NULL
);
CREATE INDEX idx_alias_norm ON product_aliases(alias_normalized);

CREATE TABLE orders (
    id            INTEGER PRIMARY KEY,
    owner_id      TEXT    NOT NULL,
    source        TEXT    NOT NULL CHECK (source IN ('web', 'chat')),
    status        TEXT    NOT NULL CHECK (status IN
                    ('cart', 'pending_confirmation', 'confirmed', 'cancelled')),
    customer_name TEXT,
    phone         TEXT,
    address       TEXT,
    total_amount  INTEGER NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX idx_orders_owner ON orders(owner_id, updated_at);

-- unit_price / product_name / variant_name là SNAPSHOT tại thời điểm backend xác nhận.
CREATE TABLE order_items (
    id           INTEGER PRIMARY KEY,
    order_id     INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    sku          TEXT    NOT NULL REFERENCES product_variants(sku),
    product_name TEXT    NOT NULL,
    variant_name TEXT    NOT NULL,
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    unit_price   INTEGER NOT NULL CHECK (unit_price >= 0),
    line_total   INTEGER NOT NULL CHECK (line_total >= 0),
    UNIQUE (order_id, sku)
);

-- Nhật ký chỉ-thêm (append-only). details là JSON đã lọc dữ liệu nhạy cảm.
CREATE TABLE audit_logs (
    id         INTEGER PRIMARY KEY,
    created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    actor_type TEXT    NOT NULL CHECK (actor_type IN ('customer', 'staff', 'chat', 'system')),
    actor_id   TEXT    NOT NULL,
    request_id TEXT,
    order_id   INTEGER REFERENCES orders(id),
    action     TEXT    NOT NULL,
    old_status TEXT,
    new_status TEXT,
    details    TEXT
);
CREATE INDEX idx_audit_order ON audit_logs(order_id, id);
CREATE INDEX idx_audit_request ON audit_logs(request_id);

CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_logs
BEGIN SELECT RAISE(ABORT, 'audit_logs là append-only'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_logs
BEGIN SELECT RAISE(ABORT, 'audit_logs là append-only'); END;
