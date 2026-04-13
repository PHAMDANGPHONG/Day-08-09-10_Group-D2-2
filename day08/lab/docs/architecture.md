# Architecture — RAG Pipeline (Day 08 Lab)

> Template: Điền vào các mục này khi hoàn thành từng sprint.
> Deliverable của Documentation Owner.

## 1. Tổng quan kiến trúc

```
[Raw Docs]
    ↓
[index.py: Preprocess → Chunk → Embed → Store]
    ↓
[ChromaDB Vector Store]
    ↓
[rag_answer.py: Query → Retrieve → Rerank → Generate]
    ↓
[Grounded Answer + Citation]
```

**Mô tả ngắn gọn:**
Hệ thống RAG nội bộ phục vụ CS Helpdesk và IT Support, trả lời câu hỏi về chính sách hoàn tiền, SLA ticket, quy trình cấp quyền và HR FAQ dựa trên 5 tài liệu nội bộ. Pipeline đảm bảo mọi câu trả lời đều có trích dẫn nguồn và tự động abstain khi không đủ bằng chứng, tránh hallucination.

---

## 2. Indexing Pipeline (Sprint 1)

### Tài liệu được index
| File | Nguồn | Department | Số chunk |
|------|-------|-----------|---------|
| `policy_refund_v4.txt` | policy/refund-v4.pdf | CS | 6 |
| `sla_p1_2026.txt` | support/sla-p1-2026.pdf | IT | 5 |
| `access_control_sop.txt` | it/access-control-sop.md | IT Security | 7 |
| `it_helpdesk_faq.txt` | support/helpdesk-faq.md | IT | 6 |
| `hr_leave_policy.txt` | hr/leave-policy-2026.pdf | HR | 5 |

**Tổng: 29 chunks**

### Quyết định chunking
| Tham số | Giá trị | Lý do |
|---------|---------|-------|
| Chunk size | 400 tokens (~1600 ký tự) | Đủ ngữ cảnh cho 1 điều khoản, không quá dài gây lost-in-the-middle |
| Overlap | 80 tokens (~320 ký tự) | Tránh mất thông tin khi điều khoản nằm ở ranh giới chunk |
| Chunking strategy | Heading-based (split tại `=== ... ===`) | Tài liệu có cấu trúc section rõ ràng; cắt tự nhiên theo điều khoản |
| Metadata fields | source, section, effective_date, department, access | Phục vụ filter, freshness, citation |

### Embedding model
- **Model**: OpenAI `text-embedding-3-small` (1536 dimensions)
- **Vector store**: ChromaDB `PersistentClient` — lưu local tại `chroma_db/`
- **Similarity metric**: Cosine (cấu hình `hnsw:space: cosine`)

---

## 3. Retrieval Pipeline (Sprint 2 + 3)

### Baseline (Sprint 2)
| Tham số | Giá trị |
|---------|---------|
| Strategy | Dense (embedding similarity) |
| Top-k search | 10 |
| Top-k select | 3 |
| Rerank | Không |

### Variant (Sprint 3)
| Tham số | Giá trị | Thay đổi so với baseline |
|---------|---------|------------------------|
| Strategy | Hybrid (dense + BM25 Reciprocal Rank Fusion) | Thay dense-only → hybrid |
| Dense weight | 0.6 | Mới |
| Sparse weight | 0.4 | Mới |
| Top-k search | 10 | Giữ nguyên |
| Top-k select | 3 | Giữ nguyên |
| RRF constant | 60 (chuẩn) | Mới |

**Lý do chọn Hybrid:**
Corpus trộn lẫn hai loại nội dung: (1) câu tự nhiên tiếng Việt (policy, HR) — dense xử lý tốt qua ngữ nghĩa; (2) keyword kỹ thuật chính xác ("P1", "Level 3", "ERR-403", "IT-ACCESS") — BM25 tìm kiếm chính xác hơn. Hybrid RRF kết hợp điểm mạnh của cả hai, phù hợp với đặc điểm corpus IT/CS helpdesk.

---

## 4. Generation (Sprint 2)

### Grounded Prompt Template
```
Answer only from the retrieved context below.
If the context is insufficient, say you do not know.
Cite the source field when possible.
Keep your answer short, clear, and factual.

Question: {query}

Context:
[1] {source} | {section} | score={score}
{chunk_text}

[2] ...

Answer:
```

### LLM Configuration
| Tham số | Giá trị |
|---------|---------|
| Model | gpt-4o-mini |
| Temperature | 0 (để output ổn định cho eval) |
| Max tokens | 512 |

---

## 5. Failure Mode Checklist

> Dùng khi debug — kiểm tra lần lượt: index → retrieval → generation

| Failure Mode | Triệu chứng | Cách kiểm tra |
|-------------|-------------|---------------|
| Index lỗi | Retrieve về docs cũ / sai version | `inspect_metadata_coverage()` trong index.py |
| Chunking tệ | Chunk cắt giữa điều khoản | `list_chunks()` và đọc text preview |
| Retrieval lỗi | Không tìm được expected source | `score_context_recall()` trong eval.py |
| Generation lỗi | Answer không grounded / bịa | `score_faithfulness()` trong eval.py |
| Token overload | Context quá dài → lost in the middle | Kiểm tra độ dài context_block |

---

## 6. Diagram (tùy chọn)

> Sơ đồ pipeline đầy đủ (Sprint 2 baseline + Sprint 3 hybrid):

```mermaid
graph LR
    A[User Query] --> B[OpenAI Embedding\ntext-embedding-3-small]
    A --> BM[BM25 Tokenize]
    B --> C[ChromaDB Cosine Search\nTop-10]
    BM --> D[BM25 Score\nTop-10]
    C --> RRF[RRF Fusion\ndense×0.6 + sparse×0.4]
    D --> RRF
    RRF --> G[Top-3 Select]
    G --> H[Build Context Block\n[N] source | section | score]
    H --> I[Grounded Prompt\nEvidence-only + Abstain rule]
    I --> J[gpt-4o-mini\ntemp=0, max_tokens=512]
    J --> K[Answer + Citation]
```
