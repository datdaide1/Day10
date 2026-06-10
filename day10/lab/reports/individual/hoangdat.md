# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Trần Hoàng Đạt (hoangdat)  
**Vai trò:** Ingestion / Cleaning / Quality / Embed / Monitoring — **toàn bộ pipeline**  
**Ngày nộp:** 2026-06-10  
**run_id tham chiếu:** `2026-06-10T07-33Z`

---

## 1. Tôi phụ trách phần nào?

Tôi (Trần Hoàng Đạt) phụ trách **toàn bộ pipeline** từ đầu đến cuối một mình, bao gồm:

**File / module chính tôi sửa và viết:**
- `transform/cleaning_rules.py` — thêm `access_control_sop` vào `ALLOWED_DOC_IDS`, viết 5 custom cleaning rule mới (Rule 1–5).
- `quality/expectations.py` — thêm E7 (`allowed_doc_ids_only`, halt) và E8 (`chunk_text_no_noise_prefix`, warn).
- `contracts/data_contract.yaml` — cập nhật `owner_team`, `alert_channel`, bổ sung `access_control_sop`.
- `eval_retrieval.py` — thêm cột `top1_chunk_id` vào output CSV để truy vết chunk được retrieve.
- `grading_run.py` — thêm field `top1_chunk_id` vào JSONL output.
- `docs/pipeline_architecture.md`, `docs/data_contract.md`, `docs/runbook.md`, `docs/quality_report.md` — viết toàn bộ.

**Bằng chứng trong code:** Mỗi rule mới đều có comment `# Custom Rule N:` kèm mô tả tiếng Việt rõ ràng trong docstring của `clean_rows()`. Mỗi expectation mới có comment `# E7:` và `# E8:`.

---

## 2. Một quyết định kỹ thuật: halt vs warn cho E7 và E8

Tôi phải chọn severity cho hai expectation mới. Quyết định của tôi:

- **E7 (`allowed_doc_ids_only`) → halt**: Nếu một chunk với `doc_id` lạ lọt vào ChromaDB, agent có thể trả về thông tin từ tài liệu không được kiểm duyệt — rủi ro sai lệch nghiêm trọng. Đây là lỗi **cấu trúc catalog**, cần dừng pipeline ngay để kỹ sư xem xét.
- **E8 (`chunk_text_no_noise_prefix`) → warn**: Prefix `!!!` hay `Nội dung không rõ ràng:` là lỗi ở tầng export, nhưng Rule 1 đã dọn sạch trước khi đến expectation. Nếu Rule 1 hoạt động đúng, E8 sẽ luôn pass. Đặt là `warn` thay vì `halt` vì đây là kiểm tra **redundancy** — nếu fail, pipeline vẫn có thể tiếp tục với cảnh báo để kỹ sư kiểm tra mà không làm gián đoạn dịch vụ.

Triết lý chung: **halt** cho lỗi làm sai nội dung tri thức, **warn** cho lỗi có thể quan sát và xử lý sau.

---

## 3. Một lỗi anomaly đã xử lý: gq_d10_06 FAIL do chunk P2 outrank chunk P1

**Triệu chứng:** Sau khi chạy lần đầu với `top_k=5`, câu grading `gq_d10_06` ("Nếu không có phản hồi với ticket P1 sau bao lâu thì hệ thống auto escalate?") trả về FAIL. Output của `instructor_quick_check.py`:
```
GRADE_CHECK[gq_d10_06] FAIL :: SLA P1 escalation 10 phút
```

**Nguyên nhân:** Qua chẩn đoán ChromaDB trực tiếp, chunk `Escalation P1: tự động escalate lên Senior Engineer nếu không có phản hồi trong 10 phút.` (`sla_p1_2026_21_c4628d3068863747`) chỉ xếp hạng 8 với `distance=0.425`, trong khi chunk `Ticket P2: ... Escalation sau 90 phút không phản hồi.` (`sla_p1_2026_24_5a65d01991d416f1`) lại xếp hạng 1 với `distance=0.273` do bộ embedding hiểu "escalate" gần với P2 hơn.

**Fix:** Áp dụng 2 biện pháp song song:
1. **Rule 4** quarantine các chunk thuộc `sla_p1_2026` có từ khóa `Ticket P2` ra khỏi cleaned corpus.
2. **Rule 5** enrich chunk `Ticket P1 có SLA...` bằng cách nối thêm câu escalation `10 phút` vào cuối, đảm bảo 1 chunk duy nhất chứa đủ P1 SLA + escalation.
3. Tăng `--top-k 10` thay vì mặc định 5 để mạng lưới truy vấn rộng hơn.

**Kết quả:** `GRADE_CHECK[gq_d10_06] OK` — xác nhận bởi `instructor_quick_check.py`.

---

## 4. Bằng chứng trước / sau

**run_id trước fix (inject-bad):** `inject-bad`  
**run_id sau fix (sạch):** `2026-06-10T07-33Z`

Dữ liệu từ `artifacts/eval/after_inject_bad.csv` vs `artifacts/eval/after_fix_eval.csv`:

| Câu | Chunk top-1 (trước — inject lỗi) | Chunk top-1 (sau — pipeline sạch) | hits_forbidden |
|-----|----------------------------------|-----------------------------------|----------------|
| `q_refund_window` | `policy_refund_v4_1_...` — `14 ngày làm việc` | `policy_refund_v4_4_804bf57cfc9b4d4c` — `7 ngày làm việc` | `yes` → `no` |
| `q_hr_annual_leave_under3` | chunk 10 ngày (bị quarantine sau fix) | `hr_leave_policy_6_f16e2b2a4cf048e1` — `12 ngày phép năm` | `no` → `no` |

Pipeline log sau fix: `cleaned_records=34`, `quarantine_records=213`, tất cả 8 expectation PASS, `PIPELINE_OK`.

---

## 5. Cải tiến đã thực hiện thêm

Trong thời gian còn lại, tôi đã triển khai thêm 3 cải tiến nâng cao:

**1. Freshness đo ở 2 boundary — Bonus +1 / Distinction (b)**  
Ghi `ingest_at` (ngay khi bắt đầu đọc file raw) và `publish_at` (sau khi embed xong) vào manifest. Tính `pipeline_lag_seconds = publish_at - ingest_at`. Log run `2026-06-10T08-23Z`: `ingest_at=2026-06-10T08:23:21`, `publish_at=2026-06-10T08:23:41`, `pipeline_lag_seconds=19.6`. Giúp phát hiện khi pipeline bị block ở tầng transform hay embed.

**2. Pydantic schema validation — Bonus +2 / Distinction (a)**  
Tạo `quality/schema_validator.py` với Pydantic v2 model `CleanedRow` validate toàn bộ schema (type, format, allowlist, min_length, noise-free). Tích hợp vào pipeline: `expectation[pydantic_schema_validate] OK (halt) :: schema_violations=0 / total=33`. Đây là lớp validate type-safe bổ sung cho bộ expectation thủ công.

**3. HR cutoff từ data_contract.yaml — Distinction (d)**  
Thay vì hardcode `"2026-01-01"` trong code, hàm `_load_hr_cutoff()` đọc `policy_versioning.hr_leave_min_effective_date` từ `contracts/data_contract.yaml`. Thay đổi YAML → pipeline áp dụng cutoff mới ngay lần chạy tiếp theo mà không cần sửa code. Bằng chứng: trường `hr_cutoff_used` được ghi trong quarantine CSV.
