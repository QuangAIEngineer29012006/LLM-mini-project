# Re-index report: corpus 1.0.0 → 1.1.0 → rollback

Bằng chứng tự động: [`artifacts/reindex_evidence.json`](reindex_evidence.json), sinh bằng `python scripts/reindex_demo.py`.
Script chạy qua API thật (`/api/admin/reindex`, `/api/knowledge`, `/api/admin/index`) trên DB và thư mục index tạm, embedding `fake`, nên không đụng DB đang dùng và không tốn quota.
Test tự động tương ứng: `tests/test_rag.py::KnowledgeApiTests::test_reindex_switches_release_and_rolls_back`.

## 1. Diff nghiệp vụ và chunk bị ảnh hưởng

Chỉ tài liệu `DOC-POL-RETURN` đổi (v1.0 → v1.1). 16 tài liệu còn lại giữ nguyên version và nội dung.

| Thay đổi | Section | Chunk cũ → mới |
|---|---|---|
| Sửa | Đổi size hoặc màu do đổi ý: thời hạn **7 ngày → 14 ngày** | `DOC-POL-RETURN@1.0#02` → `DOC-POL-RETURN@1.1#02` |
| Thêm | Ngoại lệ nón lưỡi trai: `CAP-NVY-F`, `CAP-BLK-F` không đổi do đổi ý (vẫn đổi lỗi nhà sản xuất) | — → `DOC-POL-RETURN@1.1#03` |
| Giữ nguyên | Phạm vi áp dụng, Lỗi nhà sản xuất, Báo thiếu hàng, Hủy/sửa đơn, Hoàn tiền, Trường hợp không áp dụng | nội dung trùng, chỉ đổi tiền tố chunk_id theo version |

Chunk ID gắn version (`<doc_id>@<version>#<n>`) nên citation luôn trỏ đúng bản đã dùng để trả lời.

## 2. Snapshot index cũ / mới

| Release | index_id | Chunk (public / staff / admin) | Build lại khớp bundle đã commit |
|---|---|---|---|
| 1.0.0 | `1.0.0-fake-17a26f86` | 85 (63 / 13 / 9) | Có (sha256 từng file trùng) |
| 1.1.0 | `1.1.0-fake-143be753` | 86 (64 / 13 / 9) | Có |

Mỗi bundle ở `artifacts/index/<release>-<provider>/` gồm `vectors_public.npy`, `vectors_staff.npy`, `vectors_admin.npy`, `chunks.jsonl`, `index_manifest.json`. Manifest ghi embedding provider/model/revision, dimension, normalization, metric, cách encode query/document, chunk config, release và manifest corpus nguồn, sha256 từng file. `artifacts/index_manifest.json` là con trỏ tới bundle đang active.

## 3. Verification query

Câu kiểm chứng: “Đổi size hoặc màu do đổi ý được hỗ trợ trong bao lâu?” (role customer).

| Bước | Index / DB release | Câu trả lời | Citation |
|---|---|---|---|
| Bắt đầu | 1.0.0 / 1.0.0 | “… trong vòng **7 ngày** …” | `DOC-POL-RETURN@1.0#02` |
| Activate 1.1.0 | 1.1.0 / 1.1.0 | “… trong vòng **14 ngày** …” | `DOC-POL-RETURN@1.1#02` |
| Rollback 1.0.0 | 1.0.0 / 1.0.0 | “… **7 ngày** …” | `DOC-POL-RETURN@1.0#02` |
| Activate lại 1.1.0 | 1.1.0 / 1.1.0 | “… **14 ngày** …” | `DOC-POL-RETURN@1.1#02` |

Index active sau cùng chỉ chứa `DOC-POL-RETURN` version `1.1` (trường `active_index_versions_of_DOC-POL-RETURN` trong evidence). Hai version không bao giờ được nạp cùng lúc: mỗi bundle build từ đúng một manifest release.

Câu kiểm chứng thứ hai (“Nón lưỡi trai CAP-NVY-F có được đổi do đổi ý không?”) ở 1.1.0 trích đúng section mới `@1.1#03`. Ở 1.0.0, khi chưa có ngoại lệ, bộ trả lời fake lại trích đoạn **màu và mã biến thể của nón** (`DOC-PRD-005@1.0#02`) thay vì chính sách đổi trả chung. Đây là một near-miss của generator extractive, đã ghi trong [evaluation_report.md](evaluation_report.md) mục phân tích lỗi.

## 4. Activate, cache invalidation, rollback

`POST /api/admin/reindex {"action": "activate", "release": "x.y.z"}` (chỉ admin) chạy theo thứ tự:

1. Nạp và kiểm tra bundle (sha256, số chunk từng mức quyền khớp ma trận vector). Bundle hỏng thì dừng, không đổi gì.
2. `sync_from_manifest` đồng bộ metadata corpus trong SQLite trong một transaction. Lệch SKU/catalog thì rollback, không đổi con trỏ.
3. Ghi con trỏ `artifacts/index_manifest.json` bằng file tạm + `os.replace` (nguyên tử).
4. Nạp lại index, **xóa toàn bộ cache câu trả lời** (`cache_entries_right_after_activate = 0` ở cả ba lần chuyển), kiểm tra release index = release DB.

Rollback là activate release cũ; bundle cũ vẫn còn trên đĩa nên không phải build lại.
Nếu index và DB lệch release (ví dụ ai đó đổi con trỏ bằng tay), service chuyển `degraded`: route kiến thức trả `status=error` và **không trích dẫn** theo mapping không đáng tin (`test_release_mismatch_degrades_instead_of_citing`).

## 5. Customer route không chạm tài liệu nội bộ

- Mỗi role chỉ nạp ma trận vector của các mức quyền được phép; customer chỉ có `vectors_public.npy`.
- Script lấy nội dung từng chunk `staff`/`admin` (22 chunk) làm câu hỏi của customer: **0** chunk nội bộ xuất hiện trong candidate, context hay citation; **0** trong cache của customer (cache key gồm `index_id + role + câu hỏi`).
- Câu hỏi thuộc chủ đề nội bộ (phụ cấp, hạn mức hỗ trợ, SOP…) trả `access_denied` **trước** retrieval, nên không tạo candidate nào.
- Endpoint mở nguồn trích dẫn trả cùng một lỗi 404 cho chunk ngoài quyền và chunk không tồn tại.

## 6. Audit / log

| Nguồn | Nội dung ghi | Kiểm tra |
|---|---|---|
| `corpus_sync_events` | `sync_applied`, actor `admin`/`system`, release | Không chứa nội dung tài liệu |
| `audit_logs` | `index_activate` (release, index_id), `knowledge_query` (role, status, chunk_id, index_id) | Không chứa đoạn văn nội bộ, không chứa khóa demo, không có số điện thoại |

Khóa demo, API key và nội dung context không được ghi vào log. Log chỉ có chunk ID để truy vết.

## 7. Giới hạn

- Kịch bản tự động chạy với embedding `fake` để tái lập được và không tốn quota. Index Gemini (định dạng của TV2, `src/rag/gemini_index.py`) cũng đã build cho cả hai release (`artifacts/index/1.0.0-gemini`: 85 chunk, `1.1.0-gemini`: 86 chunk). Nút Activate trên trang admin của app (đang chạy Gemini) chuyển con trỏ `artifacts/index_manifest.json` theo đúng quy trình ở mục 4; test `tests/test_rag.py::GeminiIndexTests::test_activate_switches_release_and_rolls_back` chạy quy trình này trên hai index Gemini thật (embedding câu hỏi được giả lập, không gọi API). Index Gemini không tái lập từng byte nếu Google đổi model.
- Chunk ID của index Gemini (`DOC-POL-RETURN:2`) không gắn version như bản fake; citation vẫn mang trường `version` riêng và được kiểm tra với release active.
- Activate không có bước duyệt hai người; demo chỉ yêu cầu role admin.
- Con trỏ index là file trên một máy; chạy nhiều process cần cơ chế đồng bộ khác.
