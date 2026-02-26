"""
Adaptive Rate Limiter — Sesuaikan delay antar request secara otomatis.

- Sukses: delay turun perlahan
- Error: delay naik
- 429: delay naik agresif

Thread-safe; juga support async (await wait()).
"""

from __future__ import annotations

import asyncio
import random
import threading
import time
from collections import deque
from typing import Deque


class AdaptiveRateLimiter:
    """
    Thread + async safe adaptive rate limiter.

    Usage (sync):
        limiter = AdaptiveRateLimiter(...)
        limiter.wait_sync()
        # ... do request ...
        limiter.report_success()

    Usage (async):
        await limiter.wait()
        # ... do request ...
        limiter.report_success()
    """

    def __init__(
        self,
        base_delay: float = 0.3,
        max_delay: float = 3.0,
        success_decay: float = 0.05,
        error_boost: float = 0.35,
        extra_boost_429: float = 0.8,
        error_window: int = 30,
        jitter: float = 0.25,
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.success_decay = success_decay
        self.error_boost = error_boost
        self.extra_boost_429 = extra_boost_429
        self.error_window = error_window
        self.jitter = jitter

        self._lock = threading.Lock()
        self._delay: float = base_delay
        self._recent: Deque[bool] = deque(maxlen=error_window)   # True=success
        self._last_events: list = []   # last 10 events for status()

    # ─── Wait ─────────────────────────────────────────────────────────────────

    async def wait(self) -> None:
        """Async sleep sesuai delay + jitter."""
        secs = self._current_delay()
        if secs > 0:
            await asyncio.sleep(secs)

    def wait_sync(self) -> None:
        """Sync sleep sesuai delay + jitter."""
        secs = self._current_delay()
        if secs > 0:
            time.sleep(secs)

    # ─── Report ───────────────────────────────────────────────────────────────

    def report_success(self) -> None:
        with self._lock:
            self._recent.append(True)
            self._delay = max(
                self.base_delay, self._delay - self.success_decay)
            self._add_event("ok")

    def report_error(self, is_429: bool = False) -> None:
        with self._lock:
            self._recent.append(False)
            boost = self.error_boost + (self.extra_boost_429 if is_429 else 0)
            self._delay = min(self.max_delay, self._delay + boost)
            self._add_event("429" if is_429 else "error")

    # ─── Status ───────────────────────────────────────────────────────────────

    def status(self) -> dict:
        with self._lock:
            n = len(self._recent)
            err_rate = (n - sum(self._recent)) / n if n > 0 else 0.0
            return {
                "delay_seconds": round(self._delay, 3),
                "base_delay": self.base_delay,
                "max_delay": self.max_delay,
                "recent_error_rate": round(err_rate, 4),
                "window_size": n,
                "last_events": list(self._last_events[-5:]),
            }

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _current_delay(self) -> float:
        with self._lock:
            d = self._delay
        j = random.uniform(0, self.jitter) if self.jitter > 0 else 0
        return d + j

    def _add_event(self, kind: str):
        self._last_events.append({
            "ts": time.strftime("%H:%M:%S"),
            "kind": kind,
            "delay": round(self._delay, 3),
        })
        if len(self._last_events) > 20:
            self._last_events = self._last_events[-20:]


# ─── Singleton ────────────────────────────────────────────────────────────────

_limiter: AdaptiveRateLimiter | None = None


def get_rate_limiter() -> AdaptiveRateLimiter:
    global _limiter
    if _limiter is None:
        try:
            from config import settings
            _limiter = AdaptiveRateLimiter(
                base_delay=settings.YF_BASE_DELAY,
                max_delay=settings.YF_MAX_DELAY,
                success_decay=settings.YF_SUCCESS_DECAY,
                error_boost=settings.YF_ERROR_BOOST,
                extra_boost_429=settings.YF_429_EXTRA_BOOST,
                error_window=settings.YF_ERROR_WINDOW,
                jitter=settings.CRAWL_DELAY_JITTER,
            )
        except Exception:
            _limiter = AdaptiveRateLimiter()
    return _limiter
