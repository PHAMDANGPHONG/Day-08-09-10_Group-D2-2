# Tuning Log — RAG Pipeline (Day 08 Lab)

> Template: Ghi lại mỗi thay đổi và kết quả quan sát được.
> A/B Rule: Chỉ đổi MỘT biến mỗi lần.

---

## Baseline (Sprint 2)

**Ngày:** 2026-04-13  
**Config:**
```
retrieval_mode = "dense"
chunk_size = 400 tokens
overlap = 80 tokens
top_k_search = 10
top_k_select = 3
use_rerank = False
llm_model = gpt-4o-mini
embedding = text-embedding-3-small
```

**Scorecard Baseline:**
| Metric | Average Score |
|--------|--------------|
| Faithfulness | 4.80 /5 |
| Answer Relevance | 4.70 /5 |
| Context Recall | 5.00 /5 |
| Completeness | 3.90 /5 |

**Câu hỏi yếu nhất (điểm thấp):**
- **q07** (Approval Matrix) — Completeness 2/5: Dense retrieve được document đúng nhưng câu trả lời chỉ describe chung chung thay vì trỏ đúng tên tài liệu, vì query dùng alias "Approval Matrix" không xuất hiện verbatim trong document.
- **q10** (hoàn tiền VIP khẩn cấp) — Completeness 2/5, Relevance 2/5: Đúng khi abstain (không có thông tin VIP trong docs), nhưng answer hơi verbose, chưa nêu rõ lý do tài liệu không đề cập.
- **q04** (sản phẩm kỹ thuật số) — Completeness 3/5: Trả lời được rule chính nhưng thiếu nêu rõ exception "lỗi do nhà sản xuất".

**Giả thuyết nguyên nhân (Error Tree):**
- [x] Retrieval: Dense bỏ lỡ exact keyword / alias (q07 "Approval Matrix" → "Access Control SOP")
- [ ] Indexing: Chunking cắt giữa điều khoản
- [ ] Indexing: Metadata thiếu effective_date
- [ ] Retrieval: Top-k quá ít → thiếu evidence
- [x] Generation: Answer thiếu chi tiết exception (q04, q07 completeness thấp)
- [ ] Generation: Context quá dài → lost in the middle

---

## Variant 1 (Sprint 3)

**Ngày:** 2026-04-13  
**Biến thay đổi:** `retrieval_mode = "dense"` → `retrieval_mode = "hybrid"` (dense + BM25 RRF)  
**Lý do chọn biến này:**
Từ baseline, q07 ("Approval Matrix") có Completeness 2/5 vì dense tìm theo ngữ nghĩa nhưng bỏ lỡ keyword exact match — alias "Approval Matrix" không xuất hiện verbatim trong tài liệu "Access Control SOP". Corpus IT/CS helpdesk đặc trưng bởi sự trộn lẫn câu tự nhiên tiếng Việt và keyword kỹ thuật (ticket code "P1", mã lỗi "ERR-403", tên hệ thống "Jira IT-ACCESS"). BM25 xử lý exact keyword tốt hơn dense; hybrid RRF kết hợp cả hai.

**Config thay đổi:**
```
retrieval_mode = "hybrid"  # dense + BM25 Reciprocal Rank Fusion
dense_weight = 0.6
sparse_weight = 0.4
rrf_constant = 60
# Tất cả tham số khác giữ nguyên: top_k=10/3, llm, chunk_size, overlap
```

**Scorecard Variant 1:**
| Metric | Baseline | Variant 1 | Delta |
|--------|----------|-----------|-------|
| Faithfulness | 4.80/5 | 3.80/5 | **-1.00** |
| Answer Relevance | 4.70/5 | 4.20/5 | -0.50 |
| Context Recall | 5.00/5 | 5.00/5 | 0.00 |
| Completeness | 3.90/5 | 3.30/5 | -0.60 |

**Nhận xét:**
- Context Recall vẫn 5.0/5 ở cả hai — BM25 không làm hỏng retrieval, documents đúng vẫn được tìm.
- Hybrid thực sự kém hơn ở **q09** (ERR-403-AUTH): dense trả lời abstain đúng (Faithful 5, Relevant 5), nhưng hybrid lại kéo vào những chunk access control không liên quan → LLM sinh câu trả lời sai bối cảnh (Faithful 1, Relevant 1).
- **q03** (Level 3 approval): baseline Faithful 4, hybrid Faithful 1 — BM25 đẩy lên những chunk có keyword "Level" nhưng không đúng section, làm LLM mix context sai.
- Hybrid cải thiện nhẹ ở **q01** (SLA P1): answer đầy đủ hơn về cả response time và resolution time.

**Kết luận:**
Variant 1 (Hybrid) **không cải thiện** tổng thể so với Baseline trong corpus này. Context Recall đã đạt 5.0/5 ở baseline — vấn đề không nằm ở retrieval recall mà ở generation completeness. BM25 trong hybrid gây nhiễu bằng cách kéo vào những chunk có keyword liên quan nhưng không đúng ngữ cảnh câu hỏi, làm giảm faithfulness. **Baseline dense là cấu hình tốt hơn cho corpus này.**

---

## Variant 2 (nếu có thời gian)

**Biến thay đổi:** ___________  
**Config:**
```
# TODO
```

**Scorecard Variant 2:**
| Metric | Baseline | Variant 1 | Variant 2 | Best |
|--------|----------|-----------|-----------|------|
| Faithfulness | ? | ? | ? | ? |
| Answer Relevance | ? | ? | ? | ? |
| Context Recall | ? | ? | ? | ? |
| Completeness | ? | ? | ? | ? |

---

## Tóm tắt học được

1. **Lỗi phổ biến nhất trong pipeline này là gì?**
   Generation Completeness thấp (avg 3.9/5): LLM trả lời đúng rule chính nhưng thường bỏ sót exception và điều kiện phụ. Ví dụ q04 (sản phẩm kỹ thuật số) bỏ sót exception "lỗi nhà sản xuất"; q07 (Approval Matrix) không nêu tên tài liệu cụ thể.

2. **Biến nào có tác động lớn nhất tới chất lượng?**
   Prompt engineering và generation completeness — không phải retrieval. Context Recall đã đạt 5.0/5, tức là retrieval tìm đúng documents. Điểm yếu là LLM không extract đủ thông tin từ context. Cải thiện tiếp theo nên tập trung vào prompt (yêu cầu liệt kê exception) hoặc top_k_select (tăng từ 3 lên 5).

3. **Nếu có thêm 1 giờ, nhóm sẽ thử gì tiếp theo?**
   Thử tăng `top_k_select` từ 3 → 5 (vẫn giữ `retrieval_mode=dense`) — A/B rule: chỉ đổi 1 biến. Giả thuyết: completeness thấp có thể do thiếu chunk phụ chứa exception. Dự kiến: Faithfulness có thể giảm nhẹ (nhiều context hơn → LLM khó bám sát hơn), nhưng Completeness sẽ tăng.
