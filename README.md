# AI Live Commerce Order Assistant

Website bán hàng tích hợp trợ lý AI: xem sản phẩm, chọn biến thể, quản lý giỏ hàng, tạo/sửa đơn nháp và đặt hàng qua hội thoại nhiều lượt.

## Công nghệ

React + TypeScript + Vite → FastAPI → SQLite. Gemini trích xuất intent và dữ liệu JSON; backend kiểm tra schema, SKU, tồn kho và quyền trước khi thực hiện hành động. Prompt hiện hành: `shop-assistant-v3`.

## Bắt đầu trên Windows

Yêu cầu Python 3.12+ và Node.js có npm. Mở PowerShell tại thư mục vừa giải nén:

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
- Chat tạo đơn, hỏi giá/tồn kho, bổ sung thông tin và sửa đơn.
- Phiên người dùng, kiểm tra quyền, chống tạo trùng bằng idempotency và audit.

## Kiểm thử và đánh giá

```powershell
.\.venv\Scripts\python.exe scripts/test_all.py
.\.venv\Scripts\python.exe scripts/evaluate.py --provider fake --output sample_results/current/fake_main
.\.venv\Scripts\python.exe scripts/evaluate.py --provider fake --case-file tests/spec_literal_cases.json --output sample_results/current/fake_literal
cd frontend
npm run build
```

Đọc [kết quả](sample_results/STATUS.md), [rubric 0/1/2](docs/EVALUATION_REVIEW.md) và [cải tiến đã kiểm chứng](sample_results/failure_analysis.md). Bộ đánh giá gồm 29 tình huống; báo cáo phân biệt kiểm tra tự động, kết quả Gemini đã lưu và rubric do người đọc xác nhận.

## Tài liệu

- [Kiến trúc](docs/architecture.md) · [API](docs/API.md) · [Database](database/docs/DATABASE.md)
- [Demo 7 phút](docs/DEMO_RUNBOOK.md) · [Kiểm tra trình duyệt](docs/BROWSER_ACCEPTANCE.md)
- [Cấu trúc bản tổng hợp](docs/RELEASE_NOTES.md)

Giao diện chính là React tại `frontend/src/`. `app.py`, `views/` và các module Python trong `frontend/` là giao diện Streamlit tương thích và phục vụ bộ test cũ. Khi chạy bản demo chính, dùng hai lệnh backend/Vite ở trên.

## Khi npm báo EUSAGE hoặc không tìm thấy Vite

Chạy trong thư mục `frontend`:

```powershell
npm install
npm run dev
```

`npm install` đồng bộ lockfile và cài dependency. Sau khi hoàn tất có thể tiếp tục dùng `npm ci` với lockfile mới.
