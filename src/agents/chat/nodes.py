from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Awaitable, Dict, List, Protocol

from src.core import LLMClient

from .state import AgentState


MAX_TOOL_ROUNDS = 6
MAX_TOOL_RESULT_CHARS = 16_000


class ToolExecutionLike(Protocol):
    name: str
    result: dict
    pending_action: dict | None


class AgentToolExecutor(Protocol):
    def schemas(self) -> List[Dict[str, Any]]: ...

    def execute(self, name: str, arguments: Dict[str, Any]) -> Awaitable[ToolExecutionLike]: ...


async def chat_agent_node(
    state: AgentState,
    *,
    llm_client: LLMClient,
    executor: AgentToolExecutor,
    system_prompt: str,
    llm_timeout_seconds: float,
) -> Dict[str, Any]:
    messages = list(state.get("messages", []))
    iteration_count = state.get("iteration_count", 0) + 1
    if iteration_count > 1:
        _emit_event(
            state,
            "synthesizing",
            {
                "id": "synthesizing",
                "phase": "synthesizing",
                "status": "running",
            },
        )
    try:
        on_token = state.get("on_token")
        streaming = on_token is not None and hasattr(
            llm_client, "chat_with_tools_stream"
        )
        request = (
            llm_client.chat_with_tools_stream
            if streaming
            else llm_client.chat_with_tools
        )
        request_args = (
            (
                [{"role": "system", "content": system_prompt}] + messages,
                executor.schemas(),
                on_token,
                0,
            )
            if streaming
            else (
                [{"role": "system", "content": system_prompt}] + messages,
                executor.schemas(),
                0,
            )
        )
        response = await asyncio.wait_for(
            asyncio.to_thread(request, *request_args),
            timeout=llm_timeout_seconds,
        )
        assistant_message: Dict[str, Any] = {"role": "assistant", "content": response.content}
        tool_calls = [
            {"id": call.id, "name": call.name, "arguments": call.arguments}
            for call in response.tool_calls
        ]
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
            "final_answer": "当前 LLM 服务不可用。",
            "iteration_count": iteration_count,
            "error": "llm request failed",
        }


async def tool_node(state: AgentState, *, executor: AgentToolExecutor) -> Dict[str, Any]:
    messages = list(state.get("messages", []))
    results: List[Dict[str, Any]] = list(state.get("tool_results", []))
    pending_action = state.get("pending_action")
    for call in state.get("pending_tool_calls", []):
        name = call.get("name", "")
        arguments = call.get("arguments", {}) or {}
        event_base = {
            "id": call.get("id", name),
            "tool_call_id": call.get("id", name),
            "tool_name": name,
            "arguments": arguments,
        }
        _emit_event(
            state,
            "tool_started",
            {**event_base, "phase": "tool_started", "status": "running"},
        )
        started_at = time.perf_counter()
        execution = await executor.execute(name, arguments)
        duration_ms = round((time.perf_counter() - started_at) * 1000)
        if execution.pending_action is not None and pending_action is not None:
            result = {"ok": False, "error": "only one write confirmation is allowed per turn"}
        else:
            name = execution.name
            result = execution.result
            pending_action = execution.pending_action or pending_action
        if execution.pending_action is not None:
            event_name = "awaiting_confirmation"
            result_status = "awaiting_confirmation"
        elif name == "research_submit" and result.get("ok", False):
            event_name = "background_task_created"
            result_status = "queued"
        else:
            event_name = "tool_completed"
            result_status = "completed" if result.get("ok", True) else "failed"
        tool_result = {
            "name": name,
            "arguments": arguments,
            "result": result,
            "status": result_status,
            "duration_ms": duration_ms,
        }
        results.append(tool_result)
        _emit_event(
            state,
            event_name,
            {
                **event_base,
                "phase": event_name,
                "status": result_status,
                "result": result,
                "duration_ms": duration_ms,
            },
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.get("id", name),
                "name": name,
                "content": json.dumps(result, ensure_ascii=False, default=str)[:MAX_TOOL_RESULT_CHARS],
            }
        )
    return {
        "messages": messages,
        "tool_results": results,
        "pending_action": pending_action,
        "pending_tool_calls": [],
    }


def should_continue(state: AgentState) -> str:
    if state.get("pending_tool_calls") and state.get("iteration_count", 0) < MAX_TOOL_ROUNDS:
        return "tools"
    return "end"


def _emit_event(state: AgentState, event: str, data: Dict[str, Any]) -> None:
    """Status callbacks are observational and must never break an Agent run."""
    callback = state.get("on_event")
    if callback is None:
        return
    try:
        callback(event, data)
    except Exception:
        return
