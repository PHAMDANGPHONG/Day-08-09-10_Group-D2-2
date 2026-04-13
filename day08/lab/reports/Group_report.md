# Báo Cáo Nhóm — Lab Day 08: RAG Pipeline

**Nhóm:** D2-2  
**Thành viên:**
| Tên | Vai trò | Email |
|-----|---------|-------|
| Nguyễn Trần Hải Ninh | Tech Lead · Retrieval Owner · Eval Owner| 26ai.ninhnth@vinuni.edu.vn |
| Phạm Đăng Phong | Eval Owner · Documentation Owner | 26ai.phongpd@vinuni.edu.vn |

**Ngày nộp:** 2026-04-13  
**Repository:** `PHAMDANGPHONG/Day-08-09-10_Group-D2-2`

---

## 1. Tổng quan hệ thống

Nhóm xây dựng một **RAG pipeline nội bộ** phục vụ CS Helpdesk và IT Support, trả lời câu hỏi về chính sách hoàn tiền, SLA ticket, quy trình cấp quyền truy cập và HR FAQ. Tất cả câu trả lời đều có trích dẫn nguồn `[N]` và pipeline tự động **abstain** khi không đủ bằng chứng trong corpus — không hallucinate.

### Sơ đồ pipeline

```
[Raw Docs (.txt × 5)]
        │
        ▼
[index.py]
  ├─ preprocess_document()   — parse metadata header (source, dept, date, access)
  ├─ chunk_document()        — split tại === Section === heading
  ├─ _split_by_size()        — overflow chunks với 80-token overlap
  └─ build_index()           — embed → ChromaDB PersistentClient
        │
        ▼
[ChromaDB: 29 chunks, cosine similarity]
        │
  ┌─────┴──────────────────────┐
  ▼                            ▼
[retrieve_dense()]      [retrieve_sparse()]
 OpenAI embedding           BM25Okapi
 top-10 cosine              top-10 keyword
  └───────────┬─────────────┘
              ▼ (Sprint 3 variant)
     [retrieve_hybrid()]
      RRF: dense×0.6 + sparse×0.4
              │
              ▼
     [rerank() → top-3 select]
              │
              ▼
[rag_answer.py]
  ├─ build_context_block()   — format [N] source | section | score
  ├─ build_grounded_prompt() — 6 quy tắc: evidence-only, abstain, citation...
  └─ call_llm()              — gpt-4o-mini, temp=0, max_tokens=512
              │
              ▼
[Grounded Answer + Citation [N]]
              │
              ▼
[eval.py]
  ├─ score_faithfulness()    — LLM-as-Judge (1-5)
  ├─ score_answer_relevance()— LLM-as-Judge (1-5)
  ├─ score_context_recall()  — string matching vs. expected_sources
  ├─ score_completeness()    — LLM-as-Judge vs. expected_answer (1-5)
  ├─ run_scorecard()         — loop 10 test questions
  ├─ compare_ab()            — baseline vs. variant delta table
  └─ generate_grading_log()  — logs/grading_run.json
```

---

## 2. Corpus và Indexing

### 2.1 Tài liệu được index

| File | Source | Department | Số chunk |
|------|--------|-----------|---------|
| `policy_refund_v4.txt` | policy/refund-v4.pdf | CS | 6 |
| `sla_p1_2026.txt` | support/sla-p1-2026.pdf | IT | 5 |
| `access_control_sop.txt` | it/access-control-sop.md | IT Security | 7 |
| `it_helpdesk_faq.txt` | support/helpdesk-faq.md | IT | 6 |
| `hr_leave_policy.txt` | hr/leave-policy-2026.pdf | HR | 5 |
| **Tổng** | | | **29 chunks** |

### 2.2 Quyết định chunking

| Tham số | Giá trị | Lý do |
|---------|---------|-------|
| Strategy | Heading-based (`=== ... ===`) | Corpus có section rõ ràng — mỗi điều khoản nằm trong 1 section, cắt tự nhiên tránh split điều khoản + ngoại lệ vào 2 chunk khác nhau |
| Chunk size | 400 tokens (~1600 ký tự) | Đủ ngữ cảnh cho 1 điều khoản, không gây lost-in-the-middle khi đưa vào prompt |
| Overlap | 80 tokens (~320 ký tự) | Giữ liên mạch tại ranh giới chunk, tránh mất câu ở biên |
| Metadata | source, section, department, effective_date, access | Phục vụ citation, filter freshness, tracing lỗi |

### 2.3 Embedding và Vector Store

| Tham số | Giá trị |
|---------|---------|
| Embedding model | `text-embedding-3-small` (OpenAI, 1536 dims) |
| Vector store | ChromaDB `PersistentClient`, lưu local tại `chroma_db/` |
| Similarity metric | Cosine (`hnsw:space: cosine`) |

---

## 3. Phân công công việc

| Sprint | Deliverable | Người phụ trách |
|--------|------------|----------------|
| Sprint 1 | `index.py` — preprocess, chunk (heading-based + overflow), embed, store vào ChromaDB | **Ninh** |
| Sprint 2 | `rag_answer.py` — `retrieve_dense()`, `build_context_block()`, `build_grounded_prompt()` (6 rules), `call_llm()`, `rag_answer()` | **Ninh** |
| Sprint 3 | `rag_answer.py` — `retrieve_sparse()` (BM25), `retrieve_hybrid()` (RRF), `compare_retrieval_strategies()` | **Ninh** (impl) |
| Sprint 3 | Thiết kế tiêu chí đánh giá variant, chạy scorecard thu số liệu | **Phong** |
| Sprint 4 | `eval.py` — 4 LLM-as-Judge scoring functions, `run_scorecard()`, `compare_ab()`, `generate_scorecard_summary()`, `generate_grading_log()` | **Phong** |
| Docs | `docs/architecture.md`, `docs/tuning-log.md` | **Phong** |

---

## 4. Generation Pipeline

### Grounded Prompt — 6 quy tắc

```
1. EVIDENCE-ONLY  — Chỉ dùng thông tin trong retrieved context.
2. ABSTAIN        — Nếu context không đủ, trả lời:
                    "Tài liệu hiện có không đề cập thông tin này."
3. CITATION       — Luôn cite [N] khi trích dẫn.
4. COMPLETENESS   — Extract đủ số liệu, điều kiện, ngoại lệ, approver, URL.
5. MULTI-SOURCE   — Tổng hợp từ nhiều chunk, cite từng source.
6. LANGUAGE MATCH — Trả lời cùng ngôn ngữ với câu hỏi.
```

### LLM Configuration

| Tham số | Giá trị | Lý do |
|---------|---------|-------|
| Model | `gpt-4o-mini` | Cân bằng chi phí và chất lượng |
| Temperature | `0` | Output ổn định, dễ so sánh qua eval |
| Max tokens | `512` | Đủ dài cho helpdesk answer, không lãng phí |
| Top-k search | `10` | Search rộng trước để không bỏ sót candidate |
| Top-k select | `3` | Chỉ top-3 vào prompt — tránh context noise |

---

## 5. Evaluation — Scorecard Kết quả

### 5.1 Baseline (Sprint 2 — Dense Retrieval)

**Config:** `retrieval_mode=dense`, `top_k=10/3`, `use_rerank=False`

| Metric | Average |
|--------|---------|
| Faithfulness | **4.80 / 5** |
| Answer Relevance | **4.70 / 5** |
| Context Recall | **5.00 / 5** |
| Completeness | **3.90 / 5** |

**Per-question (baseline):**

| ID | Category | Faithful | Relevant | Recall | Complete | Nhận xét |
|----|----------|----------|----------|--------|----------|----------|
| q01 | SLA | 5 | 5 | 5 | 5 | ✅ Trả lời đầy đủ response time + resolution time |
| q02 | Refund | 5 | 5 | 5 | 5 | ✅ Đúng điều kiện 7 ngày làm việc |
| q03 | Access Control | 4 | 5 | 5 | 5 | ✅ Đủ 3 approver (Line Manager, IT Admin, IT Security) |
| q04 | Refund | 4 | 5 | 5 | 3 | ⚠️ Thiếu exception "lỗi do nhà sản xuất" |
| q05 | IT Helpdesk | 5 | 5 | 5 | 4 | ✅ Đúng 5 lần sai, thiếu thời gian unlock |
| q06 | SLA | 5 | 5 | 5 | 5 | ✅ Escalation đầy đủ (10 phút → Senior Engineer) |
| q07 | Access Control | 5 | 5 | 5 | 2 | ⚠️ Retrieve đúng doc nhưng không nêu tên "Access Control SOP" |
| q08 | HR Policy | 5 | 5 | 5 | 5 | ✅ Đúng 2 ngày/tuần, điều kiện Team Lead approve |
| q09 | Insufficient Context | 5 | 5 | — | 3 | ⚠️ Abstain đúng nhưng câu trả lời thêm suy đoán không cần thiết |
| q10 | Refund | 5 | 2 | 5 | 2 | ⚠️ Abstain đúng (VIP không có trong docs) nhưng answer verbose, lạc đề |

### 5.2 Variant (Sprint 3 — Hybrid Retrieval)

**Config:** `retrieval_mode=hybrid` (dense×0.6 + BM25×0.4, RRF k=60), các tham số khác giữ nguyên

| Metric | Baseline | Variant | Delta |
|--------|----------|---------|-------|
| Faithfulness | 4.80 | 3.80 | **−1.00** |
| Answer Relevance | 4.70 | 4.20 | −0.50 |
| Context Recall | 5.00 | 5.00 | **0.00** |
| Completeness | 3.90 | 3.30 | −0.60 |

**Per-question (baseline vs. variant):**

| ID | Category | Base F/R/Rc/C | Variant F/R/Rc/C | Winner |
|----|----------|--------------|------------------|--------|
| q01 | SLA | 5/5/5/5 | 5/5/5/5 | Tie |
| q02 | Refund | 5/5/5/5 | 5/5/5/5 | Tie |
| q03 | Access Control | 4/5/5/5 | **1**/5/5/5 | Baseline |
| q04 | Refund | 4/5/5/3 | 3/4/5/3 | Baseline |
| q05 | IT Helpdesk | 5/5/5/4 | 5/5/5/4 | Tie |
| q06 | SLA | 5/5/5/5 | 5/5/5/**2** | Baseline |
| q07 | Access Control | 5/5/5/2 | 3/5/5/2 | Baseline |
| q08 | HR Policy | 5/5/5/5 | 5/5/5/4 | Baseline |
| q09 | Insufficient | 5/5/—/3 | **1/1**/—/**1** | **Baseline** (critical) |
| q10 | Refund | 5/2/5/2 | 5/2/5/2 | Tie |

---

## 6. A/B Analysis — Lý do chọn Variant và Kết luận

### Giả thuyết ban đầu

Câu **q07** ("Approval Matrix để cấp quyền là tài liệu nào?") đạt Completeness 2/5 ở baseline. Nhóm giả thuyết nguyên nhân là **alias mismatch**: query dùng "Approval Matrix" nhưng tài liệu có tên "Access Control SOP". BM25 xử lý exact keyword match tốt hơn dense — kỳ vọng hybrid cải thiện q07.

### Kết quả thực tế và lý do Variant kém hơn

**Context Recall đã đạt ceiling 5.0/5 ở baseline** — retrieval tìm đúng document trong 100% câu hỏi. Vấn đề không nằm ở retrieval mà ở generation completeness.

BM25 thay vì giúp, lại gây ra **2 regression nghiêm trọng:**

1. **q09 — ERR-403-AUTH (câu abstain):** Baseline abstain đúng (Faithful 5/5) vì dense không tìm được chunk liên quan. Hybrid: BM25 match token "403" + "access" trong `access_control_sop.txt`, kéo chunk sai vào context → LLM sinh câu trả lời hoàn toàn không grounded (Faithful **1/5**, Relevant **1/5**, Complete **1/5**). Đây là failure mode nguy hiểm nhất — từ "không biết" sang "bịa có vẻ hợp lý".

2. **q03 — Level 3 approval:** BM25 đẩy chunk chứa keyword "Level" nhưng sai section → LLM mix approver list sai (Faithful từ 4 xuống **1**).

### Kết luận

> **Baseline dense là cấu hình tốt hơn cho corpus này.**  
> Biến thay đổi duy nhất là `retrieval_mode` (dense → hybrid). Hybrid không giải quyết đúng root cause (generation completeness) và tạo ra regression mới nghiêm trọng ở câu abstain — loại câu có penalty cao nhất trong rubric chấm.

**Cấu hình dùng cho `grading_questions.json`:** `retrieval_mode = "dense"`, `top_k_search=10`, `top_k_select=5`.

---

## 7. Grading Run — Kết quả 10 Câu Ẩn

**File:** `logs/grading_run.json` — chạy lúc 17:19, ngày 2026-04-13

| ID | Câu hỏi tóm tắt | Kỹ năng kiểm tra | Kết quả tóm tắt |
|----|----------------|-----------------|-----------------|
| gq01 | SLA P1 thay đổi thế nào so với phiên bản trước? | Freshness & version | ✅ Nêu được v2026.1 cập nhật từ 6h → 4h, đủ chi tiết |
| gq02 | Remote + VPN + giới hạn thiết bị? | Multi-doc synthesis | ✅ Đúng: VPN bắt buộc, tối đa 2 thiết bị |
| gq03 | Flash Sale + đã kích hoạt → hoàn tiền không? | Exception completeness | ✅ Nêu cả 2 lý do không được hoàn (Flash Sale + đã kích hoạt) |
| gq04 | Store credit được bao nhiêu %? | Numeric fact | ✅ Đúng: 110% giá trị hoàn |
| gq05 | Contractor cần Admin Access — điều kiện? | Multi-section retrieval | ✅ Đủ: 5 ngày, security training, IT Manager + CISO |
| gq06 | P1 lúc 2am → cấp quyền tạm thời thế nào? | Cross-doc multi-hop | ✅ Đúng: on-call admin, Tech Lead verbal approve, tối đa 24h, log vào Security Audit |
| gq07 | Mức phạt vi phạm SLA P1 là bao nhiêu? | Abstain / anti-hallucination | ✅ Abstain đúng: "Tài liệu hiện có không đề cập thông tin này" |
| gq08 | Báo nghỉ phép 3 ngày = nghỉ ốm 3 ngày không? | Disambiguation | ✅ Phân biệt đúng: nghỉ phép báo trước 3 ngày làm việc ≠ nghỉ ốm >3 ngày cần giấy tờ |
| gq09 | Mật khẩu đổi mấy ngày, nhắc trước mấy ngày, qua đâu? | Multi-detail FAQ | ✅ Đủ: 90 ngày, nhắc trước 7 ngày, URL https://sso.company.internal/reset |
| gq10 | Chính sách v4 áp dụng đơn trước 01/02 không? | Temporal scoping | ✅ Đúng: không áp dụng, đơn trước 01/02/2026 theo chính sách v3 |

---

## 8. Failure Mode Analysis

| Failure Mode | Câu bị ảnh hưởng | Root cause | Status |
|-------------|-----------------|------------|--------|
| Generation thiếu ngoại lệ | q04, q07 (baseline) | LLM không extract exception từ context | ⚠️ Chưa fix — cần prompt thêm "liệt kê tất cả ngoại lệ" |
| BM25 gây nhiễu abstain | q09, q03 (hybrid only) | Token overlap ≠ semantic relevance | ✅ Đã giải quyết: loại hybrid, dùng dense |
| Answer verbose khi abstain | q09, q10 (baseline) | Prompt không specified "concise abstain" | ⚠️ Chưa fix |
| Alias mismatch | q07 | "Approval Matrix" ≠ "Access Control SOP" | ↔️ Dense embedding đủ gần, retrieve đúng nhưng generation không nêu tên |

---

## 9. Điều nhóm học được

**1. Chạy scorecard trước khi quyết định tune ở đâu:**  
Context Recall 5.0/5 ngay ở baseline cho thấy retrieval không phải vấn đề. Nếu không có eval, nhóm sẽ tiếp tục tune retrieval — lãng phí thời gian và tạo regression.

**2. A/B discipline — 1 biến mỗi lần:**  
Chỉ đổi `retrieval_mode` (dense → hybrid), giữ nguyên chunk size, top\_k, prompt, LLM. Nhờ đó biết chính xác BM25 là nguyên nhân regression ở q09 và q03.

**3. LLM-as-Judge hoạt động tốt nhưng có giới hạn ở Completeness:**  
Faithfulness và Relevance nhất quán với `temperature=0`. Completeness phụ thuộc chất lượng `expected_answer` — nếu expected\_answer không liệt kê ngoại lệ, judge cho điểm cao nhầm.

**4. BM25 + dense corpus đa ngôn ngữ = rủi ro cao:**  
Corpus tiếng Việt mixed với keyword kỹ thuật tiếng Anh (P1, ERR-403, Level 3) làm BM25 token matching kém tin cậy hơn so với corpus thuần một ngôn ngữ.

---

## 10. Nếu có thêm thời gian

**Ưu tiên cao — tăng `top_k_select` từ 3 lên 5** (giữ dense):  
Giả thuyết: chunk chứa ngoại lệ (q04: "lỗi nhà sản xuất") nằm ở rank 4–5, không vào prompt khi `top_k_select=3`. Expected: Completeness tăng từ 3.90, Faithfulness giảm nhẹ (acceptable nếu > 4.5).

**Ưu tiên trung bình — prompt enhancement cho ngoại lệ:**  
Thêm vào `build_grounded_prompt()`: *"If the question is about policies or rules, explicitly list ALL exceptions and conditions mentioned in the context, even if they appear in separate sentences."*

---

*Nhóm D2-2 — Lab Day 08: RAG Pipeline — 2026-04-13*
