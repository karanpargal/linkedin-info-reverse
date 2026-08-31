from __future__ import annotations

import threading
import time
from collections import deque

from app.linkedin.errors import RateLimited


class InProcessLimiter:
    """Keeps a public deployment from burning a LinkedIn session."""

    def __init__(self, max_per_minute: int = 12, max_concurrent: int = 1) -> None:
        self.max_per_minute = max_per_minute
        self._times: deque[float] = deque()
        self._lock = threading.Lock()
        self._busy = threading.Semaphore(max_concurrent)

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            cutoff = now - 60
            while self._times and self._times[0] < cutoff:
                self._times.popleft()
            if len(self._times) >= self.max_per_minute:
                raise RateLimited("Too many profile requests; try again shortly")
            self._times.append(now)
        if not self._busy.acquire(blocking=True, timeout=30):
            raise RateLimited("A profile fetch is already in progress")

    def release(self) -> None:
        try:
            self._busy.release()
        except ValueError:
            pass
