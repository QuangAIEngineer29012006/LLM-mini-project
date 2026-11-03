# Kiểm chứng bản tích hợp — 03/11/2026

- Source backend và công cụ evaluation từ evaluation-demo; giao diện React từ bản UI mới.
- `scripts/test_all.py`: 111 test root + 112 test database = 223 PASS.
- `scripts/evaluate.py --provider fake`: 18/18; bộ `spec_literal_cases.json`: 11/11.
- `scripts/evaluate_rag.py --split test --provider fake --embedding fake`: contract 13/17, strict relevance-label 11/17; Hit@3 0,700, Recall@5 0,683, MRR 0,650.
- `review_evaluation.py validate`: evidence và cấu trúc form hợp lệ, gồm 29 case.
- Vitest: 15/15; TypeScript kiểm tra mã nguồn thành công; Vite build thành công 32 module.
- Build dùng cấu hình production tương đương với `configFile=false` để tránh lỗi truy cập thư mục cha của sandbox; file Vite gốc chỉ bổ sung proxy `/api` cho dev.
- Backend được kiểm tra bằng FastAPI TestClient và SQLite tạm; đây là unit/integration test, chưa phải kết quả tương tác UI trình duyệt.

Môi trường dependency hiện có trong workspace kiểm thử. Không gọi Gemini mới trong lần chạy này. Metadata bản Gemini đã lưu giữ trong báo cáo riêng.

Cập nhật lockfile: tạo lại từ package.json trong thư mục sạch, npm 11.19.1 / Node 24.22.0. `npm ci --no-audit --no-fund` cài thành công 68 package. TypeScript qua kiểm tra; Vite build 31 module thành công với config được import trực tiếp (tránh giới hạn đọc thư mục cha của sandbox).
