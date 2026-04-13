# Báo Cáo Cá Nhân — Lab Day 08: RAG Pipeline

**Họ và tên:** Nguyễn Trần Hải Ninh  
**Vai trò trong nhóm:** Tech Lead, Retrieval Owner  
**Ngày nộp:** 2026-04-13  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi đã làm gì trong lab này? (100-150 từ)

Tôi phụ trách **Sprint 1, 2 và 3** — tức toàn bộ pipeline từ indexing đến retrieval và tuning.

**Sprint 1 (`index.py`):** Tôi implement hàm `preprocess_document()` để parse metadata header từ 5 file `.txt` (source, department, effective\_date, access), sau đó viết `chunk_document()` split tài liệu theo heading `=== Section ===` tự nhiên, và hàm `_split_by_size()` xử lý section dài với overlap 80 tokens. Kết quả: 29 chunks có đủ 5 metadata fields, index vào ChromaDB với cosine similarity.

**Sprint 2 (`rag_answer.py`):** Tôi implement `retrieve_dense()` (embed query → query ChromaDB, convert distance → score), `build_context_block()` định dạng prompt với số thứ tự `[N]`, và `build_grounded_prompt()` với 6 quy tắc evidence-only, abstain, citation, completeness, multi-source, language-match.

**Sprint 3 (`rag_answer.py`):** Tôi implement `retrieve_sparse()` (BM25Okapi) và `retrieve_hybrid()` (Reciprocal Rank Fusion, dense×0.6 + sparse×0.4), đồng thời chạy `compare_retrieval_strategies()` để có data so sánh. Kết quả này feed vào `tuning-log.md` do Phong hoàn thiện.

---

## 2. Điều tôi hiểu rõ hơn sau lab này (100-150 từ)

**Chunking theo cấu trúc tự nhiên vs. chunking theo token count cứng:**  
Trước lab, tôi nghĩ chunk size 400 tokens là con số kỹ thuật đơn giản. Sau khi implement `chunk_document()`, tôi hiểu tại sao heading-based chunking quan trọng hơn: nếu cắt cứng theo ký tự, điều khoản ngoại lệ như "trừ trường hợp lỗi do nhà sản xuất" có thể bị cắt đôi giữa 2 chunk, khiến LLM không bao giờ thấy đủ bối cảnh để trả lời đúng. Đây chính xác là failure mode q04 (sản phẩm kỹ thuật số) trong scorecard của nhóm.

**Grounded prompt và abstain rule:**  
Tôi implement `build_grounded_prompt()` với quy tắc ABSTAIN: nếu context không chứa câu trả lời, LLM phải nói rõ "Tài liệu hiện có không đề cập thông tin này" thay vì suy luận từ general knowledge. Thực tế với q10 ("hoàn tiền VIP khẩn cấp") — docs không đề cập VIP — pipeline abstain đúng. Điều này cho thấy grounding không chỉ là prompt engineering: nó là cam kết thiết kế về việc hệ thống biết giới hạn của mình.

---

## 3. Điều tôi ngạc nhiên hoặc gặp khó khăn (100-150 từ)

**Hybrid retrieval làm giảm điểm, không tăng như kỳ vọng:**  
Tôi giả thuyết rằng hybrid (dense + BM25) sẽ cải thiện q07 ("Approval Matrix" khi tài liệu dùng tên "Access Control SOP") vì BM25 xử lý keyword chính xác tốt hơn. Nhưng kết quả thực tế: Faithfulness giảm từ 4.80 xuống 3.80 (-1.00), Completeness giảm từ 3.90 xuống 3.30 (-0.60).

Nguyên nhân tôi phát hiện khi debug: BM25 kéo lên những chunk có keyword "Level" hoặc "access" nhưng không đúng section (q03, q09). Ví dụ q09 (ERR-403-AUTH) — dense abstain đúng (context recall = 5/5, không có thông tin trong docs), nhưng BM25 lại tìm được chunk access control "có chứa ký tự gần giống", dẫn tới LLM sinh câu trả lời hoàn toàn sai ngữ cảnh (Faithfulness từ 5 xuống 1).

Bài học: Context Recall đã đạt ceiling 5.0/5 ở baseline — retrieval không phải điểm yếu. Thêm BM25 không giải quyết vấn đề gốc là generation completeness.

---

## 4. Phân tích một câu hỏi trong scorecard (150-200 từ)

**Câu hỏi:** q07 — "Để cấp quyền admin cho contractor, văn bản nào cần được tham chiếu?"  
*(Câu này kiểm tra alias resolution: query dùng "Approval Matrix" nhưng tài liệu thực tế có tên "Access Control SOP")*

**Phân tích:**

**Baseline (dense) trả lời:** Đúng document (Context Recall 5/5), nhưng Completeness 2/5. Pipeline tìm được `access_control_sop.txt` vì embedding của "cấp quyền admin contractor" gần với embedding của nội dung SOP. Tuy nhiên, câu trả lời chỉ mô tả chung "cần tham chiếu tài liệu kiểm soát truy cập" mà không nêu tên cụ thể "Access Control SOP" hay số tài liệu.

**Lỗi nằm ở đâu:** Generation — không phải Indexing hay Retrieval. Chunk được retrieve đúng, nhưng LLM không extract metadata `source` thành tên tài liệu đọc được. Lý do: prompt của tôi yêu cầu cite `[N]` theo index số, nhưng không yêu cầu nêu tên tài liệu trong body câu trả lời.

**Variant (hybrid) có cải thiện không:** Không — Completeness vẫn 2/5, Faithfulness còn giảm thêm vì BM25 kéo thêm chunk không liên quan vào context.

**Fix đề xuất:** Thêm vào grounded prompt: "When naming a document, use its full name from the source field, not just the citation number." Đây là prompt-level fix, không cần thay đổi retrieval.

---

## 5. Nếu có thêm thời gian, tôi sẽ làm gì? (50-100 từ)

Tôi sẽ thử **tăng `top_k_select` từ 3 lên 5** (giữ nguyên `retrieval_mode=dense`, A/B rule: 1 biến). Lý do: scorecard baseline cho thấy Completeness là điểm yếu nhất (3.90/5), còn Faithfulness đã rất cao (4.80/5). Giả thuyết: LLM bỏ sót exception (q04, q07) vì chunk chứa exception nằm ở rank 4–5, không vào prompt. Tăng top_k_select sẽ expose thêm context mà không thay đổi retrieval. Nếu Faithfulness giảm dưới 4.5, tôi sẽ revert — đó là ngưỡng chấp nhận được.

---
