# AI Live Commerce Order Assistant

Website bán hàng tích hợp trợ lý AI: xem sản phẩm, chọn biến thể, quản lý giỏ hàng, tạo/sửa đơn nháp, đặt hàng qua hội thoại nhiều lượt và **tra cứu chính sách/thông tin sản phẩm có trích dẫn nguồn (RAG)**.

## Công nghệ

React + TypeScript + Vite → FastAPI → SQLite + index vector (numpy). Gemini trích xuất intent và dữ liệu JSON; backend kiểm tra schema, SKU, tồn kho và quyền trước khi thực hiện hành động. Câu hỏi kiến thức đi qua RAG chỉ đọc. Prompt hiện hành: `shop-assistant-v5` (router) và `rag-answer-v1` (trả lời có citation).

## Bắt đầu trên Windows

Yêu cầu Python 3.12+ và Node.js 24 (hoặc nhánh 22 từ 22.12) có npm. Mở PowerShell tại thư mục vừa giải nén:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Trong `.env`, chọn `LLM_PROVIDER=gemini` và điền `GEMINI_API_KEY` để dùng Gemini. Chọn `LLM_PROVIDER=fake` để chạy kiểm thử offline. Chỉ chỉnh file `.env` trên máy; bản nguồn cung cấp `.env.example`.

**Cửa sổ 1 — backend:**

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

**Cửa sổ 2 — giao diện:**

```powershell
cd frontend
npm ci
npm run dev
```

Mở http://127.0.0.1:5173. Giữ hai cửa sổ chạy. Vite chuyển tiếp `/api` đến cổng 8000. Backend tự tạo database và seed catalog lần đầu; những lần khởi động tiếp theo giữ dữ liệu hiện có.

## Các chức năng chính

- Catalog theo danh mục; tìm kiếm, chọn màu/size, xem giá và tồn kho.
- Giỏ hàng và giao nhận; tạo đơn `pending_confirmation` với tổng tiền do server tính.
- Chat tạo đơn, hỏi giá/tồn kho, bổ sung thông tin và sửa đơn. Ví dụ: “Đặt cho tôi balo laptop xám, 15inch”; bot đối chiếu SKU và hiển thị form số lượng/giao nhận ngay trong chat, sau đó tạo đơn chờ xác nhận.
- Phiên người dùng, kiểm tra quyền, chống tạo trùng bằng idempotency và audit.

## RAG: tra cứu tài liệu có trích dẫn

### Kế thừa và bổ sung

| Kế thừa từ project LLM | Bổ sung ở project RAG |
|---|---|
| Website, API, SQLite catalog/tồn/đơn/audit, giỏ và checkout | Corpus 17 tài liệu (`data_config/`), manifest v1.0/v1.1, metadata và đối soát SKU (`database/shop_db/corpus_*`) |
| Luồng chat đặt hàng: parse, schema, grounding, SKU, tồn, quyền, idempotency | Route `knowledge_query` và câu kết hợp (`backend/chat_service.py`), prompt `shop-assistant-v5` |
| Timeout, retry hữu hạn, ngân sách gọi model, mock mode, xử lý lỗi | Ingestion, index bundle, retrieval lọc quyền, generation có citation (`src/rag/`) |
| | Role customer/staff/admin mô phỏng, trang staff/admin `#admin`, re-index/rollback, evaluation RAG (`artifacts/`) |

### Chạy

Cấu hình chạy app là **Gemini embedding** (`gemini-embedding-001`). Index có sẵn trong `artifacts/` cho cả hai provider, mỗi provider một con trỏ active:

| Provider | Con trỏ active | Bundle |
|---|---|---|
| `gemini` (chính) | `artifacts/index_manifest.json` | `artifacts/index/1.1.0-gemini`, `1.0.0-gemini` |
| `fake` (offline, test/CI) | `artifacts/index_manifest_fake.json` | `artifacts/index/1.1.0-fake`, `1.0.0-fake` |

Build lại index (Gemini tốn lượt gọi embedding; gặp giới hạn mỗi phút thì tự chờ rồi thử lại; fake build lại ra đúng sha256 cũ):

```bash
python scripts/build_index.py --provider gemini --activate
```

```bash
python scripts/build_index.py --provider fake --activate
```

Biến trong `.env`:

| Biến | Ý nghĩa |
|---|---|
| `LLM_PROVIDER=fake` / `gemini` | Router và bộ sinh câu trả lời. `fake` là rule + trích câu, chạy offline |
| `RAG_EMBEDDING_PROVIDER=gemini` / `fake` | Embedding. Chọn luôn con trỏ index tương ứng; không có index cho provider đó thì RAG báo `degraded` |
| `DEMO_STAFF_KEY`, `DEMO_ADMIN_KEY` | Khóa mở phiên staff/admin mô phỏng ở trang `#admin`. Để trống = tắt |

Ví dụ trong chat: “Balo laptop bảo hành bao lâu?”, “Báo thiếu hàng sau khi nhận cần làm gì?”, “Balo laptop bảo hành bao lâu, chốt 1 BAG-GRY-15, …” (kết hợp), “Phụ cấp ca đêm bao nhiêu?” (customer bị từ chối).

### Dữ liệu và quyền

Corpus là dữ liệu mô phỏng do nhóm viết (TV1), mỗi file có `doc_id`, tác giả, version, ngày hiệu lực, `access_level`; không có dữ liệu khách hàng hay nội bộ thật. SKU trong tài liệu được đối soát với catalog SQLite bằng `python -m database.shop_db.sku_sync_service --check`.

| Role | Đọc được | Mở phiên bằng |
|---|---|---|
| customer | `public`: thông số sản phẩm, chính sách, bảng size, FAQ | Mặc định |
| staff | `public` + `staff`: SOP hỗ trợ, hạn mức hỗ trợ phí, vận hành tồn kho | `X-Demo-Role: staff` + khóa demo |
| admin | Tất cả, kèm build/activate/rollback index | `X-Demo-Role: admin` + khóa demo |

Quyền được áp **trước** retrieval: mỗi role chỉ nạp vector của mức quyền mình được đọc. Kiến trúc router và bảng route đọc/ghi: [docs/architecture.md](docs/architecture.md).

### Báo cáo

- [Evaluation RAG](artifacts/evaluation_report.md): 30 case dev/test, Hit@3/Recall@5/MRR, citation, no-evidence, access-denied, mixed, claim review, phân tích lỗi, cải tiến có kiểm soát.
- [Re-index 1.0 → 1.1 → rollback](artifacts/reindex_report.md), bằng chứng chạy tự động ở `artifacts/reindex_evidence.json`.
- [Kịch bản demo](demo.md).

### Giới hạn

- Evaluation: bản offline (fake) trên dev/test; bản Gemini đầy đủ (router + embedding + trả lời) trên test đạt 13/17, Hit@3 1,00, câu trả lời có đúng bằng chứng 100%. Các case còn fail chủ yếu do nhãn case mơ hồ, chi tiết trong báo cáo.
- Mỗi câu hỏi kiến thức tốn 3 lượt gọi Gemini (router, embedding, trả lời); nội dung tài liệu được gửi sang Google khi build index.
- Router fake là regex: câu paraphrase như “muốn đổi màu khác được không” có thể bị hiểu thành sửa đơn.
- Phát hiện `access_denied` dựa trên danh sách chủ đề nội bộ; câu hỏi nội bộ diễn đạt lạ có thể nhận `insufficient_evidence` thay vì `access_denied` (không lộ dữ liệu, chỉ sai nhãn trạng thái).
- Role là mô phỏng bằng khóa demo; rate limit và con trỏ index nằm trên một process/một máy.

## Kiểm thử và đánh giá

```powershell
.\.venv\Scripts\python.exe scripts/test_all.py
.\.venv\Scripts\python.exe scripts/evaluate.py --provider fake --output sample_results/current/fake_main
.\.venv\Scripts\python.exe scripts/evaluate.py --provider fake --case-file tests/spec_literal_cases.json --output sample_results/current/fake_literal
.\.venv\Scripts\python.exe scripts/evaluate_rag.py --split test
.\.venv\Scripts\python.exe scripts/reindex_demo.py
cd frontend
npm test
npm run build
```

Đọc [kết quả](sample_results/STATUS.md), [rubric 0/1/2](docs/EVALUATION_REVIEW.md) và [cải tiến đã kiểm chứng](sample_results/failure_analysis.md). Bộ đánh giá gồm 29 tình huống; báo cáo phân biệt kiểm tra tự động, kết quả Gemini đã lưu và rubric do người đọc xác nhận.

## Tài liệu

- [Kiến trúc](docs/architecture.md) · [API](docs/API.md) · [Database](database/docs/DATABASE.md)
- [Demo 7 phút](docs/DEMO_RUNBOOK.md) · [Kiểm tra trình duyệt](docs/BROWSER_ACCEPTANCE.md)
- [Cấu trúc bản tổng hợp](docs/RELEASE_NOTES.md)

Giao diện duy nhất là React tại `frontend/src/`. Khi chạy demo, dùng hai lệnh backend/Vite ở trên.

## Khi npm báo EUSAGE hoặc không tìm thấy Vite

Chạy trong thư mục `frontend`:

```powershell
npm install
npm run dev
```

`npm install` đồng bộ lockfile và cài dependency. Sau khi hoàn tất có thể tiếp tục dùng `npm ci` với lockfile mới.

## Rà soát frontend ngày 22/10/2026

Xem [báo cáo React](sample_results/frontend_review_2026-10-22/REPORT.md) cho các lỗi đã sửa, test hồi quy, kiểm tra desktop/mobile và giới hạn nghiệm thu. Giao diện chạy tại http://127.0.0.1:5173. Trên macOS/Linux, dùng `.venv/bin/python` thay cho đường dẫn Python Windows trong các lệnh trên.

Luồng đặt hàng qua bot ngày 22/10: [cách hoạt động và kiểm thử Gemini thật](sample_results/chat_purchase_2026-10-22/REPORT.md).
