"""WAF-aware request gate for the SmartPLAY poller.

Single point that serialises every outbound fetch (one request in flight)
and paces calls with a stagger plus jitter. On Alibaba anti-bot responses
(403/405/429) it records a latch on the ladder [90, 150, 240, 300] and
raises GateBackoff so the caller waits without blocking the gate; 3
latches within 30 minutes enter safe mode (1 hour, doubled cycle).
"""

from __future__ import annotations

import random
import threading
import time
from collections import deque

import requests

from poller.config import CYCLE_SECONDS, STAGGER_SECONDS

WAF_STATUSES = frozenset({403, 405, 429})
LATCH_LADDER = (90, 150, 240, 300)
LATCH_WINDOW_SECONDS = 30 * 60
SAFE_MODE_SECONDS = 60 * 60


class GateBackoff(Exception):
    """Raised by Gate.get on a latch status; caller should wait `seconds`."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        super().__init__(f"WAF latch: back off for {seconds:g}s")


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
        """Fetch url, pacing calls; record the status and raise on latches.

        Calls on_status itself so the fetcher never has to remember. On a
        latch status the latch is recorded first, then GateBackoff(seconds)
        is raised instead of sleeping inline.
        """
        with self._lock:
            if self._last_request_at is not None:
                remaining = self._stagger - (self._clock() - self._last_request_at)
                if remaining > 0:
                    self._sleep(remaining + self._jitter())
            response = self._session.get(url)
            self._last_request_at = self._clock()
            backoff = self._record_status(response.status_code)
            if backoff > 0:
                raise GateBackoff(backoff)
            return response

    def on_status(self, status: int) -> float:
        """Return how many seconds to back off for this response status."""
        with self._lock:
            return self._record_status(status)

    def _record_status(self, status: int) -> float:
        """Update latch/safe state for a status; caller must hold the lock."""
        if status not in WAF_STATUSES:
            if status == 200 and not self.safe_mode():
                self._latches.clear()
            return 0.0
        now = self._clock()
        self._latches.append(now)
        recent = sum(1 for t in self._latches if now - t <= LATCH_WINDOW_SECONDS)
        if recent >= 3:
            self._safe_until = now + SAFE_MODE_SECONDS
        step = min(len(self._latches), len(LATCH_LADDER)) - 1
        return float(LATCH_LADDER[step])

    @property
    def state(self) -> str:
        with self._lock:
            if self.safe_mode():
                return "safe"
            if self._safe_until is not None:
                # Safe mode expired (lazy check): the latches that caused
                # it are older than the latch window, so recover to "ok".
                self._safe_until = None
                self._latches.clear()
            if self._latches:
                return "latch"
            return "ok"

    @property
    def target_cycle_seconds(self) -> int:
        """Cycle cadence for the main loop: doubled while in safe mode."""
        return CYCLE_SECONDS * 2 if self.safe_mode() else CYCLE_SECONDS

    def safe_mode(self) -> bool:
        return self._safe_until is not None and self._clock() < self._safe_until
