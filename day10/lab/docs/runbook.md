# Runbook — Lab Day 10 (Incident Response)

Runbook hướng dẫn xử lý khi hệ thống cơ sở tri thức (KB) của CS & IT Helpdesk Agent gặp sự cố dữ liệu cũ (stale) hoặc sai lệch nội dung.

---

## Symptom (Triệu chứng)

* **Phản hồi sai lệch của Agent**: Người dùng cuối hoặc CS Agent nhận được câu trả lời sai từ chatbot, ví dụ: báo chính sách hoàn tiền là "14 ngày" (chính sách cũ) thay vì "7 ngày" (chính sách hiện hành), hoặc báo số ngày phép năm của nhân viên mới là "10 ngày" thay vì "12 ngày".
* **Lỗi truy xuất thông tin**: Các truy vấn liên quan đến quyền quản trị Cấp độ 4 (Level 4 Admin Access) không trả về kết quả hoặc trả về thông tin rỗng do tài liệu `access_control_sop` bị quarantine nhầm hoặc chưa được nhúng.

---

## Detection (Phát hiện)

* **Cảnh báo Freshness SLA**: Pipeline ghi nhận `freshness_check=FAIL` (thời gian xuất file export vượt quá 24 giờ quy định).
* **Pipeline bị Halt**: Lệnh chạy `python etl_pipeline.py run` bị treo/dừng và trả về mã lỗi `2` (PIPELINE_HALT) do vi phạm một trong các expectation halt (ví dụ: `hr_leave_no_stale_10d_annual` phát hiện nội dung 10 ngày phép).
* **Kết quả Eval hits_forbidden**: Tệp `artifacts/eval/after_fix_eval.csv` ghi nhận cột `hits_forbidden=yes` cho các câu hỏi kiểm định.

---

## Diagnosis (Chẩn đoán)

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| **1** | Mở tệp manifest gần nhất `artifacts/manifests/manifest_*.json` | Kiểm tra các chỉ số `cleaned_records` và `quarantine_records` xem có sự sụt giảm/tăng đột biến bất thường không. |
| **2** | Mở tệp cách ly `artifacts/quarantine/quarantine_*.csv` | Lọc theo cột `reason` để tìm nguyên nhân cụ thể (ví dụ: `stale_hr_policy_text` do lọt bản HR cũ, `unknown_doc_id` do chưa đăng ký doc_id mới). |
| **3** | Chạy kiểm định truy xuất: `python eval_retrieval.py` | Xem tệp `after_fix_eval.csv` để định vị chính xác câu hỏi và tài liệu (cột `top1_doc_id`, `top1_chunk_id`) nào bị sai lệch thông tin. |

---

## Mitigation (Xử lý tạm thời)

1. **Khôi phục dữ liệu sạch**: 
   * Sửa đổi file thô `data/raw/policy_export_dirty.csv` để loại bỏ hoặc chuẩn hoá các dòng lỗi.
   * Rerun lại pipeline bằng lệnh: `python etl_pipeline.py run`. Cơ chế idempotent sẽ tự động ghi đè và prune (xoá bỏ) các vector cũ/lỗi khỏi database.
2. **Rollback database**: Nếu không thể sửa file raw ngay lập tức, rollback thư mục `chroma_db/` về snapshot sao lưu gần nhất (backup hằng ngày) và khởi động lại dịch vụ.
3. **Thông báo bảo trì**: Bật cờ cảnh báo trên giao diện chatbot để thông báo cho người dùng rằng dữ liệu tri thức đang được đồng bộ hóa và cập nhật.

---

## Prevention (Phòng ngừa)

* **Tự động hóa Kiểm định**: Thiết lập CI/CD chạy lệnh `python etl_pipeline.py run` hằng ngày trước khi đẩy dữ liệu vào production.
* **Cảnh báo qua Slack**: Tích hợp gửi thông báo trực tiếp tới `#incident-alerts` ngay khi pipeline ghi nhận lỗi halt hoặc warn.
* **Chặt chẽ hóa Data Contract**: Cập nhật file `contracts/data_contract.yaml` định kỳ khi có tài liệu chính sách mới, tránh trường hợp doc_id lạ lọt qua hệ thống.
