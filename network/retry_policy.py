"""
Retry Policy — Backoff + jitter untuk request yfinance.

Formula backoff:
  sleep = min(2 ** attempt, 8) + uniform(0, 1)
  + 1.5 tambahan jika 429
"""

from __future__ import annotations

import random
import time
from typing import Type, Tuple


# Error yang layak di-retry
_RETRYABLE_TYPES: Tuple[Type[Exception], ...] = (
    TimeoutError,
    ConnectionError,
    OSError,
)

_RETRYABLE_MSG_FRAGMENTS = [
    "429",
    "too many requests",
    "timeout",
    "timed out",
    "connection reset",
    "connection refused",
    "remote disconnected",
    "ssl",
    "handshake",
    "read timed out",
    "503",
    "502",
    "500",
    "connect timeout",
    "chunkedencodingerror",
    "remotedisconnected",
]


class RetryPolicy:
    def __init__(
        self,
        max_retry: int = 3,
        extra_sleep_429: float = 1.5,
    ):
        self.max_retry = max_retry
        self.extra_sleep_429 = extra_sleep_429

    def should_retry(self, error: Exception) -> bool:
        """True jika error bisa diretry (network/throttle)."""
        if isinstance(error, _RETRYABLE_TYPES):
            return True
        msg = str(error).lower()
        return any(frag in msg for frag in _RETRYABLE_MSG_FRAGMENTS)

    def is_429(self, error: Exception) -> bool:
        msg = str(error).lower()
        return "429" in msg or "too many requests" in msg

    def backoff_seconds(self, attempt: int, is_429: bool = False) -> float:
        """
        Exponential backoff dengan jitter.
        attempt dimulai dari 1.
        """
        base = min(2 ** attempt, 8)
        jitter = random.uniform(0.0, 1.0)
        sleep = base + jitter
        if is_429:
            sleep += self.extra_sleep_429
        return sleep

    def wait(self, attempt: int, is_429: bool = False) -> None:
        """Blocking sleep sesuai backoff_seconds."""
        secs = self.backoff_seconds(attempt, is_429=is_429)
        time.sleep(secs)
