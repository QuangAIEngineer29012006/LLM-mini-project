# Quy trình evaluation và phân tích lỗi

Phần này thuộc TV5. Frontend không tham gia vào pipeline đánh giá; evaluation gọi
API backend trên database tạm, vì vậy kết quả không làm thay đổi dữ liệu demo.

## Chạy evaluation

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag.py --split dev
.\.venv\Scripts\python.exe scripts\evaluate_rag.py --split test
```

Có thể chạy chế độ Gemini khi đã cấu hình `GEMINI_API_KEY`:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag.py --split test --provider gemini --embedding gemini --pace 6 --timeout 25 --label final
```

Mỗi lần chạy sinh ba file cùng tiền tố trong `artifacts/`:

- `evaluation_results_*.json`: raw result của từng case và summary metric.
- `*_error_analysis.json`: phân loại tự động các lỗi/near-miss.
- `*_error_analysis.md`: báo cáo đọc được để đưa vào phần error analysis.

Phân loại tự động không sửa expected label và không loại bỏ case fail. Nó chỉ dựa
trên các tín hiệu đã có trong raw result:

- `routing`: route thực tế khác route mong đợi.
- `retrieval`: Hit@3 hoặc Recall@5 chưa đủ.
- `context`: multi-condition chưa phủ đủ evidence chính.
- `grounding`: câu trả lời thiếu evidence span bắt buộc.
- `citation`: citation không resolve được hoặc không thuộc relevance judgment.
- `status_safety`: status khác expected, thường gặp ở no-evidence/access-denied.
- `action_validation`: số lượng order tạo ra không đúng kỳ vọng.

## Metric

- **Hit@3**: có ít nhất một chunk liên quan trong top 3.
- **Recall@5**: tỷ lệ chunk liên quan xuất hiện trong top 5.
- **MRR**: nghịch đảo thứ hạng của chunk liên quan đầu tiên.
- **Evidence coverage**: tỷ lệ evidence chính xuất hiện trong context gửi cho generator.
- **Citation resolve/support**: citation có trỏ được về index/file nguồn và có nằm trong relevance judgment hay không.

Các metric retrieval không tính case có relevance set rỗng; các case đó được đánh
giá bằng no-evidence safe rate và status contract.

## Re-index

```powershell
.\.venv\Scripts\python.exe scripts\reindex_demo.py
```

Script chạy trên DB/index tạm và ghi `artifacts/reindex_evidence.json`. Báo cáo
`artifacts/reindex_report.md` phải thể hiện được:

1. diff nghiệp vụ và chunk bị ảnh hưởng;
2. snapshot index 1.0 và 1.1;
3. verification query trước/sau;
4. cache invalidation;
5. activate và rollback;
6. kiểm tra không rò tài liệu nội bộ và không ghi secret/PII vào audit.

## Cách trình bày error analysis

Không chỉ báo một con số pass/fail. Với mỗi lỗi cần nêu:

1. case và câu hỏi;
2. tầng lỗi (routing, retrieval, context, generation, citation, action hoặc safety);
3. bằng chứng từ raw result;
4. nguyên nhân;
5. thay đổi chỉ thực hiện trên dev;
6. kết quả test held-out sau khi chốt thay đổi.

Claim review thủ công vẫn cần người trong nhóm xác nhận; báo cáo tự động là bằng
chứng hỗ trợ, không thay thế đánh giá nội dung câu trả lời.
