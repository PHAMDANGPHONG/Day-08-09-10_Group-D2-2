# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** Ning  
**Thành viên:**
| Tên | Sprint | Vai trò | File chính | Email |
|-----|--------|---------|-----------|-------|
| Nguyễn Trần Hải Ninh | 1–2 | Ingestion & Cleaning & Quality Owner | `transform/cleaning_rules.py`, `quality/expectations.py`, `etl_pipeline.py::cmd_run()` | 26ai.ninhnth@vinuni.edu.vn |
| Phạm Đăng Phong | 3–4 | Eval & Monitoring & Docs Owner | `eval_retrieval.py`, `monitoring/freshness_check.py`, `docs/runbook.md`, `docs/pipeline_architecture.md` | 26ai.phongpd@vinuni.edu.vn |

**Ngày nộp:** 2026-04-15  
**Repo:** e:/VinUni/assignments/Lecture-Day-08-09-10  
**Độ dài khuyến nghị:** 600–1000 từ

---

## 1. Pipeline tổng quan

Nguồn dữ liệu là `data/raw/policy_export_dirty.csv` — một CSV export mô phỏng dữ liệu thực tế từ hệ thống quản lý policy của CS + IT Helpdesk. File có 10 rows với nhiều lỗi cố ý: duplicate chunk, cửa sổ hoàn tiền sai (14 ngày thay vì 7 ngày), HR policy version cũ (10 ngày thay vì 12 ngày), ngày sai format (DD/MM/YYYY thay vì YYYY-MM-DD), chunk rỗng, và doc_id không hợp lệ.

Luồng ETL đầy đủ: **Raw CSV → Ingest → Transform (clean + quarantine) → Quality (expectation suite) → Embed (Chroma upsert + prune) → Monitor (freshness check)**. Mỗi bước ghi log với `run_id` để truy vết. Artifacts được lưu tại `artifacts/`: logs, cleaned CSV, quarantine CSV, manifests, eval CSV.

**Lệnh chạy toàn bộ pipeline:**
```bash
cd day10/lab
python etl_pipeline.py run --run-id sprint3-fixed
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_sprint3-fixed.json
python eval_retrieval.py --out artifacts/eval/after_fixed_eval.csv
```

`run_id` xuất hiện ở dòng đầu log: `run_id=sprint3-fixed`. Tất cả artifact files đều có suffix `_sprint3-fixed`.

### 1a. Phân công chi tiết (2 người)

**Ninh (Sprint 1–2):**
- Ingest: `load_raw_csv()`, `LOG_DIR`, `manifest` schema
- Transform: `cleaning_rules.py` (baseline + 3 rule mới: BOM strip, future date, min length)
- Quality: `expectations.py` (baseline + E7, E8)
- Embed: `cmd_embed_internal()` logic + Chroma upsert + prune
- Input: `data/raw/policy_export_dirty.csv` (tạo/test)
- Bằng chứng: Log file với `raw_records`, `cleaned_records`, `quarantine_records`

**Phong (Sprint 3–4):**
- Eval: `eval_retrieval.py` (before/after CSV)
- Monitoring: `freshness_check.py`
- Docs: `pipeline_architecture.md`, `data_contract.md`, `runbook.md` (3 incident scenarios)
- Quality report: `docs/quality_report.md` (tóm tắt số liệu, before/after analysis)
- Bằng chứng: `after_inject_bad.csv`, `after_fixed_eval.csv`, manifest với `latest_exported_at`

---

## 2. Cleaning & expectation

Baseline của lab đã có 6 cleaning rules và 6 expectations. Nhóm đã thêm 3 rule mới và 2 expectations mới, tất cả đều có tác động đo được trên dữ liệu inject.

### 2a. Bảng metric_impact (bắt buộc)

| Rule / Expectation mới | Trước inject | Sau inject (inject-rules-test) | Chứng cứ |
|------------------------|-------------|-------------------------------|----------|
| **Rule A: strip_bom_control_chars** | quarantine=3 (row 9 bị quarantine do `unknown_doc_id` vì BOM làm hỏng doc_id) | quarantine=2, cleaned=7 (BOM stripped → doc_id khớp allowlist → row vào cleaned) | `quarantine_inject-rules-test.csv`: row 9 không còn trong quarantine |
| **Rule B: quarantine_future_effective_date** | cleaned=8 (row 7 date=2099-12-31 lọt vào cleaned) | quarantine=2 (row 7 bị quarantine với `reason=future_effective_date`) | `quarantine_inject-rules-test.csv` row 7: `future_effective_date` |
| **Rule C: normalize_whitespace + quarantine_very_short_chunk** | cleaned=8 (row 8 "Xem mục 1." 10 chars pass baseline 8-char) | quarantine=2 (row 8 bị quarantine với `reason=chunk_too_short_10_chars`) | `quarantine_inject-rules-test.csv` row 8: `chunk_too_short_10_chars` |
| **E7: no_future_effective_date (halt)** | N/A trên dirty.csv (không có future date) | FAIL khi inject (không dùng `--skip-validate` → halt pipeline) | Expectation log: `no_future_effective_date FAIL` nếu Rule B bị tắt |
| **E8: no_cleaned_annotation_in_non_refund (warn)** | PASS | PASS (không có regression) | Log: `no_cleaned_annotation_in_non_refund OK (warn)` |

**Rule chính (baseline + mở rộng):**
1. **Allowlist doc_id** — quarantine nếu `doc_id` không thuộc 4 doc hợp lệ
2. **Date normalization** — DD/MM/YYYY → ISO YYYY-MM-DD
3. **HR stale version** — `hr_leave_policy` với date < 2026-01-01 → quarantine
4. **Empty text/date** — quarantine nếu chunk_text hoặc effective_date rỗng
5. **Deduplication** — quarantine nếu text trùng (normalized)
6. **Refund window fix** — "14 ngày làm việc" → "7 ngày làm việc" trong `policy_refund_v4`
7. *(Mới)* **Strip BOM/control chars** — xoá `\ufeff`, `\u200b`, `\xa0` khỏi doc_id và chunk_text
8. *(Mới)* **Future effective_date** — quarantine nếu date > today
9. *(Mới)* **Whitespace normalize + min length 20** — normalize whitespace, quarantine nếu < 20 chars

**Expectation fail đã xử lý:**
Khi chạy `inject-bad` (`--no-refund-fix`): `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1`. Pipeline halt. Xử lý: chạy lại với `--skip-validate` chỉ để demo Sprint 3, sau đó rerun `sprint3-fixed` để khôi phục.

---

## 3. Before / after ảnh hưởng retrieval

**Kịch bản inject (Sprint 3):**

Chạy pipeline với `--no-refund-fix --skip-validate` (`run-id=inject-bad`) để bỏ qua fix cửa sổ hoàn tiền. Điều này cho phép chunk stale "14 ngày làm việc" đi vào Chroma collection. Expectation E3 FAIL nhưng bị bỏ qua bởi `--skip-validate`.

**Kết quả định lượng:**

| Question | Run: inject-bad | Run: sprint3-fixed | Thay đổi |
|----------|----------------|-------------------|----------|
| `q_refund_window` | `contains_expected=yes`, **`hits_forbidden=yes`** | `contains_expected=yes`, **`hits_forbidden=no`** | `hits_forbidden` YES → NO |
| `q_p1_sla` | `hits_forbidden=no` | `hits_forbidden=no` | Không đổi |
| `q_lockout` | `hits_forbidden=no` | `hits_forbidden=no` | Không đổi |
| `q_leave_version` | `hits_forbidden=no` | `hits_forbidden=no` | Không đổi |

**Phân tích:** Khi có chunk stale trong index, Chroma retrieval cho `q_refund_window` trả về cả chunk "7 ngày" (đúng) lẫn chunk "14 ngày" (sai) trong top-k, khiến `hits_forbidden=yes`. Sau khi rerun pipeline chuẩn, Chroma prune xoá vector cũ (`embed_prune_removed=1`), chỉ còn chunk đã fix với "7 ngày", `hits_forbidden=no`.

Đây là bằng chứng định lượng trực tiếp: **dữ liệu bẩn → retrieval sai → agent sẽ trả lời sai**. Và ngược lại: **pipeline ETL đúng → retrieval đúng → agent trả lời đúng**.

Artifacts: `artifacts/eval/after_inject_bad.csv` (before fix) và `artifacts/eval/after_fixed_eval.csv` (after fix).

---

## 4. Freshness & monitoring

SLA: `FRESHNESS_SLA_HOURS=24` (mặc định trong `.env`). Ý nghĩa:
- **PASS**: `age_hours ≤ 24` — dữ liệu đủ mới, pipeline có thể phục vụ agent
- **WARN**: manifest không có timestamp `latest_exported_at` — cần kiểm tra nguồn
- **FAIL**: `age_hours > 24` — dữ liệu cũ, nên trigger rerun hoặc alert

Tất cả các run trong lab đều cho `freshness_check=FAIL` vì CSV mẫu có `exported_at=2026-04-10T08:00:00` cố định (5 ngày trước ngày chạy lab). Đây là hành vi đúng — trong production, `exported_at` sẽ được ghi tự động khi export.

Kết quả từ `sprint3-fixed`:
```
freshness_check=FAIL {"latest_exported_at": "2026-04-10T08:00:00", "age_hours": 117.6, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}
```

---

## 5. Liên hệ Day 09

Pipeline Day 10 sử dụng collection riêng `day10_kb` (khác với `day09_kb` hoặc collection mặc định của Day 09). Lý do tách: tránh ô nhiễm dữ liệu — Day 09 embed trực tiếp từ `data/docs/*.txt` không qua ETL; Day 10 embed từ CSV export đã qua pipeline clean.

Nếu muốn Day 09 multi-agent sử dụng corpus đã clean của Day 10, chỉ cần đổi `CHROMA_COLLECTION=day09_kb` trong `.env` trước khi chạy `etl_pipeline.py run`. Điều này sẽ upsert và prune collection Day 09 với dữ liệu sạch hơn từ Day 10.

---

## 6. Rủi ro còn lại & việc chưa làm

- **Grading JSONL chưa có**: `grading_questions.json` chưa được public. Cần chạy `python grading_run.py` sau 17:00.
- **Eval dùng keyword matching**: Không phát hiện câu trả lời sai được diễn đạt khác.
- **HR cutoff hard-coded**: `"2026-01-01"` trong `cleaning_rules.py` không đọc từ `data_contract.yaml` — Distinction tier yêu cầu non-hardcoded versioning.
- **Unit tests chưa có**: Không có pytest fixtures cho từng cleaning rule.
- **Chỉ một thành viên**: Lab được thiết kế cho nhóm; một số phân tích có thể thiếu góc nhìn cross-review.
