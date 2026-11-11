"""Per-user sliding-window rate limiter."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self, max_events: int, window_s: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.max_events = max_events
        self.window_s = window_s
        self._clock = clock
        self._events: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, user_id: int) -> bool:
        """Record an event and return False when the user is over the limit."""
        now = self._clock()
        q = self._events[user_id]
        while q and now - q[0] >= self.window_s:
            q.popleft()
        if len(q) >= self.max_events:
            return False
        q.append(now)
        return True
