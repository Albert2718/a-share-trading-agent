from __future__ import annotations

from typing import Any, Dict, List, Optional

from langgraph.graph import END, StateGraph

from src.graph.nodes import chat_agent_node, should_continue, tool_node
from src.graph.state import AgentState


def create_chat_workflow():
    workflow = StateGraph(AgentState)
    workflow.add_node("chat_agent", chat_agent_node)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("chat_agent")
    workflow.add_conditional_edges("chat_agent", should_continue, {"tools": "tools", "end": END})
    workflow.add_edge("tools", "chat_agent")
    return workflow.compile()


def run_chat_turn(
    user_input: str,
    *,
    session_id: Optional[str] = None,
    history: Optional[List[Dict[str, Any]]] = None,
) -> AgentState:
    workflow = create_chat_workflow()
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
