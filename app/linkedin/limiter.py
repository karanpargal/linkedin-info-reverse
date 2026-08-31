from __future__ import annotations

import threading
import time
from collections import deque

from app.linkedin.errors import RateLimited


class InProcessLimiter:
    """Keeps a public deployment from burning a LinkedIn session."""

    def __init__(
        self,
        max_per_minute: int = 6,
        max_per_hour: int = 40,
        max_concurrent: int = 1,
    ) -> None:
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour
        self._minute: deque[float] = deque()
        self._hour: deque[float] = deque()
        self._lock = threading.Lock()
        self._busy = threading.Semaphore(max_concurrent)

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            while self._minute and self._minute[0] < now - 60:
                self._minute.popleft()
            while self._hour and self._hour[0] < now - 3600:
                self._hour.popleft()
            if len(self._minute) >= self.max_per_minute:
                raise RateLimited("Too many profile requests this minute; wait and retry")
            if len(self._hour) >= self.max_per_hour:
                raise RateLimited("Hourly LinkedIn lookup cap reached; try later")
            self._minute.append(now)
            self._hour.append(now)
        if not self._busy.acquire(blocking=True, timeout=45):
            raise RateLimited("A profile fetch is already in progress")

    def release(self) -> None:
        try:
            self._busy.release()
        except ValueError:
            pass
