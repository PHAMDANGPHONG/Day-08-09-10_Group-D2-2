# Runbook — Lab Day 10 Data Pipeline

> Ba kịch bản incident phổ biến, đủ 5 mục mỗi incident. Peer review cuối tài liệu.

---

## Incident 1: Agent trả lời sai cửa sổ hoàn tiền (“14 ngày” thay vì “7 ngày”)

### Symptom
Agent trả lời câu hỏi “Khách hàng có bao nhiêu ngày để yêu cầu hoàn tiền?” bằng “14 ngày làm việc” thay vì “7 ngày làm việc”. Người dùng phản ánh thông tin lỗi thời.

### Detection
- Log pipeline: `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1`
- Eval: `q_refund_window | hits_forbidden: yes` trong `artifacts/eval/after_inject_bad.csv`
- Alert kênh `#data-alerts-day10` nếu expectation halt được hook vào notification

### Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Mở `artifacts/manifests/manifest_<run_id>.json`, kiểm tra `”no_refund_fix”` | Nếu `true` → pipeline chạy với `--no-refund-fix`; đó là nguyên nhân |
| 2 | Mở `artifacts/cleaned/cleaned_<run_id>.csv`, tìm row `doc_id=policy_refund_v4` chứa “14 ngày” | Nếu tồn tại → chunk stale đã lọt qua clean |
| 3 | Chạy `python eval_retrieval.py --out artifacts/eval/debug_eval.csv` | `q_refund_window.hits_forbidden` phải `yes` để xác nhận |

### Mitigation
```bash
# Chạy lại pipeline không có --no-refund-fix
python etl_pipeline.py run --run-id hotfix-2026-04-15

# Xác nhận prune đã xoá vector stale
grep “embed_prune_removed” artifacts/logs/run_hotfix-2026-04-15.log

# Xác nhận eval sạch
python eval_retrieval.py --out artifacts/eval/hotfix_eval.csv
```
`embed_prune_removed > 0` xác nhận vector cũ đã bị xoá khỏi Chroma.

### Prevention
- Expectation E3 (`refund_no_stale_14d_window`, halt) đã ngăn deploy nếu không có `--skip-validate`.
- Không dùng `--no-refund-fix` trong production. Flag chỉ dùng cho demo Sprint 3.
- Thêm E8 (`no_cleaned_annotation_in_non_refund`, warn) để phát hiện regression nếu refund-fix regex vô tình match sang doc khác.

---

## Incident 2: Freshness FAIL liên tục

### Symptom
Log pipeline luôn kết thúc bằng `freshness_check=FAIL {“reason”: “freshness_sla_exceeded”}`. Gây alert giả trên `#data-alerts-day10`.

### Detection
- Dòng cuối log: `freshness_check=FAIL`
- `age_hours > sla_hours=24.0` trong JSON manifest

### Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Mở manifest: kiểm tra `”latest_exported_at”` | Nếu là `2026-04-10T08:00:00` → timestamp cố định trong CSV mẫu lab |
| 2 | Tính `age_hours = (now - latest_exported_at)` | Nếu > 24 → SLA vi phạm do CSV mẫu quá cũ, không phải lỗi code |
| 3 | Kiểm tra `.env`: `FRESHNESS_SLA_HOURS` | Tăng lên `9999` cho môi trường dev nếu cần |

### Mitigation
Trong lab: **hành vi đúng** — CSV mẫu có `exported_at` cố định 5 ngày trước. Document trong quality report, không cần fix code.

Trong production: cập nhật script export để ghi `exported_at = datetime.now()` vào mỗi row khi chạy pipeline.

### Prevention
- Tăng `FRESHNESS_SLA_HOURS` trong `.env` cho môi trường dev/test.
- Trong production: đảm bảo CSV export được sinh tự động với timestamp hiện tại.
- Thêm `freshness_boundary` thứ hai ở ingest (ghi `ingest_at` vào manifest) để phân biệt “dữ liệu nguồn stale” vs “pipeline chạy chậm”.

---

## Incident 3: Pipeline exit 0 nhưng eval sai (q_leave_version)

### Symptom
Pipeline pass hoàn toàn (exit 0, tất cả expectations OK), nhưng agent trả lời “10 ngày phép năm” thay vì “12 ngày phép năm”.

### Detection
- Eval: `q_leave_version | hits_forbidden: yes` (chứa “10 ngày phép”)
- Expectation E6 (`hr_leave_no_stale_10d_annual`) FAIL trong log

### Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Lọc `artifacts/cleaned/cleaned_<run_id>.csv` theo `doc_id=hr_leave_policy` | Không được có row nào với `effective_date < 2026-01-01` |
| 2 | Kiểm tra `artifacts/quarantine/quarantine_<run_id>.csv` | Row stale HR (date 2025-01-01) phải có trong quarantine với `reason=stale_hr_policy_effective_date` |
| 3 | Chạy `python eval_retrieval.py` | `q_leave_version.hits_forbidden` phải `no` sau khi rebuild |

### Mitigation
```bash
# Rebuild collection sạch
python etl_pipeline.py run --run-id rebuild-$(date +%Y%m%d)
python eval_retrieval.py --out artifacts/eval/rebuild_eval.csv
```

### Prevention
- Expectation E6 (`hr_leave_no_stale_10d_annual`, halt) ngăn deploy nếu chunk cũ lọt vào cleaned.
- Đưa HR cutoff date từ `cleaning_rules.py` (hard-coded `”2026-01-01”`) vào `data_contract.yaml → policy_versioning.hr_leave_min_effective_date` và đọc dynamically.
- Thêm test unit cho `clean_rows()` với fixture row HR date 2025.

---

## Peer Review (3 câu)

1. Trong Incident 1, tại sao `--skip-validate` nguy hiểm trong production? Expectation halt có đủ không nếu không có eval retrieval sau embed?
2. Freshness check hiện đo tại “publish boundary” (sau embed). Nếu muốn phát hiện dữ liệu nguồn stale sớm hơn, nên thêm điểm đo ở đâu trong pipeline và metric nào?
3. Incident 3 chỉ phát hiện qua eval, không qua expectations trong run thông thường. Bạn sẽ thiết kế expectation nào để bắt trường hợp HR stale lọt vào cleaned mà không cần chạy eval riêng?
