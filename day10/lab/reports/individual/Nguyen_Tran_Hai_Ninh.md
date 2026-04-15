# Báo Cáo Cá Nhân — Lab Day 10: Sprint 1–2 (Ingest & Clean & Quality & Embed)

**Họ và tên:** Nguyễn Trần Hải Ninh  
**Vai trò:** Ingestion & Cleaning & Quality Owner  
**Ngày nộp:** 2026-04-15  
**Độ dài yêu cầu:** 400–650 từ

---

## 1. Tôi phụ trách phần nào?

**File / module :**
- `transform/cleaning_rules.py` — toàn bộ (baseline 6 rules + thêm 3 rule mới: strip BOM/control chars, future date quarantine, min length 20)
- `quality/expectations.py` — toàn bộ (baseline 6 expectations + thêm E7, E8)
- `etl_pipeline.py::cmd_run()` — ingest, clean, validate, embed,... 
- `etl_pipeline.py::cmd_embed_internal()` — Chroma upsert + prune vector cũ logic
- `data/raw/policy_export_dirty.csv` — input CSV mẫu (10 rows với 6 lỗi cố ý)
- `contracts/data_contract.yaml` — điền schema, quality_rules,... 
**Kết nối với thành viên khác:**
- Tôi cung cấp: cleaned CSV, quarantine CSV, manifest, expectation results, Chroma collection đã embed
- Phong dùng để: test eval retrieval, injection dataset, freshness check
- Feedback loop: nếu Phong phát hiện eval fail → báo lại để kiểm tra rule/expectation cần điều chỉnh

**Bằng chứng thực tế:**
- `artifacts/logs/run_sprint3-fixed.log` — ghi `raw_records`, `cleaned_records`, `quarantine_records`, `run_id`
- `artifacts/cleaned/cleaned_sprint3-fixed.csv` — output sạch (6 rows)
- `artifacts/quarantine/quarantine_sprint3-fixed.csv` — output quarantine (4 rows) với `reason` field
- `artifacts/manifests/manifest_sprint3-fixed.json` — manifest đầy đủ metadata
- `metrics_impact` table trong group report — chứng minh 3 rule mới có tác động đo được

---

## 2. Một quyết định kỹ thuật

**Quyết định: Chọn `halt` cho E7 (`no_future_effective_date`) thay vì `warn`.**

Khi thiết kế E7, tôi có 2 lựa chọn: `warn` (ghi log cảnh báo nhưng vẫn tiếp tục embed) hoặc `halt` (dừng pipeline). Tôi chọn `halt` vì lý do sau:

Một chunk có `effective_date` trong tương lai (ví dụ `2099-12-31`) đại diện cho chính sách **chưa có hiệu lực**. Nếu embed vào vector store, agent RAG có thể trích dẫn chính sách này khi người dùng hỏi — đây là **lỗi correctness** (thông tin sai về hiện thực), không chỉ là vấn đề chất lượng dữ liệu.

So sánh với E8 (`no_cleaned_annotation_in_non_refund`) mà tôi chọn `warn`: annotation `[cleaned:...]` trong doc không phải refund là dấu hiệu regression trong code, nhưng không trực tiếp làm agent trả lời sai — chỉ là data artifact không mong muốn. Do đó `warn` đủ để alert mà không block pipeline.

Nguyên tắc: **halt khi correctness bị vi phạm, warn khi chỉ có data quality issue** không ảnh hưởng trực tiếp tới output của agent.

---

## 3. Một lỗi / anomaly đã xử lý

**Symptom:** Khi chạy pipeline lần đầu, em thấy `freshness_check=FAIL` ở tất cả các run. Em nghi ngờ có bug trong `freshness_check.py`.

**Phát hiện:** Mở `artifacts/manifests/manifest_sprint3-fixed.json`, thấy `"latest_exported_at": "2026-04-10T08:00:00"`. Tính toán: ngày chạy là `2026-04-15`, delta = 117 giờ >> SLA 24 giờ.

**Diagnosis:** `latest_exported_at` được đọc từ cột `exported_at` trong CSV. File `policy_export_dirty.csv` có `exported_at=2026-04-10T08:00:00` cố định cho tất cả rows — đây là timestamp tĩnh trong file mẫu lab, không phải timestamp tự sinh.

**Fix:** Không phải bug. Đây là hành vi đúng — CSV mẫu có dữ liệu cũ. Trong production, `exported_at` được ghi tự động. Em document anomaly này và Người B sẽ ghi trong runbook chi tiết.

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
