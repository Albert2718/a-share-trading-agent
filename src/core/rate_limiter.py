from __future__ import annotations

import time
from collections import defaultdict
from typing import DefaultDict


class RateLimiter:
    def __init__(self):
        self._last_call: DefaultDict[str, float] = defaultdict(float)
        self._blocked_until: DefaultDict[str, float] = defaultdict(float)
        self._failures: DefaultDict[str, int] = defaultdict(int)

    def wait(self, endpoint: str, min_interval: float) -> None:
        now = time.time()
        blocked = self._blocked_until[endpoint]
        if blocked > now:
            time.sleep(blocked - now)
        elapsed = time.time() - self._last_call[endpoint]
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_call[endpoint] = time.time()

    def success(self, endpoint: str) -> None:
        self._failures[endpoint] = 0

    def failure(self, endpoint: str, retryable: bool = True) -> None:
        if not retryable:
            return
        self._failures[endpoint] += 1
        delay = min(60, 2 ** self._failures[endpoint])
        self._blocked_until[endpoint] = time.time() + delay
