from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ChatTurn:
    user_input: str
    answer: str = ""
    tool_results: List[Dict[str, Any]] = field(default_factory=list)

