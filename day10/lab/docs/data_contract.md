# Data contract — Lab Day 10

Tài liệu đặc tả hợp đồng dữ liệu giữa các nguồn cấp thông tin chính sách và hệ thống cơ sở tri thức (KB) phục vụ cho CS & IT Helpdesk Agent.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| **policy_refund_v4** | CSV batch export | Lọt cửa sổ hoàn tiền cũ 14 ngày (stale data). | Alert Slack `#incident-alerts` (Halt pipeline) |
| **sla_p1_2026** | CSV batch export | Thiếu quy trình escalate tự động 10 phút. | Alert Slack `#incident-alerts` (Halt pipeline) |
| **it_helpdesk_faq** | CSV batch export | Sai định dạng ngày hiệu lực hoặc thiếu trường. | Alert Slack `#incident-alerts` (Halt pipeline) |
| **hr_leave_policy** | CSV batch export | Lọt bản ghi 10 ngày phép năm cũ năm 2025. | Alert Slack `#incident-alerts` (Halt pipeline) |
| **access_control_sop** | CSV batch export | Doc_id lạ không đăng ký trong data contract. | Alert Slack `#incident-alerts` (Halt pipeline) |

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| **chunk_id** | string | Có | Định danh duy nhất có tính ổn định cao (SHA-256 hash của `doc_id|chunk_text|seq`). |
| **doc_id** | string | Có | Mã tài liệu logic (phải thuộc allowlist: `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy`, `access_control_sop`). |
| **chunk_text** | string | Có | Nội dung văn bản của chunk (độ dài tối thiểu 8 ký tự, đã dọn dẹp các ký tự/tiền tố gây nhiễu). |
| **effective_date** | date | Có | Ngày hiệu lực của chính sách, định dạng chuẩn ISO `YYYY-MM-DD`. |
| **exported_at** | datetime | Có | Thời gian xuất bản ghi, định dạng ISO `YYYY-MM-DDTHH:MM:SS`. |

---

## 3. Quy tắc quarantine vs drop

* **Nguyên tắc không Drop**: Hệ thống **không bao giờ** âm thầm loại bỏ (drop) bất kỳ dòng dữ liệu nào từ file raw. Mọi dòng dữ liệu không đạt yêu cầu đều phải được phân loại và ghi vết.
* **Cách ly (Quarantine)**:
  * Tất cả các dòng bị lỗi cấu trúc (thiếu trường, định dạng ngày không hợp lệ, `doc_id` lạ) hoặc lỗi logic (ngày hiệu lực HR cũ, nội dung phép năm cũ 10 ngày) sẽ được đưa vào tệp `artifacts/quarantine/quarantine_<run_id>.csv`.
  * Mỗi bản ghi bị cách ly sẽ được đính kèm trường `reason` để hỗ trợ kỹ sư dữ liệu chẩn đoán nguyên nhân.
* **Quy trình tái nhập**: Sau khi nguồn cấp dữ liệu thô được sửa đổi (ví dụ cập nhật đúng chính sách hoàn tiền 7 ngày), tệp thô mới sẽ được chạy lại qua pipeline để giải phóng dữ liệu khỏi quarantine.

---

## 4. Phiên bản & canonical

* **Chính sách Hoàn tiền (Refund policy)**: 
  * Source of Truth: `data/docs/policy_refund_v4.txt`.
  * Quy tắc: Cửa sổ hoàn tiền hiện hành phải là **7 ngày làm việc**.
* **Chính sách Nghỉ phép (HR Leave policy)**:
  * Source of Truth: `data/docs/hr_leave_policy.txt` (Chỉ chấp nhận các bản ghi có hiệu lực từ `2026-01-01` trở đi).
  * Quy tắc: Số ngày phép năm tiêu chuẩn cho nhân viên dưới 3 năm kinh nghiệm phải là **12 ngày phép năm**. Các bản ghi nhắc tới "10 ngày phép năm" là stale và bị cấm.
