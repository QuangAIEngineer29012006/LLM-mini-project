# Kiến trúc hệ thống

React gọi FastAPI; FastAPI định tuyến tin nhắn sang **luồng đặt hàng** (kế thừa từ project LLM), **luồng tra cứu tài liệu** (RAG, mới) hoặc **chuyển nhân viên**. Chỉ luồng đặt hàng được phép ghi đơn; RAG chỉ đọc.

```mermaid
flowchart TD
    UI["React<br/>chat, catalog, giỏ, đơn, trang staff/admin"] --> API["FastAPI<br/>phiên + role, rate limit, schema"]
    API --> GUARD{"Regex an toàn<br/>(chat_service.UNSAFE)"}
    GUARD -- nguy hiểm --> HANDOFF["handoff<br/>không gọi model"]
    GUARD -- ổn --> ROUTER["Router LLM<br/>Extraction: intent + knowledge_question"]
    ROUTER -- "order / giá / tồn" --> ORDER["Luồng đặt hàng<br/>parse, grounding, SKU, tồn, quyền"]
    ROUTER -- knowledge_query --> RAG["RAG (chỉ đọc)<br/>quyền → retrieval → generation → citation"]
    ROUTER -- "kết hợp" --> BOTH["RAG cho phần hỏi<br/>+ luồng đặt hàng cho phần action"]
    ROUTER -- "mơ hồ / rủi ro" --> HANDOFF
    ORDER --> DB[("SQLite<br/>catalog, tồn, đơn, audit")]
    RAG --> INDEX[("Index bundle<br/>vector theo mức quyền + chunk map")]
    RAG -. "resolve citation, release" .-> DB
    BOTH --> ORDER
    BOTH --> RAG
```

## Route: quyền đọc, side effect, điểm validation

| Route | Đọc | Được ghi (side effect) | Validation bắt buộc |
|---|---|---|---|
| `create_order`, `update_order` | Catalog, tồn, đơn của phiên | Đơn nháp, dòng hàng, hội thoại, audit | Schema strict, grounding theo câu khách, SKU tồn tại duy nhất, số lượng do khách nêu, tồn kho, giao nhận, quyền sở hữu đơn, idempotency, kiểm tra lại phiên/revision trong transaction |
| `check_price`, `check_stock`, `browse_catalog` | Catalog, tồn | Chỉ hội thoại + audit | Grounding; giá/tồn đọc lại từ DB |
| `knowledge_query` (RAG) | Index đúng mức quyền của role, metadata corpus | Chỉ hội thoại + audit (chunk ID, status) | Quyền áp **trước** retrieval; citation phải thuộc context, resolve được tới file và version active; output JSON strict |
| Kết hợp | Như hai dòng trên | Chỉ phần order, qua đúng các validation của order | Kết quả RAG không bao giờ được truyền vào hàm có side effect; action chỉ chạy khi SKU/mã đơn/quyền đủ rõ |
| `handoff` | — | Hội thoại + audit | — |
| `/api/admin/reindex` | Manifest, bundle | Metadata corpus, con trỏ index | Chỉ role admin; bundle kiểm tra sha256 trước khi activate; đồng bộ DB và con trỏ cùng release |

## Thành phần

| Thành phần | Vị trí | Vai trò |
|---|---|---|
| UI | `frontend/src/App.tsx`, `Knowledge.tsx`, `AdminPage.tsx` | Chat có nhãn route, trạng thái, citation mở được nguồn; trang staff/admin |
| API | `backend/main.py`, `models.py`, `storage.py` | Endpoint, phiên + role mô phỏng, rate limit, idempotency |
| Router + order | `backend/chat_service.py`, `services.py`, `catalog_chat.py` | Điều phối hội thoại, tách phần kiến thức và phần action |
| LLM | `src/prompts.py`, `llm_client.py`, `parser.py` | Prompt `shop-assistant-v5` (thêm `knowledge_query`), Gemini/Fake, parse + grounding |
| RAG | `src/rag/` | `chunker` → `embedder` → `index` (bundle) → `retriever` → `answer` (generator) → `service` (quyền, cache, citation, re-index) |
| Dữ liệu corpus | `data_config/`, `database/shop_db/corpus_*.py`, `sku_sync_service.py` | Tài liệu Markdown, manifest release, metadata, đối soát SKU |
| Evaluation | `scripts/evaluate_rag.py`, `scripts/reindex_demo.py`, `artifacts/` | Metric RAG, kịch bản re-index |

## RAG pipeline

1. **Ingestion** (`scripts/build_index.py`): đọc manifest, kiểm tra file/encoding/doc_id/metadata qua `validate_manifest`, chia mỗi section `##` thành một chunk mang `chunk_id`, `doc_id`, `version`, `source`, `access_level`, offset, SKU.
2. **Index bundle** (`artifacts/index/<release>-<provider>/`): một ma trận vector cho mỗi mức quyền + `chunks.jsonl` + `index_manifest.json` (embedding, metric, chunk config, release, sha256). `artifacts/index_manifest.json` là con trỏ active. Nạp index sẽ kiểm tra sha256 và số dòng; lệch thì `degraded`.
3. **Quyền trước retrieval**: role chỉ nạp ma trận của các mức được phép (customer → `public`). Câu hỏi thuộc chủ đề nội bộ trả `access_denied` trước khi tạo candidate.
4. **Retrieval**: top-k cosine, cộng điểm khi câu hỏi nêu SKU, bảo đảm có chunk chính sách cho câu hỏi điều kiện nghiệp vụ. Điểm chỉ để xếp hạng/debug, không phải độ chắc chắn.
5. **Generation**: Gemini với prompt tách data/instruction (`src/rag/prompts.py`), hoặc generator extractive offline. Output `{status, answer, citations, missing_information}`.
6. **Kiểm tra citation**: mọi chunk được trích phải nằm trong context và resolve được tới file thật, đúng sha256, đúng version active; không thì hạ về `insufficient_evidence`/`error`.

## Phiên, role và tính nhất quán

`api_sessions` có thêm cột `role` (`customer` mặc định). Phiên `staff`/`admin` chỉ mở được khi gửi đúng khóa demo (`DEMO_STAFF_KEY`, `DEMO_ADMIN_KEY`); đây là role mô phỏng cho demo, không phải hệ thống đăng nhập. Lời gọi model (router và RAG) chạy **trước** transaction ghi; sau đó backend kiểm tra lại phiên, biên nhận idempotency và revision hội thoại. Cache câu trả lời RAG có key `index_id + role + câu hỏi` và bị xóa mỗi lần activate index.

## Cấu hình

`LLM_PROVIDER` (`fake`/`gemini`) chọn router và generator; `RAG_EMBEDDING_PROVIDER` (`fake`/`gemini`) chọn embedding và con trỏ index của provider đó (`artifacts/index_manifest.json` cho Gemini, `artifacts/index_manifest_fake.json` cho fake). Ngưỡng context đi theo model embedding (Gemini 0,65, fake 0,12) vì điểm cosine của hai model không cùng thang. Cấu hình chạy app: Gemini cho cả hai. Audit lưu route, intent, `rag_status`, chunk ID được trích, index_id, latency; không lưu nội dung context, khóa hay dữ liệu cá nhân.
