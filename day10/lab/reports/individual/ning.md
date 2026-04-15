# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Ning  
**Vai trò:** Cleaning & Quality Owner + Monitoring / Docs Owner  
**Ngày nộp:** 2026-04-15  
**Độ dài yêu cầu:** 400–650 từ

---

## 1. Tôi phụ trách phần nào?

**File / module tôi sở hữu:**
- `transform/cleaning_rules.py` — thêm hàm `_strip_control_chars()` (module level, trước `clean_rows`), và 3 rule mới bên trong `clean_rows()`: Rule A (strip BOM) tại trước bước allowlist check, Rule B (future date quarantine) sau HR stale check, Rule C (whitespace normalize + short chunk quarantine) sau empty text check. Cũng thêm `from datetime import date` vào imports.
- `quality/expectations.py` — thêm E7 (`no_future_effective_date`, halt) và E8 (`no_cleaned_annotation_in_non_refund`, warn) trước dòng `halt = any(...)`. Thêm `from datetime import date`.
- `contracts/data_contract.yaml` — điền `owner_team`, `alert_channel`, thêm 3 quality_rules mới, và 2 fields trong `policy_versioning`.
- `data/raw/policy_export_inject2.csv` — tạo file CSV inject với BOM thật (row 9), future date (row 7), short chunk (row 8) để chứng minh 3 rule mới có tác động đo được.
- Toàn bộ docs: `pipeline_architecture.md`, `data_contract.md`, `runbook.md`, `quality_report.md`.

**Kết nối:** Lab thực hiện solo — tôi đảm nhận toàn bộ pipeline từ code đến documentation.

**Bằng chứng:** Xem `artifacts/manifests/manifest_sprint3-fixed.json` (`run_id=sprint3-fixed`) và `artifacts/quarantine/quarantine_inject-rules-test.csv` (chứng minh Rule B và C hoạt động).

---

## 2. Một quyết định kỹ thuật

**Quyết định: Chọn `halt` cho E7 (`no_future_effective_date`) thay vì `warn`.**

Khi thiết kế E7, tôi có 2 lựa chọn: `warn` (ghi log cảnh báo nhưng vẫn tiếp tục embed) hoặc `halt` (dừng pipeline). Tôi chọn `halt` vì lý do sau:

Một chunk có `effective_date` trong tương lai (ví dụ `2099-12-31`) đại diện cho chính sách **chưa có hiệu lực**. Nếu embed vào vector store, agent RAG có thể trích dẫn chính sách này khi người dùng hỏi — đây là **lỗi correctness** (thông tin sai về hiện thực), không chỉ là vấn đề chất lượng dữ liệu.

So sánh với E8 (`no_cleaned_annotation_in_non_refund`) mà tôi chọn `warn`: annotation `[cleaned:...]` trong doc không phải refund là dấu hiệu regression trong code, nhưng không trực tiếp làm agent trả lời sai — chỉ là data artifact không mong muốn. Do đó `warn` đủ để alert mà không block pipeline.

Nguyên tắc: **halt khi correctness bị vi phạm, warn khi chỉ có data quality issue** không ảnh hưởng trực tiếp tới output của agent.

---

## 3. Một lỗi / anomaly đã xử lý

**Symptom:** Khi chạy pipeline lần đầu, tôi thấy `freshness_check=FAIL` ở tất cả các run, kể cả run sạch `sprint3-fixed`. Tôi nghi ngờ có bug trong `freshness_check.py`.

**Phát hiện:** Mở `artifacts/manifests/manifest_sprint3-fixed.json`, thấy `"latest_exported_at": "2026-04-10T08:00:00"`. Tính toán: ngày chạy là `2026-04-15`, delta = 117 giờ >> SLA 24 giờ.

**Diagnosis:** `latest_exported_at` được đọc từ cột `exported_at` trong CSV. File `policy_export_dirty.csv` có `exported_at=2026-04-10T08:00:00` cố định cho tất cả rows — đây là timestamp tĩnh trong file mẫu lab, không phải timestamp tự sinh khi chạy pipeline.

**Fix:** Không cần sửa code. Đây là hành vi đúng — trong production, `exported_at` được ghi tự động khi export từ database. Tôi document anomaly này trong `docs/runbook.md` (Incident 2) và `docs/quality_report.md` (Section 3) để tránh nhầm lẫn cho người xem sau.

---

## 4. Bằng chứng trước / sau

**run_id inject-bad** (before fix, `artifacts/eval/after_inject_bad.csv`):
```
q_refund_window,contains_expected=yes,hits_forbidden=yes,top1_doc_id=policy_refund_v4
```

**run_id sprint3-fixed** (after fix, `artifacts/eval/after_fixed_eval.csv`):
```
q_refund_window,contains_expected=yes,hits_forbidden=no,top1_doc_id=policy_refund_v4
```

`hits_forbidden` thay đổi từ `yes` → `no` sau khi pipeline chạy đúng với `apply_refund_window_fix=True`. `embed_prune_removed=1` trong log `sprint3-fixed` xác nhận vector stale đã bị xoá khỏi Chroma. Đây là bằng chứng định lượng trực tiếp về tác động của data quality lên retrieval.

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ, tôi sẽ thay thế manual `cleaning_rules.py` bằng **pydantic v2 schema validation**: định nghĩa `class ChunkRow(BaseModel)` với `effective_date: date` (type-safe, tự validate ISO format và tương lai), `chunk_text: constr(min_length=20)`, và `doc_id: Literal[...]`. Điều này giúp bắt lỗi type coercion tại ingest (không phải sau khi clean), và loại bỏ nhiều if-else manual trong `clean_rows()` — code ngắn hơn, dễ test hơn với pytest fixtures.
