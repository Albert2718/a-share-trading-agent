from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Optional


class CacheManager:
    def __init__(self, root: str = "data/cache"):
        self.root = Path(root)

    def get(self, namespace: str, key: str, ttl_seconds: int) -> Optional[Any]:
        path = self._path(namespace, key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        created_at = float(payload.get("created_at", 0))
        if ttl_seconds > 0 and time.time() - created_at > ttl_seconds:
            return None
        return payload.get("value")

    def get_stale(self, namespace: str, key: str) -> Optional[Any]:
        path = self._path(namespace, key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("value")
        except Exception:
            return None

    def set(self, namespace: str, key: str, value: Any) -> None:
        path = self._path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"created_at": time.time(), "value": value}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def status(self) -> dict:
        if not self.root.exists():
            return {"root": str(self.root), "files": 0, "bytes": 0}
        files = [item for item in self.root.rglob("*.json") if item.is_file()]
        return {
            "root": str(self.root),
            "files": len(files),
            "bytes": sum(item.stat().st_size for item in files),
        }

    def clear(self, namespace: str = "") -> int:
        target = self.root / namespace if namespace else self.root
        if not target.exists():
            return 0
        count = 0
        for path in target.rglob("*.json"):
            if path.is_file():
                path.unlink()
                count += 1
        return count

    def _path(self, namespace: str, key: str) -> Path:
        safe_namespace = re.sub(r"[^A-Za-z0-9_.-]+", "_", namespace.strip("/\\"))
        safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", key)
        if len(safe_key) > 120:
            digest = hashlib.sha1(safe_key.encode("utf-8")).hexdigest()
            safe_key = f"{safe_key[:80]}_{digest}"
        return self.root / safe_namespace / f"{safe_key}.json"
