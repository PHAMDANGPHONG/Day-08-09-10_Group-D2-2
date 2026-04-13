# Báo Cáo Cá Nhân — Lab Day 08: RAG Pipeline

**Họ và tên:** Phạm Đăng Phong  
**Vai trò trong nhóm:** Eval Owner, Documentation Owner  
**Ngày nộp:** 2026-04-13  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi đã làm gì trong lab này? (100-150 từ)

Tôi phụ trách **Sprint 3 (phần evaluation design) và Sprint 4 (toàn bộ `eval.py`)**, cùng với `docs/tuning-log.md` và `docs/architecture.md`.

**Sprint 3 (hỗ trợ):** Tôi thiết kế tiêu chí để đánh giá variant hybrid mà Ninh implement — cụ thể là xác định câu hỏi nào trong test set sẽ phân biệt được dense vs. hybrid (q07 "Approval Matrix", q09 "ERR-403-AUTH"), và chạy scorecard để thu thập số liệu thực.

**Sprint 4 (`eval.py`):** Tôi implement 4 scoring functions: `score_faithfulness()`, `score_answer_relevance()`, `score_context_recall()`, `score_completeness()` — tất cả đều dùng LLM-as-Judge (gpt-4o-mini, JSON output). Tôi viết `run_scorecard()` với loop qua 10 test questions, `compare_ab()` in bảng so sánh per-question và aggregate, và `generate_grading_log()` để tạo `logs/grading_run.json` đúng format khi `grading_questions.json` được public lúc 17:00.

Kết quả của tôi (scorecard baseline và variant) trực tiếp quyết định kết luận trong `tuning-log.md`.

---

## 2. Điều tôi hiểu rõ hơn sau lab này (100-150 từ)

**LLM-as-Judge và vấn đề calibration:**  
Trước lab tôi nghĩ chấm điểm bằng LLM là "cho LLM chấm LLM" — không đáng tin. Sau khi implement và chạy, tôi thấy LLM-as-Judge với prompt cụ thể và `temperature=0` cho kết quả khá nhất quán ở các metric có tiêu chí rõ ràng (Faithfulness, Relevance). Tuy nhiên, `score_completeness()` vẫn phụ thuộc nhiều vào `expected_answer` — nếu expected\_answer thiếu chi tiết, LLM judge cũng dễ cho điểm cao nhầm.

**Context Recall là metric về retrieval, không phải generation:**  
`score_context_recall()` không gọi LLM mà dùng string matching: kiểm tra xem expected\_sources có trong retrieved sources không. Đây là metric duy nhất không bị ảnh hưởng bởi LLM judge bias. Kết quả Context Recall = 5.0/5 ở cả baseline lẫn variant cho thấy lỗi không nằm ở retrieval — đây là insight quan trọng định hướng A/B test.

---

## 3. Điều tôi ngạc nhiên hoặc gặp khó khăn (100-150 từ)

**Khó khăn với `score_context_recall()` và partial source matching:**  
Ban đầu tôi implement exact string match cho `expected_sources`. Pipeline trả về source là full path (`/path/to/data/docs/sla_p1_2026.txt`) trong khi test\_questions.json có `expected_sources: ["support/sla-p1-2026.pdf"]`. Match hoàn toàn thất bại → recall = 0/5 mặc dù đúng document.

Tôi phải thêm bước normalize: extract filename, strip extension, lowercase rồi mới kiểm tra partial match. Sau fix: recall từ 0 lên đúng giá trị thực. Bài học: mismatch format giữa các tầng của hệ thống (chunking format metadata vs. expected format trong test) là nguồn bug thầm lặng — không crash nhưng cho kết quả sai hoàn toàn.

**Ngạc nhiên về tốc độ LLM-as-Judge:**  
10 câu × 3 metric LLM calls = 30 API calls. Với gpt-4o-mini tại thời điểm lab, mỗi call ~2-3 giây → cả scorecard mất khoảng 1 phút. Với 2 config (baseline + variant) = ~2 phút. Đây là con số quan trọng khi phải chạy lại nhiều lần để debug.

---

## 4. Phân tích một câu hỏi trong scorecard (150-200 từ)

**Câu hỏi:** q09 — "ERR-403-AUTH là lỗi gì và cần làm gì?" *(câu kiểm tra abstain / anti-hallucination)*

**Phân tích:**

**Baseline (dense) trả lời:** Abstain đúng — "Tài liệu hiện có không đề cập thông tin này." Faithfulness 5/5, Relevance 5/5. Dense embedding không tìm thấy chunk nào đủ gần với "ERR-403-AUTH" (mã lỗi này không có trong 5 tài liệu), nên context rỗng → LLM kích hoạt abstain rule.

**Lỗi nằm ở đâu (với Variant hybrid):** Retrieval — cụ thể là BM25. Khi chạy hybrid, BM25 tokenize "ERR-403-AUTH" và match với các chunk trong `access_control_sop.txt` chứa từ "access", "403", hoặc mô tả lỗi truy cập. BM25 không hiểu ngữ nghĩa — nó chỉ thấy overlap token. Những chunk này được RRF fusion đẩy lên top-3, cung cấp context sai cho LLM → LLM sinh câu trả lời về "lỗi truy cập trái phép" không có trong docs (Faithfulness 1/5, Relevance 1/5).

**Đây là failure mode nguy hiểm nhất:** Hệ thống từ abstain đúng (safe) sang hallucinate có vẻ hợp lý (harmful) chỉ vì thêm BM25. Với grading question gq07 (câu tương tự — thông tin không có trong docs), pipeline baseline abstain đúng, còn hybrid có nguy cơ bị penalty -50%.

**Kết luận:** Tôi quyết định dùng **baseline dense** cho `grading_run.json` thay vì variant hybrid — evidence từ scorecard rõ ràng: hybrid tệ hơn ở câu abstain, đây là câu có penalty cao nhất.

---

## 5. Nếu có thêm thời gian, tôi sẽ làm gì? (50-100 từ)

Tôi sẽ thêm **Abstain Rate** như metric thứ 5 trong scorecard: đếm số câu pipeline trả lời "không đủ dữ liệu" vs. số câu thực sự không có trong docs. Scorecard hiện tại không tách biệt được "abstain đúng" (tốt) và "abstain sai" (pipeline fail vì không retrieve được). Với abstain rate, có thể phát hiện regression như hybrid q09: recall vẫn 5/5 nhưng abstain rate về 0 — signal rõ rằng pipeline đang hallucinate thay vì abstain.

---
