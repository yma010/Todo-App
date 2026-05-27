"""In-process sliding-window rate limiter.

Scope: single worker. State lives in module-level dicts, so multi-worker
deployments will under-throttle by a factor of the worker count. Swap for a
Redis-backed limiter (e.g. slowapi + Redis storage) before scaling out.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, max_hits: int, window_seconds: float) -> None:
        self.max_hits = max_hits
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check_and_record(self, key: str) -> bool:
        """Atomically: prune expired hits, return False if over limit, else record and return True."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= self.max_hits:
                return False
            hits.append(now)
            return True

    def reset(self, key: str | None = None) -> None:
        """Reset one key (or all if None). Test hook."""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)
