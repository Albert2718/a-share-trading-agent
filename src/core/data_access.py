from __future__ import annotations

from typing import Any, Callable

from .cache import CacheManager
from .rate_limiter import RateLimiter


class DataAccessLayer:
    def __init__(
        self,
        cache: CacheManager | None = None,
        rate_limiter: RateLimiter | None = None,
    ):
        self.cache = cache or CacheManager()
        self.rate_limiter = rate_limiter or RateLimiter()

    def fetch(
        self,
        source: str,
        endpoint: str,
        params_key: str,
        ttl_seconds: int,
        min_interval: float,
        loader: Callable[[], Any],
        fallback: str = "cache",
    ) -> Any:
        namespace = f"{source}/{endpoint}"
        cached = self.cache.get(namespace, params_key, ttl_seconds)
        if cached is not None:
            return cached

        self.rate_limiter.wait(namespace, min_interval)
        try:
            value = loader()
        except Exception:
            self.rate_limiter.failure(namespace, retryable=True)
            if fallback == "cache":
                stale = self.cache.get_stale(namespace, params_key)
                if stale is not None:
                    return stale
            raise

        self.rate_limiter.success(namespace)
        self.cache.set(namespace, params_key, value)
        return value
