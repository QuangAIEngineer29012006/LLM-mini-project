# Bản tổng hợp

- UI: React/TypeScript/Vite từ thư mục `LLM-mini-project` của thành viên thiết kế giao diện.
- Backend/database: cùng nền code của hai thư mục Desktop.
- Evaluation/demo: bổ sung bộ công cụ từ bản `evaluation-demo` đã chuẩn bị, gồm sửa đóng kết nối SQLite, UTF-8 trên Windows và regression của FakeLLM.
- Gộp README, kiến trúc và kịch bản chạy theo giao diện React.
- Chỉ giữ báo cáo có vai trò rõ: kết quả hiện tại, input/output Gemini trước/sau và form rubric. Log probe/debug rời vẫn còn trong hai thư mục nguồn.
- Không đóng gói `.git`, `.venv`, `node_modules`, Node/npm binaries, `.env`, cache hoặc database phiên làm việc. Máy nhận cài dependency từ manifest và khởi tạo DB bằng seed.

Các module Streamlit vẫn giữ ở đường dẫn cũ để tương thích các test; React là giao diện chính. `sample_results/STATUS.md` là điểm vào duy nhất để đọc số liệu.

Sửa ánh xạ ảnh nón/balo trên UI để tên sản phẩm khớp ảnh minh họa.
