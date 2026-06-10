# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** Cá nhân (Trần Hoàng Đạt)  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| Trần Hoàng Đạt (hoangdat) | Ingestion / Raw Owner | hoangdat@vinuni.edu.vn |
| Trần Hoàng Đạt (hoangdat) | Cleaning & Quality Owner | hoangdat@vinuni.edu.vn |
| Trần Hoàng Đạt (hoangdat) | Embed & Idempotency Owner | hoangdat@vinuni.edu.vn |
| Trần Hoàng Đạt (hoangdat) | Monitoring / Docs Owner | hoangdat@vinuni.edu.vn |

**Ngày nộp:** 2026-06-10  
**Repo:** E:\VINUNI\Day10\day10\lab  
**Độ dài:** ~850 từ

---

## 1. Pipeline tổng quan

**Nguồn raw:** Tệp CSV `data/raw/policy_export_dirty.csv` gồm 247 dòng xuất từ 5 hệ thống nguồn (`policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy`, `access_control_sop`). Dữ liệu thô có nhiều lỗi cố tình: tiền tố gây nhiễu `!!!`, cụm từ lặp lại, ngày hiệu lực sai định dạng, bản ghi HR cũ (10 ngày phép năm 2025) và bản ghi `access_control_sop` bị coi là doc_id lạ do chưa được đưa vào allowlist.

**Luồng end-to-end:** `ingest (load_raw_csv)` → `clean (clean_rows)` → `validate (run_expectations)` → `embed (Chroma upsert + prune)` → `manifest + freshness check`.

**Lệnh chạy một dòng:**
```bash
python etl_pipeline.py run
```

**run_id** được tạo tự động theo timestamp UTC, ví dụ `2026-06-10T07-33Z`, và in ra đầu log cũng như ghi vào `artifacts/manifests/manifest_<run_id>.json`.

---

## 2. Cleaning & Expectation

Pipeline được mở rộng với **5 cleaning rule mới** và **2 expectation mới** so với baseline.

### 2a. Bảng metric_impact (bắt buộc)

| Rule / Expectation mới (tên ngắn) | Trước (số liệu) | Sau khi áp dụng | Chứng cứ |
|-----------------------------------|-----------------|-----------------|---------|
| **Rule 1: trim_noise_prefix** (xóa `!!!` và `Nội dung không rõ ràng:`) | Nhiều chunk bị prefix bẩn, không thể dùng để embed | 0 chunk noise sau clean (`chunk_text_no_noise_prefix OK`) | `expectation[chunk_text_no_noise_prefix] OK (warn)` |
| **Rule 2: dedup_repeated_phrase** (gộp cụm `làm việc làm việc`) | Chunk bị lặp từ gây sai ngữ nghĩa | 0 vi phạm, nội dung rõ ràng hơn | Xem `artifacts/cleaned/cleaned_*.csv` |
| **Rule 3: stale_hr_policy_text** (quarantine 10 ngày phép) | `q_hr_annual_leave_under3` → `hits_forbidden=yes` (stale 10 ngày lọt) | `contains_expected=yes`, `hits_forbidden=no` (12 ngày đúng) | `grading_run.jsonl` → `gq_d10_09` OK |
| **Rule 4: non_p1_sla_scope** (quarantine chunk P2 khỏi sla_p1_2026) | Chunk P2 lọt vào top-k khiến `gq_d10_06` FAIL | `gq_d10_06` OK — `Escalation P1: 10 phút` | `instructor_quick_check.py` gq_d10_06 OK |
| **Rule 5: enrich_p1_sla_chunk** (gắn thông tin escalation vào chunk P1) | Top-1 cho `q_p1_escalation` không chứa `10 phút` | Top-1 chunk P1 chứa đầy đủ SLA + escalation | `grading_run.jsonl` `gq_d10_06` OK |
| **E7: allowed_doc_ids_only** (halt) | `access_control_sop` bị quarantine `unknown_doc_id` (15 chunk mất) | 0 doc_id lạ sau khi thêm vào allowlist | `expectation[allowed_doc_ids_only] OK (halt)` |
| **E8: chunk_text_no_noise_prefix** (warn) | Chunk bẩn lọt vào embed | 0 vi phạm | `expectation[chunk_text_no_noise_prefix] OK (warn)` |
| **Bonus: pydantic_schema_validate** (halt) | Không có Pydantic validate — lỗi schema có thể lọt vào Chroma | `schema_violations=0 / total=33` — 100% hợp lệ | `expectation[pydantic_schema_validate] OK (halt)` trong log |
| **Bonus: Distinction (d) — HR cutoff từ contract** | `hr_leave_min_effective_date` hardcode `"2026-01-01"` trong code | Đọc từ `contracts/data_contract.yaml` — thay đổi YAML → quyết định clean thay đổi | `hr_cutoff_used` ghi trong quarantine CSV |

**Rule chính (baseline đã có + mở rộng):**
- Allowlist doc_id, chuẩn hoá `effective_date` ISO, quarantine HR stale theo ngày hiệu lực, dedup chunk_text, fix refund window 14→7 ngày.
- **Rule mới thêm:** 5 rule custom như bảng trên.

**Ví dụ expectation FAIL và cách xử lý:**
Khi chạy baseline chưa sửa, `gq_d10_06` trả về FAIL vì chunk `Ticket P2` có độ tương đồng cao hơn chunk P1 escalation. Sau khi áp dụng Rule 4 (quarantine P2 scope) và Rule 5 (enrich P1 chunk), `gq_d10_06` OK. Bằng chứng: output của `instructor_quick_check.py` với `PYTHONIOENCODING=utf-8`.

---

## 3. Before / after ảnh hưởng retrieval

**Kịch bản inject corruption (Sprint 3):**
```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
python eval_retrieval.py --top-k 10 --out artifacts/eval/after_inject_bad.csv
```
Cờ `--no-refund-fix` tắt rule fix refund window, cho phép chunk `14 ngày làm việc` lọt vào ChromaDB. Cờ `--skip-validate` bỏ qua expectation halt để pipeline không dừng lại.

**Kết quả định lượng:**

| Câu hỏi | run sạch (`after_fix_eval.csv`) | run lỗi (`after_inject_bad.csv`) |
|---------|--------------------------------|----------------------------------|
| `q_refund_window` | `contains_expected=yes`, `hits_forbidden=no` | `contains_expected=yes`, `hits_forbidden=yes` ⚠️ |
| `q_hr_annual_leave_under3` | `top1_chunk_id=hr_leave_policy_6_f16e2b2a4cf048e1`, text `12 ngày phép năm` | (không thay đổi vì inject chỉ tắt refund fix) |

Top-1 chunk khi inject lỗi: `policy_refund_v4_1_1b5aed46623236f6` — preview: `Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày làm việc kể từ xác nhận đơn.`  
Sau khi restore pipeline sạch: `policy_refund_v4_4_804bf57cfc9b4d4c` — preview: `Yêu cầu được gửi trong vòng 7 ngày làm việc kể từ thời điểm xác nhận đơn hàng.`

---

## 4. Freshness & monitoring

**SLA được chọn:** 24 giờ (`FRESHNESS_SLA_HOURS=24`), đo tại thời điểm `publish` (sau khi embed xong).

**Kết quả trên data mẫu:** `freshness_check=FAIL` vì tệp CSV mẫu có `exported_at` là `2026-04-10`, tức hơn 1471 giờ so với thời điểm chạy — vượt SLA. Đây là **hành vi đúng** đối với data mẫu cũ trong lab (theo FAQ SCORING.md). Trong môi trường production, SLA 24 giờ đảm bảo KB không bị stale quá 1 ngày làm việc. Manifest ghi `latest_exported_at`, `age_hours`, `sla_hours` và `reason` để hỗ trợ audit.

---

## 5. Liên hệ Day 09

Pipeline Day 10 cung cấp corpus sạch (`day10_kb` trong ChromaDB) trực tiếp cho Multi-Agent RAG System của Day 09. Thay vì agent trỏ vào file text thô, Semantic Worker Agent ở Day 09 query vào collection `day10_kb` để lấy các chunk đã được dọn sạch, loại bỏ stale policy. Điều này đảm bảo agent luôn trả lời đúng chính sách hiện hành (ví dụ hoàn tiền 7 ngày, phép năm 12 ngày).

---

## 6. Rủi ro còn lại & việc chưa làm

- `freshness_check=FAIL` trên data mẫu là hành vi được chấp nhận theo thiết kế; production cần cập nhật `exported_at` thật.
- Chưa tích hợp webhook Slack thật khi halt — hiện chỉ log ra console.
- Prune ID trong ChromaDB hiện quét toàn bộ bằng RAM; cần batch nếu collection > 100k chunks.
