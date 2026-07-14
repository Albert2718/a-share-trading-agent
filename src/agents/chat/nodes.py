from __future__ import annotations

import json
from typing import Any, Dict, List

from src.core import LLMClient
from src.tools.registry import ToolRegistry

from .prompts import CHAT_AGENT_SYSTEM
from .state import AgentState


MAX_TOOL_ROUNDS = 8


def chat_agent_node(state: AgentState, *, llm_client: LLMClient, registry: ToolRegistry) -> Dict[str, Any]:
    messages = list(state.get("messages", []))
    if not messages:
        messages.append({"role": "user", "content": state.get("user_input", "")})
    try:
        response = llm_client.chat_with_tools(
            [{"role": "system", "content": CHAT_AGENT_SYSTEM}] + messages,
            registry.schemas(),
            temperature=0,
        )
        assistant_message: Dict[str, Any] = {"role": "assistant", "content": response.content}
        tool_calls = [
            {"id": call.id, "name": call.name, "arguments": call.arguments}
            for call in response.tool_calls
        ]
        iteration_count = state.get("iteration_count", 0) + 1
        if tool_calls and iteration_count >= MAX_TOOL_ROUNDS:
            limit_message = "工具调用轮次已达上限，请缩小问题范围后重试。"
            messages.append({"role": "assistant", "content": limit_message})
            return {
                "messages": messages,
                "pending_tool_calls": [],
                "final_answer": limit_message,
                "iteration_count": iteration_count,
                "error": "tool round limit reached",
            }
        if tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                    },
                }
                for call in tool_calls
            ]
        messages.append(assistant_message)
        return {
            "messages": messages,
            "pending_tool_calls": tool_calls,
            "final_answer": "" if tool_calls else response.content,
            "iteration_count": iteration_count,
            "error": None,
        }
    except Exception:
        return {
            "messages": messages,
            "pending_tool_calls": [],
            "final_answer": "LLM 调用失败，请稍后重试。",
            "iteration_count": state.get("iteration_count", 0) + 1,
            "error": "llm request failed",
        }


def tool_node(state: AgentState, *, registry: ToolRegistry) -> Dict[str, Any]:
    messages = list(state.get("messages", []))
    results: List[Dict[str, Any]] = list(state.get("tool_results", []))
    for call in state.get("pending_tool_calls", []):
        name = call.get("name", "")
        arguments = call.get("arguments", {}) or {}
        result = registry.execute(name, arguments)
        results.append({"name": name, "arguments": arguments, "result": result})
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.get("id", name),
                "name": name,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            }
        )
    return {"messages": messages, "tool_results": results, "pending_tool_calls": []}


def should_continue(state: AgentState) -> str:
    if state.get("pending_tool_calls") and state.get("iteration_count", 0) < MAX_TOOL_ROUNDS:
        return "tools"
    return "end"
