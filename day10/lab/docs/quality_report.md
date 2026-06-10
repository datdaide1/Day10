# Quality report — Lab Day 10 (cá nhân)

**run_id:** 2026-06-10T07-33Z  
**Ngày:** 2026-06-10

---

## 1. Tóm tắt số liệu

| Chỉ số | Trước | Sau | Ghi chú |
|--------|-------|-----|---------|
| **raw_records** | 247 | 247 | Tổng số dòng xuất thô từ CSV đầu vào |
| **cleaned_records** | 19 | 34 | Sau khi fix: bổ sung `access_control_sop` và dọn dẹp trùng lặp |
| **quarantine_records** | 228 | 213 | Giảm đi 15 bản ghi của `access_control_sop` được giải phóng khỏi quarantine |
| **Expectation halt?** | Có | Không | Sau khi áp dụng các rule mới, toàn bộ suite validation đều PASS (exit code 0) |

---

## 2. Before / after retrieval (bắt buộc)

> Dẫn link tới các tệp kết quả kiểm định:
> - Tệp kiểm định sạch: [after_fix_eval.csv](file:///E:/VINUNI/Day10/day10/lab/artifacts/eval/after_fix_eval.csv)
> - Tệp kiểm định lỗi: [after_inject_bad.csv](file:///E:/VINUNI/Day10/day10/lab/artifacts/eval/after_inject_bad.csv)

**Câu hỏi then chốt:** refund window (`q_refund_window`)  
* **Trước (Sau khi inject dữ liệu lỗi):**
  * Top-1 Chunk ID: `policy_refund_v4_1_1b5aed46623236f6`
  * Preview: `Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày làm việc kể từ xác nhận đơn.`
  * `contains_expected`: `yes` | `hits_forbidden`: `yes` (Lỗi nghiêm trọng, chứa chính sách hoàn tiền 14 ngày đã hết hiệu lực).
* **Sau (Khi chạy pipeline sạch có dọn dẹp):**
  * Top-1 Chunk ID: `policy_refund_v4_4_804bf57cfc9b4d4c`
  * Preview: `Yêu cầu được gửi trong vòng 7 ngày làm việc kể từ thời điểm xác nhận đơn hàng.`
  * `contains_expected`: `yes` | `hits_forbidden`: `no` (Hoàn hảo, trả về đúng chính sách 7 ngày làm việc).

**Chính sách HR Leave:** versioning HR — `q_hr_annual_leave_under3` (nhân viên < 3 năm kinh nghiệm)
* **Trước (Dữ liệu chưa dọn dẹp chứa bản HR 2025 cũ):**
  * Top-1 Chunk ID: `hr_leave_policy_X` chứa bản cũ `10 ngày phép năm`.
* **Sau (Khi chạy pipeline có lọc stale HR):**
  * Top-1 Chunk ID: `hr_leave_policy_6_f16e2b2a4cf048e1`
  * Preview: `Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm theo chính sách 2026.`
  * `contains_expected`: `yes` | `hits_forbidden`: `no` (Trả về đúng 12 ngày phép năm của bản HR 2026 mới nhất).

---

## 3. Freshness & monitor

* **Kết quả freshness_check**: `FAIL`
* **Giải thích SLA**: Mặc dù freshness check trả về `FAIL` do tệp dữ liệu kiểm thử được xuất từ lịch sử (`latest_exported_at` là `2026-04-10T00:00:00`), hệ thống vẫn hoàn thành do SLA được cấu hình dạng cảnh báo và không treo pipeline. Trong môi trường production thực tế, SLA 24 giờ là hợp lý để đảm bảo dữ liệu tri thức không bị stale quá một ngày làm việc.

---

## 4. Corruption inject (Sprint 3)

* **Cơ chế mô phỏng lỗi**: Chúng tôi tiến hành chạy pipeline với cờ tắt bộ lọc hoàn tiền và bỏ qua xác thực: `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate`.
* **Kết quả**: Dữ liệu hoàn tiền cũ (14 ngày) được nhúng thành công vào cơ sở dữ liệu ChromaDB. Khi chạy đánh giá truy xuất thông qua `eval_retrieval.py`, câu hỏi `q_refund_window` lập tức báo lỗi đỏ `hits_forbidden=yes`, kiểm chứng bộ kiểm định hoạt động cực kỳ nhạy bén và chính xác.

---

## 5. Hạn chế & việc chưa làm

* Chưa tự động gửi thông báo trực tiếp qua webhook Slack khi phát hiện lỗi halt (chỉ mới in log hệ thống).
* Quy trình prune ID hiện tại cần quét toàn bộ ID bằng RAM, có thể gây quá tải nếu collection ChromaDB phình to tới hàng triệu bản ghi.
