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

import json
import os
import re
from pathlib import Path
from typing import Any, Optional
import sys

WORKER_NAME = "policy_tool_worker"

_MCP_CONFIG_CACHE: Optional[dict[str, Any]] = None


def _load_mcp_config() -> dict[str, Any]:
    """
    Nạp mcp_config.json nếu có. Fallback về config rỗng để không làm vỡ flow hiện tại.
    """
    global _MCP_CONFIG_CACHE
    if _MCP_CONFIG_CACHE is not None:
        return _MCP_CONFIG_CACHE

    config_path = Path(__file__).resolve().parents[1] / "mcp_config.json"
    if not config_path.exists():
        _MCP_CONFIG_CACHE = {}
        return {}

    try:
        with config_path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
            _MCP_CONFIG_CACHE = loaded if isinstance(loaded, dict) else {}
    except Exception:
        _MCP_CONFIG_CACHE = {}
    return _MCP_CONFIG_CACHE if _MCP_CONFIG_CACHE is not None else {}


def _enabled_tools(config: dict) -> set:
    """Lấy danh sách tool đang được bật trong mcp_config.json."""
    enabled = set()
    for item in config.get("tools", []):
        if item.get("enabled", True) and item.get("name"):
            enabled.add(item["name"])
    return enabled


def _extract_leave_days(task: str) -> int:
    """Parse số ngày nghỉ từ câu hỏi, fallback 1 nếu không parse được."""
    m = re.search(r"(\d+)\s*(ngay|ngày|day|days)", task.lower())
    if not m:
        return 1
    try:
        return max(1, int(m.group(1)))
    except ValueError:
        return 1


def _extract_access_level(task: str) -> int:
    """Parse access level từ câu hỏi, fallback level 1."""
    m = re.search(r"level\s*([1-3])", task.lower())
    if m:
        return int(m.group(1))
    m2 = re.search(r"muc\s*([1-3])", task.lower())
    if m2:
        return int(m2.group(1))
    return 1


def _detect_leave_type(task_lower: str) -> str:
    """Suy ra loại nghỉ phép từ câu hỏi."""
    if "om" in task_lower or "ốm" in task_lower or "sick" in task_lower:
        return "sick"
    if "thai san" in task_lower or "thai sản" in task_lower or "maternity" in task_lower:
        return "maternity"
    if "le tet" in task_lower or "lễ tết" in task_lower or "holiday" in task_lower:
        return "holiday"
    return "annual"


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

    config = _load_mcp_config()
    enabled = _enabled_tools(config)
    if enabled and tool_name not in enabled:
        return {
            "tool": tool_name,
            "input": tool_input,
            "output": None,
            "error": {
                "code": "MCP_TOOL_DISABLED",
                "reason": f"Tool '{tool_name}' đang bị tắt trong mcp_config.json",
            },
            "timestamp": datetime.now().isoformat(),
        }

    try:
        # TODO Sprint 3: Thay bằng real MCP client nếu dùng HTTP server
        from mcp_server import dispatch_tool, list_tools

        available_tools = {t.get("name") for t in list_tools()}
        if tool_name not in available_tools:
            return {
                "tool": tool_name,
                "input": tool_input,
                "output": None,
                "error": {
                    "code": "MCP_TOOL_NOT_FOUND",
                    "reason": f"Tool '{tool_name}' không có trong MCP server",
                },
                "timestamp": datetime.now().isoformat(),
            }

        result = dispatch_tool(tool_name, tool_input)
        result_error = result.get("error") if isinstance(result, dict) else None
        return {
            "tool": tool_name,
            "input": tool_input,
            "output": result,
            "error": None if not result_error else {"code": "MCP_TOOL_ERROR", "reason": str(result_error)},
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

def analyze_policy(task: str, chunks: list) -> dict:
    """
    Phân tích policy dựa trên context chunks.

    TODO Sprint 2: Implement logic này với LLM call hoặc rule-based check.

    Cần xử lý các exceptions:
    - Flash Sale → không được hoàn tiền
    - Digital product / license key / subscription → không được hoàn tiền
    - Sản phẩm đã kích hoạt → không được hoàn tiền
    - Đơn hàng trước 01/02/2026 → áp dụng policy v3 (không có trong docs)

    Returns:
        dict with: policy_applies, policy_name, exceptions_found, source, rule, explanation
    """
    task_lower = task.lower()
    context_text = " ".join([c.get("text", "") for c in chunks]).lower()

    # --- Rule-based exception detection ---
    exceptions_found = []

    # Exception 1: Flash Sale
    if "flash sale" in task_lower or "flash sale" in context_text:
        exceptions_found.append({
            "type": "flash_sale_exception",
            "rule": "Đơn hàng Flash Sale không được hoàn tiền (Điều 3, chính sách v4).",
            "source": "policy_refund_v4.txt",
        })

    # Exception 2: Digital product
    if any(kw in task_lower for kw in ["license key", "license", "subscription", "kỹ thuật số"]):
        exceptions_found.append({
            "type": "digital_product_exception",
            "rule": "Sản phẩm kỹ thuật số (license key, subscription) không được hoàn tiền (Điều 3).",
            "source": "policy_refund_v4.txt",
        })

    # Exception 3: Activated product
    if any(kw in task_lower for kw in ["đã kích hoạt", "đã đăng ký", "đã sử dụng"]):
        exceptions_found.append({
            "type": "activated_exception",
            "rule": "Sản phẩm đã kích hoạt hoặc đăng ký tài khoản không được hoàn tiền (Điều 3).",
            "source": "policy_refund_v4.txt",
        })

    # Determine policy_applies
    policy_applies = len(exceptions_found) == 0

    # Determine which policy version applies (temporal scoping)
    # Nếu task đề cập đơn hàng trước 01/02/2026 → flag lại vì docs không có policy v3
    policy_name = "refund_policy_v4"
    policy_version_note = ""
    if "31/01" in task_lower or "30/01" in task_lower or "trước 01/02" in task_lower:
        policy_version_note = "Đơn hàng đặt trước 01/02/2026 áp dụng chính sách v3 (không có trong tài liệu hiện tại)."

    # --- LLM-based analysis (primary) với rule-based làm fallback ---
    # Mặc định explanation từ rule-based, sẽ bị ghi đè nếu LLM thành công
    explanation = "Rule-based fallback (LLM unavailable or failed)."

    try:
        from openai import OpenAI

        # Tạo OpenAI client với API key từ .env
        llm_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Ghép toàn bộ text của các chunks thành một context string
        # (không lowercase vì LLM cần đọc nội dung gốc)
        context_for_llm = "\n\n".join([c.get("text", "") for c in chunks])

        response = llm_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Bạn là policy analyst. Dựa vào context được cung cấp, xác định:\n"
                        "1. Policy hoàn tiền có áp dụng không (policy_applies: true/false)\n"
                        "2. Có exceptions nào không (flash_sale, digital_product, activated)\n"
                        "Trả về JSON hợp lệ với đúng 3 key: "
                        "{\"policy_applies\": bool, \"exceptions\": [str], \"explanation\": str}"
                    )
                },
                {
                    "role": "user",
                    "content": f"Task: {task}\n\nContext:\n{context_for_llm}"
                }
            ],
            temperature=0,                              # temperature=0 để output ổn định, không sáng tạo
            response_format={"type": "json_object"},    # ép LLM trả về JSON hợp lệ
        )

        # Parse JSON string từ LLM response
        llm_result = json.loads(response.choices[0].message.content)

        # Dùng LLM's policy_applies thay cho rule-based nếu LLM trả về hợp lệ
        # LLM hiểu ngữ cảnh tốt hơn rule-based với các câu hỏi phức tạp
        policy_applies = llm_result.get("policy_applies", policy_applies)

        # Lấy explanation từ LLM (giải thích tại sao policy áp dụng hay không)
        explanation = llm_result.get("explanation", explanation)

        # Nếu LLM detect thêm exceptions mà rule-based bỏ sót → append vào danh sách
        # (rule-based chỉ check keyword đơn giản, LLM có thể hiểu ngữ nghĩa sâu hơn)
        for ex_type in llm_result.get("exceptions", []):
            already_found = any(e["type"] == ex_type for e in exceptions_found)
            if not already_found:
                exceptions_found.append({
                    "type": ex_type,
                    "rule": f"Detected by LLM: {ex_type}",
                    "source": "policy_refund_v4.txt",
                })

    except Exception as llm_error:
        # LLM call thất bại (network, API key, quota...) → giữ nguyên rule-based result
        # Không raise exception để worker vẫn hoạt động được
        explanation = f"Rule-based fallback (LLM error: {llm_error})."

    sources = list({c.get("source", "unknown") for c in chunks if c})

    return {
        "policy_applies": policy_applies,
        "policy_name": policy_name,
        "exceptions_found": exceptions_found,
        "source": sources,
        "policy_version_note": policy_version_note,
        "explanation": explanation,   # giờ chứa explanation thật từ LLM (hoặc fallback message)
    }


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
    task_lower = task.lower()
    chunks = state.get("retrieved_chunks", [])
    needs_tool = state.get("needs_tool", False)
    mcp_config = _load_mcp_config()
    mcp_defaults = mcp_config.get("defaults", {}) if isinstance(mcp_config, dict) else {}
    search_top_k = int(mcp_defaults.get("search_top_k", 3))

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
            "mcp_config_loaded": bool(mcp_config),
        },
        "output": None,
        "error": None,
    }

    try:
        policy_like_keywords = [
            "hoàn tiền",
            "refund",
            "flash sale",
            "license",
            "cấp quyền",
            "access",
            "level",
            "nghỉ phép",
            "leave",
            "đi muộn",
            "late",
        ]
        should_consult_tools = needs_tool or any(kw in task_lower for kw in policy_like_keywords)

        # Step 1: Nếu chưa có chunks, gọi MCP search_kb
        if not chunks and should_consult_tools:
            mcp_result = _call_mcp_tool("search_kb", {"query": task, "top_k": search_top_k})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP search_kb")

            if mcp_result.get("output") and mcp_result["output"].get("chunks"):
                chunks = mcp_result["output"]["chunks"]
                state["retrieved_chunks"] = chunks

        # Step 2: Phân tích policy
        policy_result = analyze_policy(task, chunks)
        state["policy_result"] = policy_result

        # Step 3: Nếu cần thêm info từ MCP (e.g., ticket status), gọi get_ticket_info
        if should_consult_tools and any(kw in task_lower for kw in ["ticket", "p1", "jira"]):
            mcp_result = _call_mcp_tool("get_ticket_info", {"ticket_id": "P1-LATEST"})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP get_ticket_info")

        # Step 4: Leave policy process via MCP
        if should_consult_tools and any(kw in task_lower for kw in ["nghỉ", "nghi", "leave"]):
            leave_days = _extract_leave_days(task)
            leave_type = _detect_leave_type(task_lower)
            mcp_result = _call_mcp_tool(
                "get_leave_process",
                {
                    "leave_days": leave_days,
                    "leave_type": leave_type,
                    "is_emergency": any(kw in task_lower for kw in ["khẩn cấp", "emergency"]),
                },
            )
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP get_leave_process")
            if mcp_result.get("output"):
                state["policy_result"]["leave_process"] = mcp_result["output"]

        # Step 5: Access control check via MCP
        if should_consult_tools and any(kw in task_lower for kw in ["access", "cấp quyền", "level"]):
            requester_role = "contractor" if "contractor" in task_lower else mcp_defaults.get("requester_role", "employee")
            mcp_result = _call_mcp_tool(
                "check_access_permission",
                {
                    "access_level": _extract_access_level(task),
                    "requester_role": requester_role,
                    "is_emergency": any(kw in task_lower for kw in ["khẩn cấp", "emergency"]),
                },
            )
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP check_access_permission")
            if mcp_result.get("output"):
                state["policy_result"]["access_check"] = mcp_result["output"]

        # Step 6: Late penalty guidance via MCP
        if should_consult_tools and any(kw in task_lower for kw in ["đi muộn", "di muon", "late"]):
            m = re.search(r"(\d+)\s*(phut|phút|min)", task_lower)
            minutes_late = int(m.group(1)) if m else 10
            mcp_result = _call_mcp_tool(
                "get_late_penalty",
                {"minutes_late": minutes_late, "late_count_this_month": 1},
            )
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP get_late_penalty")
            if mcp_result.get("output"):
                state["policy_result"]["late_penalty"] = mcp_result["output"]

        worker_io["output"] = {
            "policy_applies": policy_result["policy_applies"],
            "exceptions_count": len(policy_result.get("exceptions_found", [])),
            "mcp_calls": len(state["mcp_tools_used"]),
            "mcp_call_tools": [x.get("tool", "unknown") for x in state.get("mcp_tools_used", [])],
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
        {
            "task": "Xin nghỉ phép 3 ngày thì quy trình thế nào?",
            "retrieved_chunks": [],
            "needs_tool": True,
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
