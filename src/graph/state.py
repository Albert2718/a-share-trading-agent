from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    user_input: str
    session_id: Optional[str]
    messages: List[Dict[str, Any]]
    pending_tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    final_answer: str
    iteration_count: int
    error: Optional[str]

