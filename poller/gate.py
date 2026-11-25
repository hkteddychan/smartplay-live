"""WAF-aware request gate for the SmartPLAY poller.

Single point that serialises every outbound fetch (one request in flight)
and paces calls with a stagger plus jitter. On Alibaba anti-bot responses
(403/405/429) it backs off on a latch ladder and enters safe mode after
3 latches within 30 minutes.
"""

from __future__ import annotations

import random
import threading
import time
from collections import deque

import requests

from poller.config import STAGGER_SECONDS

WAF_STATUSES = frozenset({403, 405, 429})
LATCH_LADDER = (90, 150, 240, 300)
LATCH_WINDOW_SECONDS = 30 * 60
SAFE_MODE_SECONDS = 60 * 60


class Gate:
    """Serialise and pace outbound fetches; track WAF latch/safe state."""

    def __init__(
        self,
        session: requests.Session,
        sleep=time.sleep,
        clock=time.monotonic,
        stagger: float = STAGGER_SECONDS,
        jitter=None,
    ) -> None:
        self._session = session
        self._sleep = sleep
        self._clock = clock
        self._stagger = stagger
        self._jitter = jitter if jitter is not None else (lambda: random.uniform(0, 2))
        self._lock = threading.Lock()
        self._last_request_at: float | None = None
        self._latches: deque[float] = deque(maxlen=10)
        self._safe_until: float | None = None

    def get(self, url: str) -> requests.Response:
        """Fetch url, sleeping first if the previous request was too recent."""
        with self._lock:
            if self._last_request_at is not None:
                remaining = self._stagger - (self._clock() - self._last_request_at)
                if remaining > 0:
                    self._sleep(remaining + self._jitter())
            response = self._session.get(url)
            self._last_request_at = self._clock()
            return response

    def on_status(self, status: int) -> float:
        """Return how many seconds to sleep for this response status."""
        if status not in WAF_STATUSES:
            return 0.0
        with self._lock:
            now = self._clock()
            self._latches.append(now)
            recent = sum(1 for t in self._latches if now - t <= LATCH_WINDOW_SECONDS)
            if recent >= 3:
                self._safe_until = now + SAFE_MODE_SECONDS
            step = min(len(self._latches), len(LATCH_LADDER)) - 1
            return float(LATCH_LADDER[step])

    @property
    def state(self) -> str:
        if self.safe_mode():
            return "safe"
        if self._latches:
            return "latch"
        return "ok"

    def safe_mode(self) -> bool:
        return self._safe_until is not None and self._clock() < self._safe_until
