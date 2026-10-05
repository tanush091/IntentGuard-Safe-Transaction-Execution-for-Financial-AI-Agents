"""Clocks. Experiments use SimulatedClock so time-dependent behaviour is reproducible."""

from __future__ import annotations

import threading
import time


class SystemClock:
    def now(self) -> float:
        return time.time()


class SimulatedClock:
    def __init__(self, start: float = 1_700_000_000.0):
        self._t = start
        self._lock = threading.Lock()

    def now(self) -> float:
        with self._lock:
            return self._t

    def advance(self, seconds: float) -> float:
        if seconds < 0:
            raise ValueError("time cannot go backwards")
        with self._lock:
            self._t += seconds
            return self._t

    def advance_to(self, t: float) -> float:
        with self._lock:
            if t > self._t:
                self._t = t
            return self._t
