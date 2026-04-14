# Single Agent vs Multi-Agent Comparison — Lab Day 09

**Nhóm:** Group-D2-2  
**Ngày:** 2026-04-14

> Số liệu Day 08 lấy từ `day08/lab/logs/grading_run.json` (10 câu grading).
> Số liệu Day 09 lấy từ `artifacts/eval_report.json` (15 test questions).
> Day 08 không track latency/confidence — ghi "not tracked" và giải thích rõ.

---

## 1. Metrics Comparison

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Delta | Ghi chú |
|--------|----------------------|---------------------|-------|---------|
| Avg confidence | not tracked | **0.514** | N/A | Day 08 không có confidence scoring |
| Avg latency (ms) | not tracked | **5,513ms** | N/A | Day 08 không đo latency |
| Abstain rate (%) | **10%** (1/10) | **6.7%** (1/15) | -3.3% | Cả hai đều abstain đúng câu "không có info" |
| Multi-hop accuracy (est.) | ~70% | ~80% | +10% | Day 09 có thêm MCP context cho cross-doc queries |
| Routing visibility | ✗ Không có | ✓ Có `route_reason` | N/A | Day 09 log rõ keyword matched |
| Worker isolation | ✗ Không thể test riêng | ✓ Test độc lập được | N/A | Mỗi worker có `run(state)` interface |
| MCP extensibility | ✗ Hard-code | ✓ 4 MCP tools | N/A | Day 09 gọi `search_kb`, `check_access_permission`, v.v. |
| Debug time (estimate) | ~30 phút | ~10 phút | -20 phút | Day 09 trace rõ bước nào sai |

---

## 2. Phân tích theo loại câu hỏi

### 2.1 Câu hỏi đơn giản (single-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | Cao (4/5 simple câu đúng) | Cao — avg conf 0.52-0.58 |
| Latency | không đo | ~3,000ms (retrieval only) |
| Observation | Single agent trả lời tốt câu đơn giản | Multi-agent có overhead thêm ~2000ms do LangGraph + synthesis worker |

**Kết luận:** Với câu hỏi đơn giản (1 document, 1 fact), multi-agent không cải thiện accuracy đáng kể nhưng tốn latency hơn. Single agent đủ cho use case này.

### 2.2 Câu hỏi multi-hop (cross-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy (est.) | ~60-70% (không có routing) | ~80% (policy worker + MCP) |
| Routing visible? | ✗ | ✓ route_reason cho thấy keyword matched |
| Observation | Day 08 đôi khi trả lời đúng 1 phần (retrieve từ sai document) | Day 09 có thể gọi MCP check_access_permission bổ sung khi cần cross-doc |

**Kết luận:** Multi-hop queries hưởng lợi rõ nhất từ multi-agent. Policy worker + MCP cung cấp structured analysis thay vì retrieval-only, giúp xử lý exception cases (Flash Sale, digital product, emergency access) chính xác hơn.

### 2.3 Câu hỏi cần abstain

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Abstain rate | 10% (1/10 — gq07 SLA penalty) | 6.7% (1/15 — q09 ERR-403-AUTH) |
| Hallucination cases | 0/10 trong grading run | 0/15 trong test run |
| Observation | Day 08 nói "Tài liệu hiện có không đề cập" | Day 09 nói "Không đủ thông tin"; HITL triggered trước khi trả lời |

**Kết luận:** Cả hai hệ thống đều abstain đúng khi không có info. Day 09 thêm HITL layer (human_review_node) để flag risky queries trước — defensive layer tốt hơn cho production.

---

## 3. Debuggability Analysis

### Day 08 — Debug workflow
```
Khi answer sai → phải đọc toàn bộ RAG pipeline code → tìm lỗi ở:
  - indexing (chunk quality?)
  - retrieval (embedding model? top_k?)
  - generation (prompt? context window?)
Không có trace → không biết bắt đầu từ đâu.
Thời gian ước tính: ~30 phút cho 1 bug
```

### Day 09 — Debug workflow
```
Khi answer sai → đọc trace JSON → xem:
  1. supervisor_route + route_reason → routing đúng chưa?
  2. retrieved_chunks + scores → retrieval có lấy đúng document không?
  3. mcp_tools_used → MCP có được gọi không? Output là gì?
  4. policy_result → LLM analysis có detect đúng exceptions không?
  5. confidence → thấp → có nên trigger HITL không?
Thời gian ước tính: ~10 phút cho 1 bug
```

**Câu cụ thể đã debug trong lab:** `human_review → synthesis` edge bị bug (human_review route không qua retrieval_worker, synthesis nhận state trống). Tìm ra trong <5 phút bằng cách đọc trace — thấy `retrieved_chunks: []` khi `supervisor_route: human_review`. Fix: uncomment `builder.add_edge("human_review", "retrieval_worker")` trong `graph.py`.

---

## 4. Extensibility Analysis

| Scenario | Day 08 | Day 09 |
|---------|--------|--------|
| Thêm 1 tool/API mới | Phải sửa toàn prompt + code | Thêm MCP tool vào `mcp_server.py` + route rule |
| Thêm 1 domain mới | Phải retrain/re-prompt | Thêm 1 worker mới + register trong graph |
| Thay đổi retrieval strategy | Sửa trực tiếp trong pipeline | Sửa `retrieval.py` độc lập, không ảnh hưởng policy/synthesis |
| A/B test một phần | Khó — phải clone toàn pipeline | Dễ — swap worker implementation |

**Nhận xét:** MCP layer trong Day 09 cho phép thêm external tools (ticket system, access control API) mà không cần sửa core orchestration. Trong Day 08, mỗi tool mới đòi hỏi thay đổi prompt và code trong cùng một file.

---

## 5. Cost & Latency Trade-off

| Scenario | Day 08 LLM calls | Day 09 LLM calls | Day 09 MCP calls |
|---------|----------------|----------------|----------------|
| Simple retrieval query | 1 | 1 (synthesis) | 0 |
| Policy query | 1 | 2 (policy LLM + synthesis) | 1-2 (search_kb + optional) |
| Cross-doc multi-hop | 1 | 2 | 2-3 |

**Nhận xét về cost-benefit:**
- Day 09 tốn thêm ~1 LLM call cho policy queries (gpt-4o-mini analysis) → chi phí tăng ~2x cho policy cases
- Nhưng đổi lại: structured exception detection, MCP tool calls, và confidence scoring
- Với avg latency 5,513ms vs không đo được ở Day 08 → acceptable cho internal helpdesk use case

---

## 6. Kết luận

**Multi-agent tốt hơn single agent ở điểm nào:**

1. **Debuggability:** Trace rõ từng bước (route_reason, worker IO log, MCP calls) → debug nhanh hơn ~3x khi so sánh workflow trên.
2. **Policy exception handling:** Policy worker + LLM analysis detect đúng edge cases (Flash Sale, digital product, emergency access) mà single-agent RAG hay miss do không có structured reasoning step.
3. **Extensibility via MCP:** Thêm tools (ticket lookup, access check) không cần sửa core — Day 08 không có abstraction layer này.

**Multi-agent kém hơn hoặc không khác biệt:**

1. **Latency cho câu đơn giản:** Simple retrieval queries (~3,000ms Day 09 vs unknown Day 08) tốn overhead không cần thiết từ LangGraph state management và supervisor routing.

**Khi nào KHÔNG nên dùng multi-agent:**

Use cases đơn giản với 1 loại query duy nhất, không có policy/exception logic, và latency là priority (VD: real-time FAQ chatbot đơn giản). Single agent với RAG đủ dùng và nhanh hơn.

**Nếu tiếp tục phát triển hệ thống:**

Thêm LLM-based routing classifier thay keyword matching để handle câu hỏi ambiguous (VD: "quy trình P1" bị route sai sang policy vì keyword "quy trình"). Thêm confidence threshold-based HITL trigger tự động (confidence < 0.4 → forward to human) thay hard-coded ERR pattern.
