# Kiểm chứng ngày 20/10/2026

Môi trường: Python 3.12.13, FastAPI 0.153.0, Pydantic 2.14.1, Streamlit 1.66.0. Dữ liệu kiểm thử là dữ liệu demo, mỗi bài integration dùng SQLite tạm.

| Kiểm tra | Lệnh / bằng chứng | Kết quả |
|---|---|---|
| Frontend/backend/LLM | `python -m unittest discover -s tests -t .` | 51 test PASS |
| Database hiện có | Tại `database/`: `../.venv/bin/python -m unittest discover -s tests -t .` | 79 test PASS |
| Workflow evaluation | `python scripts/evaluate.py` | 18/18 case PASS; xem `evaluation_fake.md` và JSON |
| Streamlit → HTTP → SQLite | `python scripts/smoke_frontend.py` | 10 bước trên 6 màn hình PASS; xem `frontend_smoke.json` |
| Source database | So SHA-256 các file database đã track với HEAD trước/sau | Không đổi file hiện có; chỉ thêm `database/tests/__init__.py` để chạy test đúng package |
| Python syntax | `python -m compileall -q backend src scripts tests` | PASS |
| Diff whitespace | `git -c core.whitespace=cr-at-eol diff --check` | PASS; giữ CRLF của file frontend hiện có |

Các test backend bao gồm token hết hạn/thu hồi (kể cả thu hồi trong lúc chờ LLM), IDOR giữa hai phiên, quantity sai kiểu, giả giá/tồn/trạng thái, rollback lỗi tồn kho/đổi SKU, checkout/chat đồng thời cùng key chỉ ra một đơn, audit không lộ PII và parser/schema/evidence.

HTTP client Gemini được test với response mock: schema payload, timeout, 429/Retry-After, retry tối đa 2, không retry 4xx/refusal, response provider lỗi. Chưa gọi Google thật do chưa cấu hình key; không có điểm benchmark Gemini. Smoke dùng Streamlit AppTest, chưa kiểm tra ảnh render trên trình duyệt thật hoặc bố cục responsive.

Hai cảnh báo từ thư viện khi chạy test: Starlette hiện cảnh báo deprecation với TestClient dùng httpx; Streamlit AppTest hiện cảnh báo missing ScriptRunContext ở thread khởi tạo. Cả hai không tạo exception trong ứng dụng, và các bước test đều hoàn tất.
