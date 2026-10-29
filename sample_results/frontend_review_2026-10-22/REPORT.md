# Rà soát và chạy lại frontend React — 22/10/2026

Bản nguồn được rà soát: commit `d4a4e310aac7c9b61424df3051be4d0fa0c2d70d`, cùng các sửa lỗi trong working tree của lần rà soát này. Môi trường: macOS 27.0, Node 25.8.1, Python trong `.venv`, Codex in-app browser. Frontend chính đã chạy tại [127.0.0.1:5173](http://127.0.0.1:5173), API tại cổng 8000, provider `gemini`, model `gemini-3.5-flash-lite`.

## Các vấn đề đã sửa

| Vấn đề trong bản nhận bàn giao | Thay đổi |
|---|---|
| Mobile ẩn mục Đơn hàng và input tìm kiếm; biểu tượng tìm kiếm không có đường mở input đáng tin cậy | Hiển thị điều hướng và ô tìm kiếm trên mobile; tìm được tiếng Việt không dấu |
| Nhấn xem đơn từ chat luôn chọn đơn mới nhất | Giữ đúng mã đơn được tham chiếu; cập nhật danh sách từ API |
| StrictMode có thể khởi tạo hai phiên vì hai effect cùng thấy localStorage trống | Dùng một promise tạo phiên và một lượt load đang chạy |
| Token hết hạn khiến UI bị kẹt, chỉ có nút đóng lỗi | Phục hồi phiên lúc tải dữ liệu, báo rõ phiên mới không chứa đơn cũ; không tự phát lại thao tác ghi |
| Nhấp nhanh giỏ hàng/sửa đơn có thể tạo nhiều request cùng lúc và trả trạng thái lệch | Khóa thao tác ghi bằng ref, disable khi đang xử lý; mở khóa cả khi lỗi |
| Nhãn sắp xếp chỉ là trang trí | Select sắp xếp giá tăng/giảm có hành vi thật |
| Form dùng giới hạn địa chỉ 300 trong khi API chỉ nhận 200; lỗi gộp khó xác định trường | Đồng bộ 200 ký tự, lỗi từng trường, aria-invalid/describedby, autocomplete và input điện thoại |
| Modal/chat thiếu semantics và thao tác bàn phím; tin nhắn mới có thể nằm ngoài vùng cuộn | Dialog có nhãn, Escape, vòng Tab trong hộp thoại, khôi phục focus; tự cuộn chat tới tin mới |
| Reload trở về cửa hàng và mất trang đang xem | Điều hướng hash cho cửa hàng/giỏ/giao nhận/đơn hàng; reload đọc lại đơn cùng phiên |
| Chữ nhỏ, nút sửa đơn quá nhỏ và thiếu focus rõ | Tăng chữ cho thông tin mua hàng, tăng kích thước control, focus ring, hỗ trợ reduced motion |
| Số liệu 2.000+ khách, bestseller và cam kết giao/đổi trả không có dữ liệu xác nhận | Bỏ các thông tin này; ảnh từ Unsplash được ghi rõ là ảnh minh họa |
| Dependency Vite 5.4.21/esbuild có cảnh báo npm audit | Cập nhật Vite 7.3.7 và lockfile; npm audit sau cập nhật: 0 vulnerability |

Giữ bố cục và bảng màu của frontend mới; không viết lại backend, schema database hoặc prompt Gemini trong lần này. Thêm các module `api.ts`, `Dialog.tsx` và bộ test React.

## Kết quả kiểm tra

| Kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| Bộ test Python hiện có | 169/169 PASS: 90 application/tooling + 79 database | Chạy mới `.venv/bin/python scripts/test_all.py` trong lần rà soát này |
| React regression | 9/9 PASS | [frontend-tests.txt](frontend-tests.txt), `frontend/src/App.test.tsx` |
| Cài sạch dependency từ lockfile | PASS | [npm-ci.txt](npm-ci.txt) |
| TypeScript + production build | PASS, Vite 7.3.7 | [build.txt](build.txt) |
| npm audit (cả dev dependency) | 0 vulnerability | [npm-audit.json](npm-audit.json) |
| Trình duyệt desktop | Tương tác tại viewport 1366×768 | Đã kiểm tra tương tác và DOM ở 1366×768; ảnh desktop bị công cụ chụp cắt nên không dùng làm bằng chứng đầy đủ |
| Trình duyệt mobile | Tương tác tại viewport 390×844; không tràn ngang ở các trang đã đo | [Sản phẩm](mobile-product.png), [đơn hàng](mobile-orders.png), [chat](mobile-chat.png) |
| Live Gemini qua UI chính | 1 request thật, `check_price` → `price_checked`, không lỗi | [live-smoke.json](live-smoke.json), [ảnh mobile Gemini thật](mobile-live-gemini.png) |

9 regression test mới kiểm tra: StrictMode chỉ tạo một phiên và tìm không dấu; tự phục hồi phiên hết hạn; retry sau lỗi API; khóa biến thể hết hàng/Escape; mở đúng đơn chat khi có đơn mới hơn; tiếp tục sửa sau lần lưu trước; giữ idempotency key khi gửi lại chat sau lỗi mạng; form trống không gửi đơn; không gửi thêm request thêm giỏ khi request trước còn chờ.

## Quan sát trực tiếp trên trình duyệt

Các thao tác ghi dùng API HTTP thật + SQLite tạm + FakeLLM riêng tại 8001/5174, không thêm đơn thử vào DB vận hành:

- Tìm `ao thun`, mở áo thun; Trắng/M hết hàng bị disable; Đen/M thêm được.
- Thêm 2 áo, tăng thành 3: giỏ tính 450.000₫. Nhập SĐT sai bị chặn; form trống hiển thị lỗi cả 3 trường.
- Giao nhận mock hợp lệ tạo `DH000001` ở `pending_confirmation`. Sửa sang `TSH-BLK-L`, số lượng 2: DB và UI xác nhận tổng 300.000₫. Reload vẫn đọc được danh sách đơn cùng phiên.
- Chat đặt 1 nón đen → hỏi giao nhận → xen câu hỏi giá áo thun → bổ sung giao nhận: tạo `DH000002`, `CAP-BLK-F`, số lượng 1, tổng 90.000₫ trong cùng phiên.
- Yêu cầu 99 áo khi tồn 25 bị từ chối. Injection nguyên câu trong đề trả handoff, không thay đổi đơn.
- Mobile có tìm kiếm và Đơn hàng, chọn sản phẩm được; checkout tạo `DH000003`, áo đen/M số lượng 1, tổng 150.000₫. Chat catalog cuộn được, ô nhập/nút gửi nằm trong khung.
- Dừng riêng API thử: UI báo lỗi kèm nút tải lại. Khởi động lại API với cùng DB: tải lại được, giữ danh sách đơn.
- Cho phiên trong DB thử hết hạn rồi reload: UI tạo phiên mới, báo rõ lý do, không hiển thị đơn của phiên trước.

Sau đó đã dừng cả hai service thử. Backend chính được restart và React chính chạy tại 5173. Câu hỏi live `Áo thun đen size M giá bao nhiêu?` trả giá 150.000 VND, tồn 25; audit xác nhận `interpretation_source=gemini`, `model_id=gemini-3.5-flash-lite`, route `price_checked`, không lỗi, latency khoảng 6 giây. Console của lượt UI chính không ghi error/warn.

SHA-256 nội dung products/product_variants/inventory/product_aliases của DB vận hành trước/sau giữ nguyên: `357a1ce32d5672a3e8256053861fbbd6d96288cc74766f74e83e91a7793c64e2`. Không tạo đơn mua thử ở DB vận hành; lượt live chỉ hỏi giá. Token/key không ghi vào artifact.

## Giới hạn

Đây là rà soát frontend và kiểm tra các luồng đã mô tả, không tuyên bố đủ toàn bộ 15 kịch bản nghiệm thu trình duyệt. Ảnh desktop do công cụ chụp bị cắt; không coi đó là nghiệm thu hình ảnh đầy đủ desktop. Chưa kiểm tra lại Windows/Safari, bàn phím ảo trên thiết bị thật hoặc cửa sổ ẩn danh; quyền giữa các phiên được kiểm tra ở bộ API hiện có. Vẫn cần ảnh sản phẩm thật và chính sách vận chuyển chính thức trước khi dùng như cửa hàng bán hàng thật. Ảnh và font còn phụ thuộc mạng ngoài.

Bộ 29 case Gemini ngày 21/10 được giữ nguyên, không chạy lại toàn bộ trong lần này. Các thao tác đặt/sửa đơn bằng FakeLLM không dùng làm điểm Gemini. Lịch sử chat hiển thị vẫn nằm trong bộ nhớ trang và mất khi reload; phiên và đơn đọc lại từ API. Các chức năng đăng nhập/khôi phục đơn sau khi phiên hết hạn chưa có trong MVP.
