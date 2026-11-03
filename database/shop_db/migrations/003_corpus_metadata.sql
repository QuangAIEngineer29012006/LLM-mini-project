-- TV1: corpus metadata + nội dung văn bản trích xuất sẵn từ PDF. Manifest là nguồn chuẩn metadata.
DROP VIEW  IF EXISTS v_corpus_active_sections;
DROP VIEW  IF EXISTS v_corpus_sku_status;
DROP VIEW  IF EXISTS v_corpus_active_documents;
DROP TABLE IF EXISTS corpus_sync_events;
DROP TABLE IF EXISTS corpus_document_skus;
DROP TABLE IF EXISTS corpus_document_products;
DROP TABLE IF EXISTS corpus_document_sections;
DROP TABLE IF EXISTS corpus_document_versions;
DROP TABLE IF EXISTS corpus_documents;
DROP TABLE IF EXISTS corpus_releases;

CREATE TABLE corpus_releases (
    release          TEXT PRIMARY KEY,                 -- '1.0.0', '1.1.0'
    manifest_path    TEXT NOT NULL,                    -- đường dẫn tương đối từ root repo
    manifest_sha256  TEXT NOT NULL,
    is_active        INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
    synced_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE UNIQUE INDEX idx_corpus_one_active_release ON corpus_releases(is_active) WHERE is_active = 1;

CREATE TABLE corpus_documents (
    doc_id                  TEXT PRIMARY KEY,
    title                   TEXT NOT NULL,
    doc_type                TEXT NOT NULL CHECK (doc_type IN
                              ('product_spec', 'policy', 'guide', 'faq', 'sop_internal', 'admin_ops')),
    category                TEXT NOT NULL,             -- 'Áo' | 'Giày' | 'Phụ kiện' | 'general' | 'internal'
    access_level            TEXT NOT NULL CHECK (access_level IN ('public', 'staff', 'admin')),
    declared_catalog_status TEXT NOT NULL CHECK (declared_catalog_status IN
                              ('active', 'discontinued', 'not_applicable')),
    active_version          TEXT,                      -- NULL khi is_active = 0
    is_active               INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX idx_corpus_docs_filter ON corpus_documents(is_active, access_level, doc_type, category);

CREATE TABLE corpus_document_versions (
    id               INTEGER PRIMARY KEY,
    doc_id           TEXT NOT NULL REFERENCES corpus_documents(doc_id) ON DELETE CASCADE,
    version          TEXT NOT NULL,
    source_path      TEXT NOT NULL,
    author           TEXT NOT NULL,
    content_sha256   TEXT NOT NULL,
    file_size_bytes  INTEGER NOT NULL CHECK (file_size_bytes > 0),
    effective_date   TEXT NOT NULL,
    change_note      TEXT NOT NULL DEFAULT '',
    first_release    TEXT NOT NULL,
    content_text     TEXT NOT NULL DEFAULT '',        -- toàn văn đã trích xuất tự động từ PDF (chuẩn hóa LF + heading ##)
    body_text        TEXT NOT NULL DEFAULT '',        -- phần nội dung chính đã tách bỏ khung metadata đầu trang
    is_active        INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (doc_id, version)
);
CREATE UNIQUE INDEX idx_corpus_one_active_version ON corpus_document_versions(doc_id) WHERE is_active = 1;

CREATE TABLE corpus_document_sections (
    id             INTEGER PRIMARY KEY,
    version_id     INTEGER NOT NULL REFERENCES corpus_document_versions(id) ON DELETE CASCADE,
    doc_id         TEXT    NOT NULL REFERENCES corpus_documents(doc_id) ON DELETE CASCADE,
    version        TEXT    NOT NULL,
    section_index  INTEGER NOT NULL CHECK (section_index >= 1),
    section_title  TEXT    NOT NULL,
    section_text   TEXT    NOT NULL,
    char_start     INTEGER NOT NULL CHECK (char_start >= 0),
    char_end       INTEGER NOT NULL CHECK (char_end >= char_start),
    UNIQUE (doc_id, version, section_index)
);
CREATE INDEX idx_corpus_sections_doc_ver ON corpus_document_sections(doc_id, version, section_index);

CREATE TABLE corpus_document_products (
    doc_id      TEXT    NOT NULL REFERENCES corpus_documents(doc_id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    PRIMARY KEY (doc_id, product_id)
);
CREATE INDEX idx_corpus_doc_products_pid ON corpus_document_products(product_id);

CREATE TABLE corpus_document_skus (
    doc_id  TEXT NOT NULL REFERENCES corpus_documents(doc_id) ON DELETE CASCADE,
    sku     TEXT NOT NULL REFERENCES product_variants(sku) ON DELETE CASCADE,
    PRIMARY KEY (doc_id, sku)
);
CREATE INDEX idx_corpus_doc_skus_sku ON corpus_document_skus(sku);

-- Nhật ký đồng bộ, chỉ-thêm. details chỉ chứa mã lỗi/số đếm/doc_id, không chứa nội dung tài liệu.
CREATE TABLE corpus_sync_events (
    id              INTEGER PRIMARY KEY,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    actor_type      TEXT NOT NULL CHECK (actor_type IN ('staff', 'admin', 'system')),
    actor_id        TEXT NOT NULL,
    event_type      TEXT NOT NULL CHECK (event_type IN ('sync_applied', 'sync_rejected')),
    corpus_release  TEXT,
    details         TEXT NOT NULL DEFAULT '{}'
);
CREATE TRIGGER corpus_sync_events_no_update BEFORE UPDATE ON corpus_sync_events
BEGIN SELECT RAISE(ABORT, 'corpus_sync_events là append-only'); END;
CREATE TRIGGER corpus_sync_events_no_delete BEFORE DELETE ON corpus_sync_events
BEGIN SELECT RAISE(ABORT, 'corpus_sync_events là append-only'); END;

CREATE VIEW v_corpus_active_documents AS
SELECT d.doc_id, d.title, d.doc_type, d.category, d.access_level, d.declared_catalog_status,
       v.version, v.source_path, v.author, v.content_sha256, v.file_size_bytes,
       v.effective_date, v.change_note
FROM corpus_documents d
JOIN corpus_document_versions v ON v.doc_id = d.doc_id AND v.is_active = 1
WHERE d.is_active = 1;

-- Trạng thái bán LIVE: chỉ bán được khi cả sản phẩm và biến thể đều is_active = 1.
-- Lưu ý: JKT-NVY-L có product_variants.is_active = 1 nhưng products(id=7).is_active = 0 → live_sellable = 0.
CREATE VIEW v_corpus_sku_status AS
SELECT s.doc_id, s.sku, pv.product_id, p.name AS product_name,
       CASE WHEN p.is_active = 1 AND pv.is_active = 1 THEN 1 ELSE 0 END AS live_sellable,
       d.declared_catalog_status
FROM corpus_document_skus s
JOIN product_variants pv ON pv.sku = s.sku
JOIN products p          ON p.id = pv.product_id
JOIN corpus_documents d  ON d.doc_id = s.doc_id;

-- Nội dung từng mục (section) đã trích xuất sẵn từ PDF của các tài liệu đang active.
CREATE VIEW v_corpus_active_sections AS
SELECT d.doc_id, d.title, d.doc_type, d.category, d.access_level,
       v.version, v.source_path,
       s.section_index, s.section_title, s.section_text, s.char_start, s.char_end
FROM corpus_documents d
JOIN corpus_document_versions v ON v.doc_id = d.doc_id AND v.is_active = 1
JOIN corpus_document_sections s ON s.version_id = v.id
WHERE d.is_active = 1;

