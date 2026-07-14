from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_MEMORY_PATH = Path("data/memory/user_memory.json")


class UserMemoryStore:
    def __init__(self, path: Path | str = DEFAULT_MEMORY_PATH):
        self.path = Path(path)

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return self._empty()
        base = self._empty()
        base.update(data if isinstance(data, dict) else {})
        base.setdefault("portfolio", [])
        base.setdefault("alerts", [])
        base.setdefault("preferences", {})
        return base

    def save(self, data: Dict[str, Any]) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.path

    def portfolio(self) -> List[Dict[str, Any]]:
        return list(self.load().get("portfolio", []))

    def alerts(self) -> List[Dict[str, Any]]:
        return list(self.load().get("alerts", []))

    def preferences(self) -> Dict[str, Any]:
        return dict(self.load().get("preferences", {}))

    def _empty(self) -> Dict[str, Any]:
        return {"portfolio": [], "alerts": [], "preferences": {}, "updated_at": None}
