# Data contract — Lab Day 10

> File YAML: `contracts/data_contract.yaml` — đây là bản mở rộng dạng prose.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|--------------------|----------------|
| `data/raw/policy_export_dirty.csv` | `load_raw_csv()` trong `cleaning_rules.py` — đọc bằng `csv.DictReader`, strip whitespace | Unknown `doc_id` (legacy export), ngày sai format DD/MM/YYYY, chunk_text rỗng, BOM trong doc_id, duplicate text | `quarantine_records` trong log; E3/E5/E7 expectations halt; `#data-alerts-day10` |
| `data/docs/*.txt` (5 file policy) | Đọc trực tiếp trong Day 08/09 RAG pipeline | Version mismatch giữa canonical text và CSV export (vd: refund 7 ngày trong txt vs 14 ngày trong CSV từ bản cũ) | `refund_no_stale_14d_window` expectation (E3); `hits_forbidden=yes` trong eval |

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| `chunk_id` | string | Có | SHA-256 hash prefix của `doc_id\|chunk_text\|seq` — ổn định, idempotent. Format: `{doc_id}_{seq}_{hash16}` |
| `doc_id` | string | Có | Phải thuộc `ALLOWED_DOC_IDS` (xem contract.yaml). BOM/control chars được strip trước khi kiểm tra (Rule A) |
| `chunk_text` | string | Có | Tối thiểu 20 ký tự sau khi normalize whitespace (Rule C). Không được chứa `[cleaned:...]` ngoại trừ `policy_refund_v4` |
| `effective_date` | date (ISO) | Có | Format `YYYY-MM-DD`. Chuẩn hoá từ `DD/MM/YYYY` hoặc ISO sẵn. Phải ≤ ngày hiện tại (Rule B) và ≥ `2026-01-01` với `hr_leave_policy` |
| `exported_at` | datetime (ISO) | Có | Dùng để tính freshness. Phải là ISO 8601. Nếu rỗng, freshness check trả về WARN |

---

## 3. Quy tắc quarantine vs drop

**Records bị quarantine** (không xoá hẳn) được ghi vào `artifacts/quarantine/quarantine_<run_id>.csv` với trường `reason`. Các lý do quarantine hiện tại:

| Reason | Mô tả | Rule |
|--------|-------|------|
| `unknown_doc_id` | `doc_id` không thuộc allowlist (sau khi đã strip BOM) | Baseline |
| `missing_effective_date` | `effective_date` rỗng | Baseline |
| `invalid_effective_date_format` | Không parse được sang ISO | Baseline |
| `stale_hr_policy_effective_date` | `hr_leave_policy` có date < 2026-01-01 | Baseline |
| `missing_chunk_text` | `chunk_text` rỗng sau strip | Baseline |
| `duplicate_chunk_text` | Text trùng với record trước (normalized) | Baseline |
| `future_effective_date` | `effective_date` > ngày hiện tại | Rule B (mới) |
| `chunk_too_short_N_chars` | `chunk_text` < 20 ký tự sau normalize | Rule C (mới) |

**Quy trình xử lý quarantine:**
- Records được lưu, không bị xoá vĩnh viễn.
- `owner_team` (`data-platform-team`) review file quarantine sau mỗi run.
- Để re-ingest: sửa nguồn gốc (CSV hoặc canonical doc) và chạy lại pipeline với `run_id` mới.
- Không có merge tự động — phải có sự chấp thuận của con người.

---

## 4. Phiên bản & canonical

**Source of truth cho refund policy:**
- File: `data/docs/policy_refund_v4.txt`
- Effective date: `2026-02-01`
- Nội dung đúng: **7 ngày làm việc**
- Mọi chunk trong export chứa "14 ngày làm việc" là artifact từ `policy_refund_v3` (bản cũ, migration lỗi) → bị fix bởi `apply_refund_window_fix=True` và kết quả bị gắn tag `[cleaned: stale_refund_window]`.

**Source of truth cho HR leave policy:**
- File: `data/docs/hr_leave_policy.txt`
- Cutoff: `effective_date >= 2026-01-01`
- Nội dung đúng: **12 ngày phép năm**
- Bản cũ 2025 (10 ngày) bị quarantine bởi rule `stale_hr_policy_effective_date`.
