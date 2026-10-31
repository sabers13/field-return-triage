"""Pacing: at most N concurrent requests and M requests per minute per model.

PLAN §8 fixes the numbers for the live run (2 concurrent, 30/minute). The limits are
read from ``config/budget.toml`` by :func:`field_return_triage.llm.settings.load_budget`
and enforced by one :class:`Pacer` per model client. The clock and sleeper are
injectable so tests stay instant and deterministic.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager

__all__ = ["Pacer"]

Clock = Callable[[], float]
Sleeper = Callable[[float], None]


class Pacer:
    """A thread-safe sliding-window request pacer with a concurrency cap."""

    def __init__(
        self,
        *,
        max_concurrency: int = 2,
        requests_per_minute: int = 30,
        window_seconds: float = 60.0,
        clock: Clock = time.monotonic,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        if max_concurrency < 1:
            msg = "max_concurrency must be at least 1"
            raise ValueError(msg)
        if requests_per_minute < 1:
            msg = "requests_per_minute must be at least 1"
            raise ValueError(msg)
        if window_seconds <= 0:
            msg = "window_seconds must be greater than zero"
            raise ValueError(msg)
        self.max_concurrency = max_concurrency
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._semaphore = threading.BoundedSemaphore(max_concurrency)
        self._lock = threading.Lock()
        self._stamps: deque[float] = deque()

    @contextmanager
    def slot(self) -> Iterator[None]:
        """Hold one concurrency slot and one place in the minute window."""
        self._semaphore.acquire()
        try:
            self._reserve()
            yield
        finally:
            self._semaphore.release()

    def _reserve(self) -> None:
        """Wait until the window has room, then stamp the request atomically."""
        while True:
            with self._lock:
                now = self._clock()
                while self._stamps and now - self._stamps[0] >= self.window_seconds:
                    self._stamps.popleft()
                if len(self._stamps) < self.requests_per_minute:
                    self._stamps.append(now)
                    return
                delay = self._stamps[0] + self.window_seconds - now
            if delay > 0:
                self._sleeper(delay)
