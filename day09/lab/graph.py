"""
graph.py — Supervisor Orchestrator (LangGraph)
Sprint 1: AgentState, supervisor_node, route_decision, LangGraph StateGraph.

Kiến trúc:
    START → supervisor → conditional_edge
                            ├── retrieval_worker  → synthesis → END
                            ├── policy_tool_worker → synthesis → END
                            └── human_review → retrieval_worker → synthesis → END

Chạy thử:
    python graph.py
"""

import json
import os
import time
from datetime import datetime
from typing import TypedDict, Literal, Optional

from langgraph.graph import StateGraph, END, START

# ─────────────────────────────────────────────
# 1. Shared State — dữ liệu đi xuyên toàn graph
# ─────────────────────────────────────────────

class AgentState(TypedDict):
    # Input
    task: str                           # Câu hỏi đầu vào từ user

    # Supervisor decisions
    route_reason: str                   # Lý do route sang worker nào
    risk_high: bool                     # True → cần HITL hoặc human_review
    needs_tool: bool                    # True → cần gọi external tool qua MCP
    hitl_triggered: bool                # True → đã pause cho human review

    # Worker outputs
    retrieved_chunks: list              # Output từ retrieval_worker
    retrieved_sources: list             # Danh sách nguồn tài liệu
    policy_result: dict                 # Output từ policy_tool_worker
    mcp_tools_used: list                # Danh sách MCP tools đã gọi

    # Final output
    final_answer: str                   # Câu trả lời tổng hợp
    sources: list                       # Sources được cite
    confidence: float                   # Mức độ tin cậy (0.0 - 1.0)

    # Trace & history
    history: list                       # Lịch sử các bước đã qua
    workers_called: list                # Danh sách workers đã được gọi
    supervisor_route: str               # Worker được chọn bởi supervisor
    latency_ms: Optional[int]           # Thời gian xử lý (ms)
    run_id: str                         # ID của run này


def make_initial_state(task: str) -> AgentState:
    """Khởi tạo state cho một run mới."""
    return {
        "task": task,
        "route_reason": "",
        "risk_high": False,
        "needs_tool": False,
        "hitl_triggered": False,
        "retrieved_chunks": [],
        "retrieved_sources": [],
        "policy_result": {},
        "mcp_tools_used": [],
        "final_answer": "",
        "sources": [],
        "confidence": 0.0,
        "history": [],
        "workers_called": [],
        "supervisor_route": "",
        "latency_ms": None,
        "run_id": f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    }


# ─────────────────────────────────────────────
# 2. Supervisor Node — quyết định route
# ─────────────────────────────────────────────

def supervisor_node(state: AgentState) -> AgentState:
    """
    Supervisor phân tích task và quyết định:
    1. Route sang worker nào
    2. Có cần MCP tool không
    3. Có risk cao cần HITL không

    Routing logic (theo thứ tự ưu tiên):
    1. Chứa mã lỗi không rõ (ERR-XXX) → human_review
    2. Chứa policy/refund/access keywords → policy_tool_worker
    3. Chứa P1/SLA/ticket/escalation keywords → retrieval_worker
    4. Mặc định → retrieval_worker
    """
    task = state["task"].lower()
    state["history"].append(f"[supervisor] received task: {state['task'][:80]}")

    HUMAN_REVIEW_PATTERNS = ["err-", "error code", "mã lỗi không rõ"]

    POLICY_KEYWORDS = [
        "hoàn tiền", "refund", "flash sale", "license key", "license",
        "subscription", "kỹ thuật số", "digital",
        "cấp quyền", "access level", "level 3", "admin access",
        "policy", "chính sách", "quy trình", "contractor",
        "emergency", "khẩn cấp",
    ]

    ESCALATION_KEYWORDS = [
        "p1", "sla", "ticket", "escalation", "escalate",
        "2am", "trực đêm", "on-call", "oncall", "pagerduty",
        "incident", "outage",
    ]

    RISK_KEYWORDS = [
        "emergency", "khẩn cấp", "2am", "không rõ",
        "err-", "critical", "p1",
    ]

    route = "retrieval_worker"
    route_reason = "default: no specific keyword matched → retrieval"
    needs_tool = False
    risk_high = False

    # Ưu tiên 1: human_review nếu có unknown error code
    if any(pat in task for pat in HUMAN_REVIEW_PATTERNS):
        route = "human_review"
        route_reason = "unknown error code pattern detected → human review"
        risk_high = True

    # Ưu tiên 2: policy_tool nếu liên quan policy / access / refund
    elif any(kw in task for kw in POLICY_KEYWORDS):
        route = "policy_tool_worker"
        matched = [kw for kw in POLICY_KEYWORDS if kw in task]
        route_reason = f"policy/access keyword matched: {matched[:3]}"
        needs_tool = True

    # Ưu tiên 3: retrieval nếu liên quan SLA / ticket / escalation
    elif any(kw in task for kw in ESCALATION_KEYWORDS):
        route = "retrieval_worker"
        matched = [kw for kw in ESCALATION_KEYWORDS if kw in task]
        route_reason = f"SLA/ticket keyword matched: {matched[:3]}"

    # Flag risk_high độc lập với route
    if any(kw in task for kw in RISK_KEYWORDS):
        risk_high = True
        if "risk_high" not in route_reason:
            route_reason += " | risk_high=True"

    # Ghi rõ MCP decision vào route_reason (Sprint 3 DoD)
    if needs_tool:
        route_reason += " | MCP tools will be invoked by worker"
    else:
        route_reason += " | no MCP needed"

    state["supervisor_route"] = route
    state["route_reason"] = route_reason
    state["needs_tool"] = needs_tool
    state["risk_high"] = risk_high
    state["history"].append(
        f"[supervisor] route={route} | needs_tool={needs_tool} | "
        f"risk_high={risk_high} | reason={route_reason}"
    )

    return state


# ─────────────────────────────────────────────
# 3. Route Decision — conditional edge
# ─────────────────────────────────────────────

def route_decision(state: AgentState) -> Literal["retrieval_worker", "policy_tool_worker", "human_review"]:
    """
    Trả về tên worker tiếp theo dựa vào supervisor_route trong state.
    Đây là conditional edge của graph.
    """
    route = state.get("supervisor_route", "retrieval_worker")
    return route  # type: ignore


# ─────────────────────────────────────────────
# 4. Human Review Node — HITL placeholder
# ─────────────────────────────────────────────

def human_review_node(state: AgentState) -> AgentState:
    """
    HITL node: pause và chờ human approval.
    Trong lab này, implement dưới dạng placeholder (in ra warning).

    TODO Sprint 3 (optional): Implement actual HITL với interrupt_before hoặc
    breakpoint nếu dùng LangGraph.
    """
    state["hitl_triggered"] = True
    state["history"].append("[human_review] HITL triggered — awaiting human input")
    state["workers_called"].append("human_review")

    # Placeholder: tự động approve để pipeline tiếp tục
    print(f"\n⚠️  HITL TRIGGERED")
    print(f"   Task: {state['task']}")
    print(f"   Reason: {state['route_reason']}")
    print(f"   Action: Auto-approving in lab mode (set hitl_triggered=True)\n")

    # Sau khi human approve, route về retrieval để lấy evidence
    state["supervisor_route"] = "retrieval_worker"
    state["route_reason"] += " | human approved → retrieval"

    return state


# ─────────────────────────────────────────────
# 5. Import Workers
# ─────────────────────────────────────────────

from workers.retrieval import run as retrieval_run
from workers.policy_tool import run as policy_tool_run
from workers.synthesis import run as synthesis_run


def retrieval_worker_node(state: AgentState) -> AgentState:
    """Wrapper gọi retrieval worker."""
    return retrieval_run(state)


def policy_tool_worker_node(state: AgentState) -> AgentState:
    """Wrapper gọi policy/tool worker."""
    return policy_tool_run(state)


def synthesis_worker_node(state: AgentState) -> AgentState:
    """Wrapper gọi synthesis worker."""
    return synthesis_run(state)


# ─────────────────────────────────────────────
# 6. Build LangGraph StateGraph
# ─────────────────────────────────────────────

def build_graph():
    """
    Xây dựng LangGraph StateGraph với Supervisor-Worker pattern.

    Topology:
        START → supervisor
        supervisor → conditional_edge → retrieval_worker
                                      → policy_tool_worker
                                      → human_review
        human_review → retrieval_worker
        retrieval_worker → synthesis
        policy_tool_worker → synthesis
        synthesis → END
    """
    builder = StateGraph(AgentState)

    # Đăng ký nodes
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("retrieval_worker", retrieval_worker_node)
    builder.add_node("policy_tool_worker", policy_tool_worker_node)
    builder.add_node("human_review", human_review_node)
    builder.add_node("synthesis", synthesis_worker_node)

    # Entry point
    builder.add_edge(START, "supervisor")

    # Conditional edge từ supervisor → workers
    builder.add_conditional_edges(
        "supervisor",
        route_decision,
        {
            "retrieval_worker": "retrieval_worker",
            "policy_tool_worker": "policy_tool_worker",
            "human_review": "human_review",
        },
    )

    # Sau human_review → luôn vào retrieval để lấy evidence trước khi tổng hợp
    builder.add_edge("human_review", "retrieval_worker")

    # Cả hai worker đều dẫn vào synthesis
    builder.add_edge("retrieval_worker", "synthesis")
    builder.add_edge("policy_tool_worker", "synthesis")

    # Synthesis → kết thúc
    builder.add_edge("synthesis", END)

    return builder.compile()


# ─────────────────────────────────────────────
# 7. Public API
# ─────────────────────────────────────────────

_graph = build_graph()


def run_graph(task: str) -> AgentState:
    """
    Entry point: nhận câu hỏi, trả về AgentState với full trace.

    Args:
        task: Câu hỏi từ user

    Returns:
        AgentState với final_answer, trace, routing info, v.v.
    """
    state = make_initial_state(task)
    start = time.time()
    result = _graph.invoke(state)
    result["latency_ms"] = int((time.time() - start) * 1000)
    result["history"].append(f"[graph] completed in {result['latency_ms']}ms")
    return result


def save_trace(state: AgentState, output_dir: str = "./artifacts/traces") -> str:
    """Lưu trace ra file JSON."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{output_dir}/{state['run_id']}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return filename


# ─────────────────────────────────────────────
# 8. Manual Test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Day 09 Lab — Supervisor-Worker Graph")
    print("=" * 60)

    test_queries = [
        "SLA xử lý ticket P1 là bao lâu?",
        "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",
        "Cần cấp quyền Level 3 để khắc phục P1 khẩn cấp. Quy trình là gì?",
    ]

    for query in test_queries:
        print(f"\n▶ Query: {query}")
        result = run_graph(query)
        print(f"  Route   : {result['supervisor_route']}")
        print(f"  Reason  : {result['route_reason']}")
        print(f"  Workers : {result['workers_called']}")
        print(f"  Answer  : {result['final_answer'][:100]}...")
        print(f"  Confidence: {result['confidence']}")
        print(f"  Latency : {result['latency_ms']}ms")

        # Lưu trace
        trace_file = save_trace(result)
        print(f"  Trace saved → {trace_file}")

    print("\n✅ graph.py test complete. Implement TODO sections in Sprint 1 & 2.")
