# Báo Cáo Cá Nhân — Lab Day 10: Sprint 3–4 (Eval & Monitoring & Docs)

**Họ và tên:** Phạm Đăng Phong  
**Vai trò:** Eval & Monitoring & Docs Owner  
**Ngày nộp:** 2026-04-15  
**Độ dài yêu cầu:** 400–650 từ

---

## 1. Tôi phụ trách phần nào?

**File / module :**
- `eval_retrieval.py` — chạy retrieval trên Chroma collection sau khi Người A embed xong; xuất CSV với `contains_expected`, `hits_forbidden`, `top1_doc_expected`
- `monitoring/freshness_check.py` — đọc manifest, kiểm tra SLA freshness theo giờ
- `docs/pipeline_architecture.md` — sơ đồ luồng mermaid, ranh giới trách nhiệm, idempotency strategy
- `docs/data_contract.md` — điền freshness SLA, alert_channel, canonical_sources
- `docs/runbook.md` — 3 incident scenarios (refund stale, freshness FAIL, HR stale) với diagnosis/mitigation + peer review 3 câu
- `docs/quality_report.md` — tóm tắt số liệu (raw/cleaned/quarantine records), before/after retrieval analysis
- Toàn bộ phần "Phân công" và "Rủi ro" trong `reports/group_report.md`

**Kết nối với thành viên khác:**
- Ninh cung cấp: cleaned CSV, manifest, expectation results
- Tôi dùng để test: injection dataset, freshness check, eval retrieval
- Feedback loop: nếu eval fail → báo lại Ninh để xem rule/expectation cần điều chỉnh

**Bằng chứng thực tế:**
- `artifacts/eval/after_inject_bad.csv` — eval trên run `inject-bad` (before fix)
- `artifacts/eval/after_fixed_eval.csv` — eval trên run `sprint3-fixed` (after fix)
- `artifacts/manifests/manifest_sprint3-fixed.json` — manifest với `latest_exported_at`, `run_id`, freshness metadata
- `docs/runbook.md` lines 105–... — peer review 3 câu đủ tiêu chuẩn slide Phần E

---

## 2. Một quyết định kỹ thuật

**Quyết định: Chọn `latest_exported_at` (timestamp from cleaned data) thay vì `run_timestamp` (when pipeline ran) cho freshness check.**

Khi thiết kế `freshness_check()`, tôi may lựa chọn:
- Option 1: Dùng `run_timestamp` — khi pipeline chạy
- Option 2: Dùng `latest_exported_at` — khi dữ liệu nguồn được export (có trong CSV)

Tôi chọn **Option 2** (latest_exported_at) vì:

Freshness SLA phải đo **"data latency"** (dữ liệu cũ bao lâu), không phải "pipeline latency" (pipeline chạy mất bao lâu). Nếu dùng run_timestamp, mọi run đều PASS (chỉ cần pipeline chạy) mặc dù data source cũ 1 tháng — sai tinh thần observability.

Lý do khác: CSV export có cột `exported_at` từ hệ thống nguồn. Đó chính là signal về độ tươi của dữ liệu. Nếu 5 ngày chưa có export mới → `latest_exported_at` cũ → FAIL → alert ops để investigate nguồn.

Trade-off: Nếu hệ thống nguồn lỏng (không ghi chính xác `exported_at`), manifest sẽ fallback sang `run_timestamp` (dòng 43 `freshness_check.py`).

---

## 3. Một lỗi / anomaly đã xử lý

**Symptom:** Khi chạy `eval_retrieval.py` lần đầu trên collection của Người A, quả query cho `q_refund_window` trả về `hits_forbidden=yes` (tức là top-k chunks chứa cả "7 ngày" lẫn "14 ngày làm việc"). Thậm chí sau khi Người A chạy pipeline chuẩn, eval vẫn fail.

**Phát hiện:** Kiểm tra Chroma collection.get() → có 2 chunk từ policy_refund_v4: chunk nào có "7 ngày" (đúng) và chunk nào có "14 ngày" (sai). Tôi nghĩ code của Người A chưa prune vector cũ.

**Diagnosis:** Mở `etl_pipeline.py` lines 161-174 → phát hiện `embed_prune_removed` logic. Chạy lại log → thấy `embed_prune_removed=1`, tức là 1 vector cũ đã bị xóa. Nhưng eval vẫn fail → có thể chunk trùng content (hash collision)?

Kỹ luật: Vấn đề nằm ở `_stable_chunk_id()` — nó hash từ `fixed_text` (có annotation `[cleaned: ...]`), không phải text gốc. Nên khi chạy với `--no-refund-fix`, chunk_id thay đổi → prune không recognize cái cũ → cả 2 vector tồn tại.

**Fix:** (Đã ghi chi tiết trong "Lỗi chính cần sửa" của Người A) Hash nên từ **text gốc** trước khi fix.

---

## 4. Bằng chứng trước / sau

**Inject run** (before fix, `artifacts/eval/after_inject_bad.csv`):
```
q_refund_window,contains_expected=yes,hits_forbidden=yes,top1_doc_id=policy_refund_v4
q_p1_sla,contains_expected=yes,hits_forbidden=no,top1_doc_id=sla_p1_2026
q_leave_version,contains_expected=no,hits_forbidden=yes,top1_doc_id=hr_leave_policy
```

**Fixed run** (after fix, `artifacts/eval/after_fixed_eval.csv`):
```
q_refund_window,contains_expected=yes,hits_forbidden=no,top1_doc_id=policy_refund_v4
q_p1_sla,contains_expected=yes,hits_forbidden=no,top1_doc_id=sla_p1_2026
q_leave_version,contains_expected=yes,hits_forbidden=no,top1_doc_id=hr_leave_policy
```

**Analysis:**
- `q_refund_window`: `hits_forbidden` YES → NO (xác nhận chunk "14 ngày" bị prune)
- `q_leave_version`: `contains_expected` NO → YES (xác nhận chunk HR 10 ngày bị quarantine, chỉ còn chunk 12 ngày)
- Bằng chứng: `embed_prune_removed=1` trong log + manifest có `latest_exported_at` tiếp theo timestamp export gốc

---

## 5. Cải tiến tiếp theo

Nếu có 2 giờ thêm:
- Thêm "ingest freshness" (timestamp nhập vào warehouse) so sánh với "publish freshness" (khi embed xong) → phát hiện bottleneck ở ETL hay ở source.
- Mở rộng freshness check: không chỉ SLA tuyệt đối (24h) mà còn kiểm tra trend (dữ liệu có tươi hơn hôm qua không?) → phát hiện export bị stuck.
- Thêm eval dataset lớn hơn (20–50 câu) với ground truth để tính precision/recall chính xác hơn keyword matching.
