# System Architecture — Lab Day 09

**Nhóm:** Group-D2-2  
**Ngày:** 2026-04-14  
**Version:** 1.0

---

## 1. Tổng quan kiến trúc

**Pattern đã chọn:** Supervisor-Worker với LangGraph StateGraph

**Lý do chọn pattern này (thay vì single agent):**

Day 08 dùng single-agent RAG pipeline: một hàm vừa retrieve, vừa kiểm tra policy, vừa tổng hợp answer. Khi pipeline trả lời sai, không rõ lỗi ở bước nào. Day 09 tách thành Supervisor điều phối + Workers chuyên biệt để:
1. **Trace rõ ràng:** Mỗi bước được log với route_reason, worker IO, MCP calls
2. **Test độc lập:** Mỗi worker có `run(state)` interface, test được mà không cần chạy toàn graph
3. **Extensible qua MCP:** Tool mới chỉ cần thêm vào mcp_server.py, không sửa core

---

## 2. Sơ đồ Pipeline

```
User Request (task)
        │
        ▼
┌─────────────────────────────────┐
│          SUPERVISOR             │
│   (graph.py: supervisor_node)   │
│                                 │
│  Keyword matching (priority):   │
│  1. ERR-xxx → human_review      │
│  2. policy/access → policy_tool │
│  3. SLA/ticket → retrieval      │
│  4. default → retrieval         │
│                                 │
│  Sets: supervisor_route         │
│        route_reason             │
│        needs_tool               │
│        risk_high                │
└──────────────┬──────────────────┘
               │
         [route_decision]
               │
    ┌──────────┼──────────────┐
    │          │              │
    ▼          ▼              ▼
┌───────┐ ┌────────┐  ┌──────────────┐
│HUMAN  │ │RETRIEVAL│  │POLICY TOOL  │
│REVIEW │ │WORKER  │  │WORKER       │
│       │ │        │  │             │
│ HITL  │ │ChromaDB│  │MCP: search_kb│
│trigger│ │OpenAI  │  │MCP: check_  │
│       │ │embed   │  │  access_perm │
└───┬───┘ └───┬────┘  │MCP: get_    │
    │         │       │  ticket_info│
    │  (after │       │LLM: gpt-4o- │
    │  review)│       │  mini policy│
    │         │       │  analysis   │
    └────►────┘       └──────┬──────┘
                             │
    ┌────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│       SYNTHESIS WORKER       │
│    (workers/synthesis.py)    │
│                              │
│  - Build context from chunks │
│  - LLM: gpt-4o-mini          │
│  - Grounded answer + cite    │
│  - Confidence estimation     │
│  - Abstain if no evidence    │
└──────────────┬───────────────┘
               │
               ▼
         Final Answer
    (AgentState: final_answer,
     sources, confidence, trace)
```

---

## 3. Vai trò từng thành phần

### Supervisor (`graph.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Phân tích task, quyết định route sang worker nào, flag risk và MCP need |
| **Input** | `task` (câu hỏi từ user) |
| **Output** | `supervisor_route`, `route_reason`, `risk_high`, `needs_tool` |
| **Routing logic** | Priority keyword matching: 4 tầng ưu tiên (human_review > policy_tool > SLA/ticket > default) |
| **HITL condition** | Task chứa pattern `ERR-xxx` hoặc "error code" → trigger human_review, set risk_high=True |

### Retrieval Worker (`workers/retrieval.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Embed query bằng OpenAI, query ChromaDB, trả về top-k chunks với score |
| **Embedding model** | `text-embedding-3-small` (1536 dim) — reuse index từ Day 08 |
| **Vector DB** | ChromaDB PersistentClient, collection `rag_lab`, 29 chunks từ 5 docs |
| **Top-k** | 3 (configurable qua `RETRIEVAL_TOP_K` env var) |
| **Stateless?** | Yes — không lưu state giữa các runs |

### Policy Tool Worker (`workers/policy_tool.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Kiểm tra policy áp dụng, detect exceptions, gọi MCP tools khi cần |
| **LLM model** | `gpt-4o-mini` với `response_format={"type": "json_object"}` |
| **MCP tools gọi** | `search_kb` (khi không có chunks), `get_ticket_info` (khi có từ khóa ticket/P1), `check_access_permission` (khi có từ khóa access/level/admin) |
| **Exception cases xử lý** | Flash Sale, digital product (license key, subscription), activated product, emergency access |
| **Fallback** | Nếu LLM fail → rule-based keyword matching |

### Synthesis Worker (`workers/synthesis.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Tổng hợp final answer từ chunks + policy_result, tạo citations, estimate confidence |
| **LLM model** | `gpt-4o-mini`, temperature=0.1 (low, grounded), max_tokens=500 |
| **Grounding strategy** | System prompt: "Answer ONLY from provided context. Say 'Không đủ thông tin' if insufficient." |
| **Abstain condition** | Không có chunks hoặc chunks score thấp → confidence ≤ 0.3 → trả lời abstain |
| **Citation format** | `[1]`, `[2]`, ... từ source list của chunks |

### MCP Server (`mcp_server.py`)

| Tool | Input | Output |
|------|-------|--------|
| `search_kb` | `query: str`, `top_k: int` | `chunks[]`, `sources[]`, `total_found` |
| `get_ticket_info` | `ticket_id: str` | ticket details (priority, status, assignee, notifications_sent) |
| `check_access_permission` | `access_level: int`, `requester_role: str`, `is_emergency: bool` | `can_grant`, `required_approvers`, `emergency_override`, `notes` |
| `create_ticket` | `priority: str`, `title: str`, `description: str` | `ticket_id`, `url`, `created_at` (mock) |

---

## 4. Shared State Schema (AgentState)

| Field | Type | Mô tả | Ai đọc/ghi |
|-------|------|-------|-----------|
| `task` | str | Câu hỏi đầu vào | User → supervisor đọc |
| `supervisor_route` | str | Worker được chọn (`retrieval_worker`/`policy_tool_worker`/`human_review`) | supervisor ghi |
| `route_reason` | str | Lý do route + MCP decision | supervisor ghi |
| `risk_high` | bool | Flag câu hỏi rủi ro cao | supervisor ghi, policy_tool đọc |
| `needs_tool` | bool | Cần gọi MCP không | supervisor ghi, policy_tool đọc |
| `hitl_triggered` | bool | Đã qua human review chưa | human_review ghi |
| `retrieved_chunks` | list | Evidence chunks từ ChromaDB | retrieval/policy_tool ghi, synthesis đọc |
| `retrieved_sources` | list | Source file names | retrieval/policy_tool ghi |
| `policy_result` | dict | Kết quả phân tích policy (LLM) | policy_tool ghi, synthesis đọc |
| `mcp_tools_used` | list | Danh sách MCP calls với input/output/timestamp | policy_tool ghi |
| `final_answer` | str | Câu trả lời cuối | synthesis ghi |
| `sources` | list | Sources được cite trong answer | synthesis ghi |
| `confidence` | float | Mức tin cậy 0.0-1.0 | synthesis ghi |
| `history` | list | Log các bước đã qua | tất cả workers ghi |
| `workers_called` | list | Thứ tự workers đã chạy | tất cả workers ghi |
| `latency_ms` | int | Tổng thời gian xử lý | run_graph() ghi |
| `run_id` | str | ID unique của run | make_initial_state() ghi |

---

## 5. Lý do chọn Supervisor-Worker so với Single Agent (Day 08)

| Tiêu chí | Single Agent (Day 08) | Supervisor-Worker (Day 09) |
|----------|----------------------|--------------------------|
| Debug khi sai | Đọc toàn pipeline code, ~30 phút | Xem trace JSON, ~10 phút |
| Thêm capability mới | Phải sửa toàn prompt | Thêm MCP tool hoặc worker mới |
| Routing visibility | Không có | Có `route_reason` + MCP decision log |
| Worker isolation | Không thể test riêng | Test `python workers/retrieval.py` độc lập |
| Policy exception handling | Trong prompt chung | Policy worker với LLM analysis riêng |
| Confidence scoring | Không có | Synthesis tính từ chunk scores |

**Quan sát từ thực tế lab:**

- Policy queries được xử lý tốt hơn khi có worker riêng: LLM analysis detect đúng Flash Sale exception (q07, q12) mà retrieval-only hay miss
- human_review_node là defensive layer quan trọng: câu hỏi với unknown error code (ERR-403-AUTH) được flag trước, tránh hallucinate
- MCP layer cho phép thêm `check_access_permission` tool để trả lời access control queries chi tiết hơn (q13, q15)

---

## 6. Giới hạn và điểm cần cải tiến

1. **Keyword-based routing dễ bị false positive:** Keyword "quy trình" trong câu hỏi về SLA quy trình bị route sang `policy_tool_worker` thay vì `retrieval_worker`. LLM-based routing classifier sẽ accurate hơn.

2. **policy_tool_worker không share retrieval với retrieval path:** Khi supervisor route → `policy_tool_worker`, nó phải gọi lại MCP `search_kb` để lấy chunks. Có thể optimize bằng cách luôn chạy retrieval trước, sau đó supervisor quyết định dùng kết quả đó cho policy check hay synthesis.

3. **Human review là auto-approve trong lab mode:** Thực tế production cần interrupt_before LangGraph feature để pause thật sự và chờ human response — không phải auto-approve sau 0ms.
