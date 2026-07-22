from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, TypedDict


AgentEventCallback = Callable[[str, Dict[str, Any]], None]


class AgentState(TypedDict, total=False):
    messages: List[Dict[str, Any]]
    pending_tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    pending_action: Optional[Dict[str, Any]]
    final_answer: str
    iteration_count: int
    error: Optional[str]
    on_token: Optional[Callable[[str], None]]
    on_event: Optional[AgentEventCallback]
