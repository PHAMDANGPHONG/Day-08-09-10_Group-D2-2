# Quality report — Lab Day 10

**run_id:** sprint3-fixed (main), inject-bad (corruption), inject-rules-test (new rules proof)  
**Ngày:** 2026-04-15

---

## 1. Tóm tắt số liệu

| Chỉ số | inject-bad (before fix) | sprint3-fixed (after fix) | Ghi chú |
|--------|------------------------|---------------------------|---------|
| raw_records | 10 | 10 | Cùng input CSV |
| cleaned_records | 6 | 6 | inject-bad: refund chunk với "14 ngày" không bị fix nhưng vẫn pass clean (không bị quarantine) |
| quarantine_records | 4 | 4 | Cả 2 run: duplicate row 2, empty row 5, stale HR row 7, unknown doc_id row 9 |
| Expectation halt? | **YES** (E3 FAIL: violations=1) | **NO** (tất cả 8 expectations pass) | inject-bad dùng `--skip-validate` để tiếp tục embed dù halt |

**inject-rules-test (chứng minh rule mới):**

| Chỉ số | Giá trị |
|--------|---------|
| raw_records | 9 |
| cleaned_records | 7 |
| quarantine_records | 2 |
| Quarantine reasons | `future_effective_date` (row 7, date=2099-12-31) + `chunk_too_short_10_chars` (row 8, text="Xem mục 1.") |
| Rule A demo | Row 9 có BOM `\ufeff` trong doc_id → Rule A strip BOM → doc_id thành `policy_refund_v4` → row vào cleaned |
| Expectation halt? | NO (tất cả 8 expectations pass) |

---

## 2. Before / after retrieval

### Câu hỏi then chốt: `q_refund_window`

**Trước (inject-bad — `after_inject_bad.csv`):**
```
question_id,contains_expected,hits_forbidden,top1_doc_id
q_refund_window,yes,yes,policy_refund_v4
```
→ `hits_forbidden=yes`: index có chunk stale "14 ngày làm việc" từ inject-bad run. Agent sẽ trích dẫn thông tin sai.

**Sau (sprint3-fixed — `after_fixed_eval.csv`):**
```
question_id,contains_expected,hits_forbidden,top1_doc_id
q_refund_window,yes,no,policy_refund_v4
```
→ `hits_forbidden=no`: chunk stale đã bị fix thành "7 ngày làm việc". Agent trả lời đúng.

**Kết luận:** Việc inject corruption (`--no-refund-fix`) làm cho eval `q_refund_window` có `hits_forbidden=yes`. Sau khi rerun pipeline chuẩn, `hits_forbidden=no`. Đây là bằng chứng định lượng về tác động của data quality lên retrieval accuracy.

### Merit: `q_leave_version`

**Trước (inject-bad):**
```
question_id,contains_expected,hits_forbidden,top1_doc_id
q_leave_version,yes,no,hr_leave_policy
```

**Sau (sprint3-fixed):**
```
question_id,contains_expected,hits_forbidden,top1_doc_id
q_leave_version,yes,no,hr_leave_policy
```

→ `q_leave_version` pass ở cả 2 run vì inject-bad không ảnh hưởng đến HR policy chunk (chỉ inject refund window). Stale HR chunk (10 ngày, date 2025) bị quarantine trong cả 2 run do baseline rule `stale_hr_policy_effective_date`.

### Tất cả questions (sprint3-fixed):
```
q_refund_window | contains_expected: yes | hits_forbidden: no | top1_doc_id: policy_refund_v4
q_p1_sla        | contains_expected: yes | hits_forbidden: no | top1_doc_id: sla_p1_2026
q_lockout       | contains_expected: yes | hits_forbidden: no | top1_doc_id: it_helpdesk_faq
q_leave_version | contains_expected: yes | hits_forbidden: no | top1_doc_id: hr_leave_policy
```
Tất cả 4 câu pass sau khi pipeline chạy đúng.

---

## 3. Freshness & monitor

**Kết quả:** `freshness_check=FAIL` trên tất cả các run.

```json
{"latest_exported_at": "2026-04-10T08:00:00", "age_hours": 117.6, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}
```

**Giải thích:** CSV mẫu có `exported_at=2026-04-10T08:00:00` cố định — cũ hơn 117 giờ so với ngày chạy lab (2026-04-15). SLA mặc định `FRESHNESS_SLA_HOURS=24`.

**Đây là hành vi đúng**, không phải lỗi code. Trong production:
- CSV export sẽ được sinh tự động với `exported_at = now()`.
- Freshness FAIL sẽ kích hoạt alert trên `#data-alerts-day10`.
- Runbook Incident 2 mô tả cách xử lý.

Nếu muốn test pipeline mà không bị Freshness FAIL, đặt `FRESHNESS_SLA_HOURS=9999` trong `.env` cho môi trường dev.

---

## 4. Corruption inject (Sprint 3)

**Phương pháp inject:**
```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
```
- `--no-refund-fix`: tắt rule fix "14 ngày" → "7 ngày". Chunk stale `policy_refund_v4` không được sửa và đi thẳng vào cleaned CSV.
- `--skip-validate`: bỏ qua halt từ E3 (`refund_no_stale_14d_window` FAIL) để tiếp tục embed.
- Kết quả: Chroma collection có vector embedding cho chunk "14 ngày làm việc" — agent sẽ trích dẫn thông tin sai.

**Detection mechanisms đã kích hoạt:**
1. Log: `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1`
2. Eval: `q_refund_window | hits_forbidden: yes`
3. Manifest: `"no_refund_fix": true, "skipped_validate": true`

**Recovery:**
```bash
python etl_pipeline.py run --run-id sprint3-fixed
# embed_prune_removed=1 — xác nhận vector stale đã bị xoá
```

---

## 5. Hạn chế & việc chưa làm

- **Sample size nhỏ:** CSV mẫu chỉ 10 rows — ý nghĩa thống kê thấp cho các metric.
- **Eval keyword-based:** `eval_retrieval.py` dùng substring matching, không phải semantic similarity. Câu trả lời sai được diễn đạt khác sẽ không bị bắt.
- **Rule A chưa có trong-isolation test:** BOM injection test yêu cầu tạo CSV riêng (`inject2.csv`) và chứng minh trong run `inject-rules-test` — không thể test trực tiếp trên dirty.csv gốc mà không sửa file.
- **Grading JSONL chưa có:** `grading_questions.json` chưa được public (sau 17:00). Cần chạy `python grading_run.py` sau khi file được release.
- **Individual reports:** Chỉ có template — cần điền thông tin thực tế sau khi hoàn thành tất cả code.
