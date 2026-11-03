# Kịch bản demo RAG (10–12 phút)

Theo đúng 6 mục ở §10 của đề. Mỗi bước ghi câu cần gõ và điều cần chỉ cho người xem.

## Chuẩn bị

1. `.env`: `LLM_PROVIDER=gemini` và `RAG_EMBEDDING_PROVIDER=gemini` cho demo thật (hoặc cả hai `fake` để chạy offline). Đặt `DEMO_STAFF_KEY`, `DEMO_ADMIN_KEY` bằng chuỗi bất kỳ. Mỗi câu hỏi kiến thức tốn 3 lượt gọi Gemini.
2. Kiểm tra index và metadata cùng release:

```bash
python -m database.shop_db.sku_sync_service --check --manifest data_config/corpus_manifest_v1.1.json
```

3. Chạy backend và frontend như README, mở http://127.0.0.1:5173. `GET /api/health` phải có `"rag_ready": true`.

## 1. Khách xem catalog rồi hỏi sản phẩm/chính sách có citation (2 phút)

- Mở trang Cửa hàng, bấm Balo laptop để thấy giá/tồn từ DB.
- Mở chat, gõ: **“Balo laptop bảo hành bao lâu?”**
- Chỉ: nhãn **Tra cứu tài liệu**, trạng thái **Có trích dẫn nguồn**, citation `DOC-POL-WARRANTY · v1.0`.
- Bấm citation để mở đúng đoạn tài liệu gốc, bấm **Xem BAG-GRY-15**: modal sản phẩm mở với biến thể đã chọn, **Thêm vào giỏ** đi qua API giỏ hàng cũ. Đây là luồng nối kiến thức với sản phẩm.

## 2. Câu hỏi nhiều điều kiện (1,5 phút)

- Gõ: **“Nón lưỡi trai đổi ý có đổi được không, còn nếu bị lỗi khóa thì sao?”**
- Chỉ: câu trả lời giữ cả ngoại lệ (không đổi do đổi ý) lẫn điều kiện còn lại (vẫn đổi lỗi nhà sản xuất), trích đoạn “Ngoại lệ nón lưỡi trai” của `DOC-POL-RETURN · v1.1`.

## 3. Đặt hàng vẫn dùng database, tồn kho, validation cũ (1,5 phút)

- Gõ: **“Đặt cho tôi balo laptop xám, 15inch”**: bot khớp `BAG-GRY-15`, giá 520.000₫, còn 4, hỏi số lượng và giao nhận, **không** tự điền số lượng.
- Điền form trong chat: đơn nháp `pending_confirmation`, tổng do server tính.

## 4. Câu kết hợp: citation + action có kiểm soát (2 phút)

- Gõ: **“Balo laptop bảo hành bao lâu, chốt 1 BAG-GRY-15, Tên Khách Demo, SĐT 0912345678, giao về 12 Đường Mẫu, Phường Mẫu, Quận 7”**
- Chỉ: nhãn **Tài liệu + đơn hàng**; phần bảo hành có citation; phần đặt hàng tạo đơn vì SKU, số lượng, giao nhận đều rõ.
- Đối chứng: **“Mẫu này có đổi trả không, thêm hai áo size M vào đơn nháp”**: có citation cho phần đổi trả, nhưng **không tạo đơn** vì chưa rõ sản phẩm/SKU; bot hỏi lại.

## 5. No-evidence và access-denied (1,5 phút)

- **“Cửa hàng có hỗ trợ trả góp không?”** → **Chưa đủ bằng chứng**, không citation, không tự suy ra “có” hay “không”.
- **“Hạn mức hỗ trợ phí vận chuyển nội bộ là bao nhiêu?”** (khách) → **Không có quyền truy cập**, không citation. Khách không được biết shop sẵn sàng bù phí ship đến mức nào.
- Footer → **Nhân viên / Quản trị** → mở phiên **staff** bằng khóa demo → hỏi lại cùng câu: nhân viên cấp 1 được tự duyệt hỗ trợ phí gửi trả tối đa 30.000 VND/đơn, có citation `DOC-INT-PROMO-RULES`. Cùng câu hỏi, kết quả khác nhau theo role.
- Dự phòng (tài liệu mức admin): **“Phụ cấp ca trực tối muộn của nhân viên là bao nhiêu?”** — khách và staff bị từ chối, admin nhận 150.000 VND/ca (`DOC-ADM-HR-POLICY`). Tài liệu ghi “ca trực kỹ thuật tối muộn”, không có chữ “ca đêm”, nên đừng hỏi “ca đêm”.

## 6. Metric, error trace, re-index (2,5 phút)

- Trang admin, hỏi một câu: bảng **Retrieval** hiện rank, điểm (ghi rõ không phải độ chắc chắn), mức quyền, chunk nào vào context.
- Mở [artifacts/evaluation_report.md](artifacts/evaluation_report.md): bảng metric, một lỗi tiêu biểu (P02 “không thích màu”: embedding fake không tìm ra đoạn đổi ý nên Gemini từ chối; Gemini embedding tìm ra ở rank 1 và trả lời đúng 14 ngày), cải tiến có kiểm soát trên dev, và mục 3d so sánh trước/sau khi ghép retrieval của TV2.
- Re-index trên trang admin: hỏi khách **“Đổi size hoặc màu do đổi ý được hỗ trợ trong bao lâu?”** → 14 ngày (`v1.1`). Admin bấm **Activate 1.0.0** → hỏi lại → 7 ngày (`v1.0`), cache đã bị xóa. Bấm **Activate 1.1.0** để trả về. Chi tiết: [artifacts/reindex_report.md](artifacts/reindex_report.md).

## Hỏi đáp dự phòng

- *Vì sao không lộ tài liệu nội bộ dù chỉ ẩn ở cuối?* Customer không nạp vector của tài liệu nội bộ; không có candidate nào để rò (test `test_customer_candidates_never_contain_internal_chunks`).
- *RAG có tạo đơn được không?* Không. Kết quả RAG chỉ là text + citation; action đi qua luồng đặt hàng với đầy đủ validation.
- *Index lệch DB thì sao?* Service chuyển `degraded`, route kiến thức trả `error` và không trích dẫn.
