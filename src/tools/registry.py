from __future__ import annotations

import inspect
from typing import Any, Dict, Iterable, List

from .definitions import ToolDefinition


class ToolRegistry:
    def __init__(self, definitions: Iterable[ToolDefinition]):
        self._definitions = {definition.name: definition for definition in definitions}

    def schemas(self) -> List[Dict[str, Any]]:
        return [definition.schema() for definition in self._definitions.values()]

    def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        definition = self._definitions.get(name)
        if definition is None:
            return {"ok": False, "tool": name, "error": "unknown tool"}
        try:
            allowed = set(inspect.signature(definition.handler).parameters)
            clean_args = {key: value for key, value in (arguments or {}).items() if key in allowed}
            result = definition.handler(**clean_args)
            payload = dict(result) if isinstance(result, dict) else {"ok": True, "result": result}
            payload["tool"] = name
            return payload
        except Exception:
            return {"ok": False, "tool": name, "error": "tool execution failed"}
