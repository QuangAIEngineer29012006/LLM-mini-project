# Nghiệm thu trên trình duyệt thật

Kiểm tra giao diện React tại cổng 5173 với FastAPI tại cổng 8000. Ghi nhận kết quả tương tác trong Chrome/Edge theo các tình huống dưới đây.

## Chuẩn bị

- Dùng bản UI dự định nộp, ghi `git rev-parse HEAD`, trình duyệt/phiên bản, Windows, ngày kiểm tra và người kiểm tra.
- Bật backend thật, SQLite demo riêng và `LLM_PROVIDER=fake` cho lượt kiểm tra giao diện. React gọi HTTP API qua Vite proxy. Phần ngôn ngữ Gemini dùng kết quả đánh giá riêng; không coi fake là model thật.
- Một cửa sổ thường, một cửa sổ ẩn danh; dùng dữ liệu giao nhận mock. Không xóa database đang có dữ liệu cần giữ.
- DevTools responsive: 1366×768 và 390×844. Kiểm tra catalog, chi tiết, giỏ, checkout, đơn hàng và chat, lỗi console và request thất bại.
- Lưu ảnh/video/log đã che token, số điện thoại, địa chỉ nếu không cần thiết vào `sample_results/browser_evidence/`. Không commit cookie/header Authorization hay key.

## Các bước cần thực hiện

| Case | Thao tác | Expected |
|---|---|---|
| B01 | Mở catalog; tìm áo thun; xóa từ khóa | Catalog từ API, kết quả/empty state rõ |
| B02 | Mở áo thun; chọn trắng M rồi đen M | Hết hàng bị chặn; biến thể còn hàng thêm được |
| B03 | Thêm 2 áo đen M; đổi 3; xóa | Giỏ và tổng tiền theo server; có empty state |
| B04 | Gửi giao nhận trống, SĐT sai | Có lỗi từng field; chưa tạo đơn |
| B05 | Điền giao nhận mock, gửi; thử nhấp lặp | Có đơn pending_confirmation; một request replay không tạo hai đơn |
| B06 | Sửa số lượng và biến thể đơn | Kiểm tra lại tồn kho, tổng tiền; không đổi đơn khác |
| B07 | Chat đặt áo đen M rồi bổ sung giao nhận | Đơn chat xuất hiện trong Đơn hàng cùng phiên |
| B08 | Trong lúc thiếu giao nhận, hỏi giá/tồn rồi tiếp tục | Số liệu đúng DB, không mất yêu cầu mua đang dở |
| B09 | Đặt quá tồn và hỏi hàng không tồn tại | Không tạo đơn sai; hướng dẫn điều chỉnh |
| B10 | Gửi nguyên câu injection trong đề; hỏi sửa đơn mơ hồ | Không lộ key/xóa đơn; hỏi mã hoặc handoff |
| B11 | Trên instance kiểm thử, dùng DevTools chặn `/api/*`, rồi bỏ chặn để thử lại | Có lỗi rõ, không báo thành công; bỏ chặn request và thử lại để phục hồi |
| B12 | Tải lại trang khi đang xem đơn và sau checkout | Không crash hoặc tạo thêm đơn; ghi rõ hành vi phiên thực tế |
| B13 | Mở ẩn danh; kiểm tra API đọc/sửa ID đơn của phiên thường | API từ chối; UI không hiển thị dữ liệu phiên khác |
| B14 | Dùng đủ trang ở 1366×768 | Nút, form, bảng, chat không bị che/chồng chữ |
| B15 | Dùng đủ trang ở 390×844 | Điều hướng, nhập liệu, gửi chat và cuộn dùng được |

B11 chỉ thay cấu hình instance kiểm thử, không dừng service của người khác. B13 cần ghi cả trạng thái HTTP khi kiểm tra quyền, không chỉ nhìn nút UI. Với B05 phân biệt replay cùng request key và hai ý định mua mới; không quy mọi hai request khác key thành đơn trùng.

## Ghi nhận kết quả

Sửa `sample_results/browser_acceptance.json`: điền môi trường và đổi mỗi case thành `pass`, `fail`, `blocked` hoặc giữ `not_run`. Ghi `observed` bằng kết quả thực tế; thêm đường dẫn evidence tương đối với repository. B14/B15 cần ảnh thể hiện từng viewport và phạm vi trang đã xem.

```powershell
python scripts/browser_acceptance.py report sample_results/browser_acceptance.json --output sample_results/browser_acceptance.md
python scripts/browser_acceptance.py report sample_results/browser_acceptance.json --complete
```

Lệnh đầu cho phép báo cáo trung thực cả những mục chưa chạy. Lệnh `--complete` chỉ đạt khi đủ 15 case PASS với evidence và metadata. Nếu có lỗi UI, tạo issue có bước tái hiện/ảnh và bàn giao người đang thiết kế UI; chạy lại case liên quan sau sửa. Không lấy kết quả UI cũ nghiệm thu UI mới.
