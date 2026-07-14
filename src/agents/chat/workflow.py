from __future__ import annotations

from functools import partial
from typing import Any, Dict, List, Optional

from langgraph.graph import END, StateGraph

from src.core import LLMClient, get_llm_client
from src.tools.registry import ToolRegistry

from .nodes import chat_agent_node, should_continue, tool_node
from .state import AgentState
from .tool_catalog import build_default_registry


def create_chat_workflow(
    llm_client: LLMClient | None = None,
    registry: ToolRegistry | None = None,
):
    llm = llm_client or get_llm_client()
    tools = registry or build_default_registry()
    workflow = StateGraph(AgentState)
    workflow.add_node("chat_agent", partial(chat_agent_node, llm_client=llm, registry=tools))
    workflow.add_node("tools", partial(tool_node, registry=tools))
    workflow.set_entry_point("chat_agent")
    workflow.add_conditional_edges("chat_agent", should_continue, {"tools": "tools", "end": END})
    workflow.add_edge("tools", "chat_agent")
    return workflow.compile()


def run_chat_turn(
    user_input: str,
    *,
    session_id: Optional[str] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    llm_client: LLMClient | None = None,
    registry: ToolRegistry | None = None,
) -> AgentState:
    workflow = create_chat_workflow(llm_client=llm_client, registry=registry)
    messages = list(history or [])
    messages.append({"role": "user", "content": user_input})
    return workflow.invoke(
        {
            "user_input": user_input,
            "session_id": session_id,
            "messages": messages,
            "pending_tool_calls": [],
            "tool_results": [],
            "final_answer": "",
            "iteration_count": 0,
            "error": None,
        }
    )
