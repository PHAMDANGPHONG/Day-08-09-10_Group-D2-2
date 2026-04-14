"""
workers/policy_tool.py — Policy & Tool Worker
Sprint 2+3: Kiểm tra policy dựa vào context, gọi MCP tools khi cần.

Input (từ AgentState):
    - task: câu hỏi
    - retrieved_chunks: context từ retrieval_worker
    - needs_tool: True nếu supervisor quyết định cần tool call

Output (vào AgentState):
    - policy_result: {"policy_applies", "policy_name", "exceptions_found", "source", "rule"}
    - mcp_tools_used: list of tool calls đã thực hiện
    - worker_io_log: log

Gọi độc lập để test:
    python workers/policy_tool.py
"""

import os
import sys
import json
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

WORKER_NAME = "policy_tool_worker"
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

_openai_client = None

def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


# ─────────────────────────────────────────────
# MCP Client — Sprint 3: Thay bằng real MCP call
# ─────────────────────────────────────────────

def _call_mcp_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Gọi MCP tool.

    Sprint 3 TODO: Implement bằng cách import mcp_server hoặc gọi HTTP.

    Hiện tại: Import trực tiếp từ mcp_server.py (trong-process mock).
    """
    from datetime import datetime

    try:
        # TODO Sprint 3: Thay bằng real MCP client nếu dùng HTTP server
        from mcp_server import dispatch_tool
        result = dispatch_tool(tool_name, tool_input)
        return {
            "tool": tool_name,
            "input": tool_input,
            "output": result,
            "error": None,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "tool": tool_name,
            "input": tool_input,
            "output": None,
            "error": {"code": "MCP_CALL_FAILED", "reason": str(e)},
            "timestamp": datetime.now().isoformat(),
        }


# ─────────────────────────────────────────────
# Policy Analysis Logic
# ─────────────────────────────────────────────

POLICY_SYSTEM_PROMPT = """Bạn là Policy Analyst nội bộ. Nhiệm vụ: phân tích câu hỏi và tài liệu được cung cấp để xác định policy nào áp dụng.

Quy tắc:
1. CHỈ dựa vào context được cung cấp. KHÔNG dùng kiến thức ngoài.
2. Xác định rõ các exceptions/ngoại lệ nếu có.
3. Trả về JSON hợp lệ theo đúng format sau (không thêm text ngoài JSON):

{
  "policy_applies": true hoặc false,
  "policy_name": "tên policy (ví dụ: refund_policy_v4, access_control_sop)",
  "exceptions_found": [
    {
      "type": "tên_loại_exception",
      "rule": "mô tả rule cụ thể từ tài liệu",
      "source": "tên file nguồn"
    }
  ],
  "conclusion": "kết luận ngắn gọn (1-2 câu)",
  "explanation": "giải thích chi tiết dựa trên tài liệu"
}

Lưu ý: "policy_applies": false nếu có exception ngăn chặn (ví dụ Flash Sale, digital product, đã kích hoạt).
"""


def _analyze_policy_llm(task: str, chunks: list) -> dict:
    """Phân tích policy bằng LLM với context từ chunks."""
    context_parts = []
    for i, c in enumerate(chunks, 1):
        source = c.get("source", "unknown")
        section = c.get("metadata", {}).get("section", "")
        text = c.get("text", "")
        header = f"[{i}] {source}" + (f" / {section}" if section else "")
        context_parts.append(f"{header}\n{text}")

    context = "\n\n".join(context_parts) if context_parts else "(Không có context)"

    user_message = f"""Câu hỏi: {task}

Tài liệu tham khảo:
{context}

Phân tích và trả về JSON."""

    client = _get_openai_client()
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": POLICY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)
    result["source"] = list({c.get("source", "unknown") for c in chunks if c})
    result.setdefault("exceptions_found", [])
    return result


def _analyze_policy_rules(task: str, chunks: list) -> dict:
    """Fallback: rule-based detection khi LLM không khả dụng."""
    task_lower = task.lower()
    context_text = " ".join([c.get("text", "") for c in chunks]).lower()
    exceptions_found = []

    if "flash sale" in task_lower or "flash sale" in context_text:
        exceptions_found.append({
            "type": "flash_sale_exception",
            "rule": "Đơn hàng Flash Sale không được hoàn tiền (Điều 3, chính sách v4).",
            "source": "policy/refund-v4.pdf",
        })
    if any(kw in task_lower for kw in ["license key", "license", "subscription", "kỹ thuật số"]):
        exceptions_found.append({
            "type": "digital_product_exception",
            "rule": "Sản phẩm kỹ thuật số (license key, subscription) không được hoàn tiền (Điều 3).",
            "source": "policy/refund-v4.pdf",
        })
    if any(kw in task_lower for kw in ["đã kích hoạt", "đã đăng ký", "đã sử dụng"]):
        exceptions_found.append({
            "type": "activated_exception",
            "rule": "Sản phẩm đã kích hoạt hoặc đăng ký không được hoàn tiền (Điều 3).",
            "source": "policy/refund-v4.pdf",
        })

    sources = list({c.get("source", "unknown") for c in chunks if c})
    return {
        "policy_applies": len(exceptions_found) == 0,
        "policy_name": "refund_policy_v4",
        "exceptions_found": exceptions_found,
        "source": sources,
        "conclusion": "Rule-based fallback analysis.",
        "explanation": "LLM không khả dụng — dùng rule-based detection.",
    }


def analyze_policy(task: str, chunks: list) -> dict:
    """
    Phân tích policy dựa trên context chunks.
    Ưu tiên dùng LLM; fallback sang rule-based nếu lỗi.
    """
    try:
        return _analyze_policy_llm(task, chunks)
    except Exception as e:
        print(f"  [policy_tool] LLM failed ({e}), falling back to rule-based.")
        return _analyze_policy_rules(task, chunks)


# ─────────────────────────────────────────────
# Worker Entry Point
# ─────────────────────────────────────────────

def run(state: dict) -> dict:
    """
    Worker entry point — gọi từ graph.py.

    Args:
        state: AgentState dict

    Returns:
        Updated AgentState với policy_result và mcp_tools_used
    """
    task = state.get("task", "")
    chunks = state.get("retrieved_chunks", [])
    needs_tool = state.get("needs_tool", False)
    risk_high = state.get("risk_high", False)

    state.setdefault("workers_called", [])
    state.setdefault("history", [])
    state.setdefault("mcp_tools_used", [])

    state["workers_called"].append(WORKER_NAME)

    worker_io = {
        "worker": WORKER_NAME,
        "input": {
            "task": task,
            "chunks_count": len(chunks),
            "needs_tool": needs_tool,
        },
        "output": None,
        "error": None,
    }

    try:
        # Step 1: Nếu chưa có chunks, gọi MCP search_kb
        if not chunks and needs_tool:
            mcp_result = _call_mcp_tool("search_kb", {"query": task, "top_k": 3})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP search_kb")

            if mcp_result.get("output") and mcp_result["output"].get("chunks"):
                chunks = mcp_result["output"]["chunks"]
                state["retrieved_chunks"] = chunks
                state["retrieved_sources"] = list({c.get("source", "unknown") for c in chunks if c})

        # Step 2: Phân tích policy
        policy_result = analyze_policy(task, chunks)
        state["policy_result"] = policy_result

        # Step 3: Nếu cần thêm info từ MCP (e.g., ticket status), gọi get_ticket_info
        if needs_tool and any(kw in task.lower() for kw in ["ticket", "p1", "jira"]):
            mcp_result = _call_mcp_tool("get_ticket_info", {"ticket_id": "P1-LATEST"})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP get_ticket_info")

        # Step 4: Nếu liên quan đến access/permission, gọi check_access_permission
        if needs_tool and any(kw in task.lower() for kw in ["quyền", "access", "level", "admin", "permission"]):
            access_level = 3 if "level 3" in task.lower() else 2 if "level 2" in task.lower() else 1
            is_emergency = "emergency" in task.lower() or "khẩn cấp" in task.lower() or risk_high
            mcp_result = _call_mcp_tool("check_access_permission", {
                "access_level": access_level,
                "requester_role": "contractor",
                "is_emergency": is_emergency,
            })
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP check_access_permission")

        worker_io["output"] = {
            "policy_applies": policy_result["policy_applies"],
            "exceptions_count": len(policy_result.get("exceptions_found", [])),
            "mcp_calls": len(state["mcp_tools_used"]),
        }
        state["history"].append(
            f"[{WORKER_NAME}] policy_applies={policy_result['policy_applies']}, "
            f"exceptions={len(policy_result.get('exceptions_found', []))}"
        )

    except Exception as e:
        worker_io["error"] = {"code": "POLICY_CHECK_FAILED", "reason": str(e)}
        state["policy_result"] = {"error": str(e)}
        state["history"].append(f"[{WORKER_NAME}] ERROR: {e}")

    state.setdefault("worker_io_logs", []).append(worker_io)
    return state


# ─────────────────────────────────────────────
# Test độc lập
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Policy Tool Worker — Standalone Test")
    print("=" * 50)

    test_cases = [
        {
            "task": "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",
            "retrieved_chunks": [
                {"text": "Ngoại lệ: Đơn hàng Flash Sale không được hoàn tiền.", "source": "policy_refund_v4.txt", "score": 0.9}
            ],
        },
        {
            "task": "Khách hàng muốn hoàn tiền license key đã kích hoạt.",
            "retrieved_chunks": [
                {"text": "Sản phẩm kỹ thuật số (license key, subscription) không được hoàn tiền.", "source": "policy_refund_v4.txt", "score": 0.88}
            ],
        },
        {
            "task": "Khách hàng yêu cầu hoàn tiền trong 5 ngày, sản phẩm lỗi, chưa kích hoạt.",
            "retrieved_chunks": [
                {"text": "Yêu cầu trong 7 ngày làm việc, sản phẩm lỗi nhà sản xuất, chưa dùng.", "source": "policy_refund_v4.txt", "score": 0.85}
            ],
        },
    ]

    for tc in test_cases:
        print(f"\n▶ Task: {tc['task'][:70]}...")
        result = run(tc.copy())
        pr = result.get("policy_result", {})
        print(f"  policy_applies: {pr.get('policy_applies')}")
        if pr.get("exceptions_found"):
            for ex in pr["exceptions_found"]:
                print(f"  exception: {ex['type']} — {ex['rule'][:60]}...")
        print(f"  MCP calls: {len(result.get('mcp_tools_used', []))}")

    print("\n✅ policy_tool_worker test done.")
