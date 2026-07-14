from __future__ import annotations

import json
from typing import Any, Dict, List

from src.core import get_llm_client
from src.graph.prompts import CHAT_AGENT_SYSTEM
from src.graph.state import AgentState
from src.graph.tool_registry import ToolRegistry


MAX_TOOL_ROUNDS = 8


def chat_agent_node(state: AgentState) -> Dict[str, Any]:
    messages = list(state.get("messages", []))
    if not messages:
        messages.append({"role": "user", "content": state.get("user_input", "")})

    registry = ToolRegistry()
    try:
        llm = get_llm_client()
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "system", "content": CHAT_AGENT_SYSTEM}] + messages,
            tools=registry.schemas(),
            tool_choice="auto",
            temperature=0,
        )
        message = response.choices[0].message
        assistant_message = _message_to_dict(message)
        messages.append(assistant_message)
        tool_calls = _tool_calls_to_dict(getattr(message, "tool_calls", None))
        final_answer = "" if tool_calls else (getattr(message, "content", None) or "")
        return {
            "messages": messages,
            "pending_tool_calls": tool_calls,
            "final_answer": final_answer,
            "iteration_count": state.get("iteration_count", 0) + 1,
            "error": None,
        }
    except Exception as exc:
        return {
            "messages": messages,
            "pending_tool_calls": [],
            "final_answer": f"LLM 调用失败：{exc}",
            "iteration_count": state.get("iteration_count", 0) + 1,
            "error": str(exc),
        }


def tool_node(state: AgentState) -> Dict[str, Any]:
    registry = ToolRegistry()
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


def _message_to_dict(message) -> Dict[str, Any]:
    data = {"role": "assistant", "content": getattr(message, "content", None) or ""}
    tool_calls = _tool_calls_to_dict(getattr(message, "tool_calls", None))
    if tool_calls:
        data["tool_calls"] = [
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
    return data


def _tool_calls_to_dict(tool_calls) -> List[Dict[str, Any]]:
    if not tool_calls:
        return []
    parsed = []
    for call in tool_calls:
        function = getattr(call, "function", None)
        raw_args = getattr(function, "arguments", "{}") if function is not None else "{}"
        try:
            args = json.loads(raw_args or "{}")
        except json.JSONDecodeError:
            args = {}
        parsed.append(
            {
                "id": getattr(call, "id", "") or getattr(function, "name", "tool"),
                "name": getattr(function, "name", ""),
                "arguments": args,
            }
        )
    return parsed
