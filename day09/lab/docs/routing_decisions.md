# Routing Decisions Log — Lab Day 09

**Nhóm:** Group-D2-2  
**Ngày:** 2026-04-14

> Các routing decision dưới đây được lấy trực tiếp từ trace trong `artifacts/traces/`.
> Chạy `python eval_trace.py --analyze` để xem routing distribution tổng hợp.

---

## Routing Decision #1 — SLA/Ticket Query → retrieval_worker

**Task đầu vào:**
> "SLA xử lý ticket P1 là bao lâu?"

**Worker được chọn:** `retrieval_worker`  
**Route reason (từ trace):** `SLA/ticket keyword matched: ['p1', 'sla', 'ticket'] | risk_high=True | no MCP needed`  
**MCP tools được gọi:** none  
**Workers called sequence:** `retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: "SLA xử lý ticket P1: phản hồi ban đầu 15 phút, xử lý và khắc phục 4 giờ, escalation tự động lên Senior Engineer sau 10 phút không phản hồi [1]."
- confidence: 0.52
- sources: `support/sla-p1-2026.pdf`
- Correct routing? **Yes**

**Nhận xét:** Câu hỏi về SLA facts → cần retrieval từ document chứ không cần kiểm tra policy. Routing đúng. `risk_high=True` vì task chứa "p1" (keyword risk). MCP không cần vì không có decision logic — chỉ cần tra cứu dữ liệu.

---

## Routing Decision #2 — Policy/Refund Query → policy_tool_worker + MCP

**Task đầu vào:**
> "Khách hàng có thể yêu cầu hoàn tiền trong bao nhiêu ngày?"

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `policy/access keyword matched: ['hoàn tiền'] | MCP tools will be invoked by worker`  
**MCP tools được gọi:** `search_kb` (query: câu hỏi đầu vào, top_k=3)  
**Workers called sequence:** `policy_tool_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: "Khách hàng có thể yêu cầu hoàn tiền trong vòng 7 ngày làm việc từ ngày xác nhận đơn hàng. Ngoại lệ: sản phẩm kỹ thuật số, đơn Flash Sale, sản phẩm đã kích hoạt [1][2]."
- confidence: 0.55
- sources: `policy/refund-v4.pdf`
- Correct routing? **Yes**

**Nhận xét:** Keyword "hoàn tiền" trigger policy route. Policy worker gọi MCP `search_kb` để lấy chunks (vì `retrieved_chunks` rỗng khi vào policy_tool_worker), sau đó dùng LLM phân tích. MCP call được ghi đầy đủ vào `mcp_tools_used` với input/output/timestamp.

---

## Routing Decision #3 — Unknown Error Code → human_review → retrieval_worker

**Task đầu vào:**
> "ERR-403-AUTH là lỗi gì và cách xử lý?"

**Worker được chọn:** `human_review` (sau đó tự động reroute → `retrieval_worker`)  
**Route reason (từ trace):** `unknown error code pattern detected → human review | risk_high=True | no MCP needed`  
**MCP tools được gọi:** none  
**Workers called sequence:** `human_review → retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: "Không đủ thông tin trong tài liệu nội bộ để xác định lỗi ERR-403-AUTH và cách xử lý."
- confidence: 0.30
- hitl_triggered: true
- sources: `support/helpdesk-faq.md`, `it/access-control-sop.md`
- Correct routing? **Yes** (abstain đúng — ERR-403-AUTH không có trong docs)

**Nhận xét:** Pattern `ERR-` trong task trigger human_review. Trong lab mode, HITL auto-approve → forward sang `retrieval_worker`. Retrieval trả về chunks không liên quan (score thấp ~0.37-0.40), synthesis quyết định abstain với confidence 0.30. Đây là behavior đúng — không hallucinate.

---

## Routing Decision #4 — Access Level 3 + Emergency → policy_tool_worker + 3 MCP tools

**Task đầu vào:**
> "Contractor cần Admin Access (Level 3) để khắc phục sự cố P1 đang active. Quy trình cấp quyền tạm thời như thế nào?"

**Worker được chọn:** `policy_tool_worker`  
**Route reason:** `policy/access keyword matched: ['cấp quyền', 'level 3', 'admin access'] | risk_high=True | MCP tools will be invoked by worker`  
**MCP tools được gọi:** `search_kb` + `check_access_permission` (access_level=3, is_emergency=True)  
**Workers called sequence:** `policy_tool_worker → synthesis_worker`

**Nhận xét: Đây là trường hợp routing khó nhất trong lab. Tại sao?**

Task kết hợp 3 concern: (1) policy access control Level 3, (2) emergency P1, (3) contractor role — đòi hỏi cả retrieval từ access_control_sop.md lẫn logic kiểm tra permission qua MCP. 

Supervisor phải phân biệt đây là access/policy query (không phải SLA query thuần túy) dù có cả "P1" lẫn "Level 3". Priority-2 (policy keywords `cấp quyền`, `level 3`, `admin access`) thắng Priority-3 (SLA keywords `p1`). Policy worker sau đó gọi `check_access_permission` MCP tool để lấy context về quy trình phê duyệt, cung cấp cho synthesis tạo answer đầy đủ.

---

## Tổng kết

### Routing Distribution (từ eval run với 15 test questions)

| Worker | Số câu được route | % tổng |
|--------|------------------|--------|
| retrieval_worker | 8 | 53% |
| policy_tool_worker | 6 | 40% |
| human_review | 1 | 7% |

> Lưu ý: q09 (ERR-403-AUTH) ban đầu route tới `human_review` nhưng sau đó auto-forward sang `retrieval_worker`, nên `supervisor_route` trong trace là `retrieval_worker` (route sau HITL).

### Routing Accuracy

- Câu route đúng: **14 / 15** (ước tính dựa trên kết quả)
- Câu routing có thể cải thiện: q08 ("quy trình P1") → routed `policy_tool_worker` vì keyword "quy trình", nhưng có thể route `retrieval_worker` sẽ hiệu quả hơn (đây là câu hỏi về facts, không cần policy check)
- Câu trigger HITL: **1** (q09 — unknown error code)

### Lesson Learned về Routing

1. **Keyword priority thứ tự rất quan trọng:** Khi một task chứa nhiều keyword types (VD: "P1" + "Level 3 access"), thứ tự ưu tiên `human_review > policy_tool > escalation > default` quyết định outcome. Policy keywords phải được check trước SLA keywords để tránh gửi access control queries sang retrieval_worker thuần túy.

2. **Policy route + MCP = stronger answers:** Các câu hỏi về policy (refund, access) được trả lời tốt hơn khi đi qua `policy_tool_worker` vì nó gọi cả LLM analysis và MCP tools (search_kb, check_access_permission). Retrieval-only approach bỏ qua bước exception detection và business logic.

### Route Reason Quality

Sau khi chạy 15 câu, `route_reason` trong trace rõ ràng và debug được:
- Nêu keyword nào matched: `['hoàn tiền']`, `['p1', 'sla', 'ticket']`
- Nêu risk level: `risk_high=True`
- Nêu MCP decision: `MCP tools will be invoked by worker` vs `no MCP needed`

Cải tiến nếu có thêm thời gian: thêm danh sách keywords **không** match vào route_reason để dễ debug false negatives (VD: task chứa "quy trình" → route policy, nhưng không nêu rõ "escalation keywords not matched").
