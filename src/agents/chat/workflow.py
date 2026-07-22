from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable, Dict, List

from langgraph.graph import END, StateGraph

from src.core import LLMClient, get_llm_client

from .nodes import AgentToolExecutor, chat_agent_node, should_continue, tool_node
from .state import AgentEventCallback, AgentState


@dataclass(frozen=True)
class AgentRunResult:
    answer: str
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    pending_action: Dict[str, Any] | None = None
    error: str | None = None


class LangGraphChatAgent:
    """The single top-level chat Agent used by the web application."""

    def __init__(
        self,
        executor: AgentToolExecutor,
        system_prompt: str,
        *,
        llm_client: LLMClient | None = None,
        llm_timeout_seconds: float = 30,
    ):
        self.executor = executor
        self.system_prompt = system_prompt
        self.llm_client = llm_client or get_llm_client()
        graph = StateGraph(AgentState)
        graph.add_node(
            "chat_agent",
            partial(
                chat_agent_node,
                llm_client=self.llm_client,
                executor=self.executor,
                system_prompt=self.system_prompt,
                llm_timeout_seconds=llm_timeout_seconds,
            ),
        )
        graph.add_node("tools", partial(tool_node, executor=self.executor))
        graph.set_entry_point("chat_agent")
        graph.add_conditional_edges("chat_agent", should_continue, {"tools": "tools", "end": END})
        graph.add_edge("tools", "chat_agent")
        self.graph = graph.compile()

    async def run(
        self,
        messages: List[Dict[str, Any]],
        on_token: Callable[[str], None] | None = None,
        on_event: AgentEventCallback | None = None,
    ) -> AgentRunResult:
        if on_event is not None:
            on_event(
                "planning",
                {
                    "id": "planning",
                    "phase": "planning",
                    "status": "running",
                },
            )
        state = await self.graph.ainvoke(
            {
                "messages": list(messages),
                "pending_tool_calls": [],
                "tool_results": [],
                "pending_action": None,
                "final_answer": "",
                "iteration_count": 0,
                "error": None,
                "on_token": on_token,
                "on_event": on_event,
            }
        )
        return AgentRunResult(
            answer=state.get("final_answer") or "我没有得到可用回答。",
            tool_results=list(state.get("tool_results", [])),
            pending_action=state.get("pending_action"),
            error=state.get("error"),
        )
