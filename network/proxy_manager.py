"""
Proxy Manager — Load, rotate, health-check, blacklist proxy pool.

Mode:
  off     : tidak pakai proxy
  single  : satu proxy tetap (dari PROXY_URL)
  rotate  : giliran dari daftar di PROXY_LIST_PATH
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_HEALTHCHECK_TIMEOUT = 6  # detik


class ProxyManager:
    """
    Thread-safe proxy manager dengan rotation, blacklist, dan health-check.
    """

    def __init__(
        self,
        mode: str = "off",
        proxy_url: Optional[str] = None,
        list_path: str = "data/proxies.txt",
        timeout: int = 12,
        cooldown_seconds: int = 1200,
        healthcheck_url: str = "https://query1.finance.yahoo.com",
        rotate_on_error: bool = True,
        fallback_direct: bool = True,
    ):
        self.mode = mode.lower()
        self.proxy_url = proxy_url or ""
        self.list_path = list_path
        self.timeout = timeout
        self.cooldown_seconds = cooldown_seconds
        self.healthcheck_url = healthcheck_url
        self.rotate_on_error = rotate_on_error
        self.fallback_direct = fallback_direct

        self._lock = threading.Lock()
        self._proxies: List[str] = []
        self._idx: int = 0
        self._blacklist: Dict[str, float] = {}   # proxy → unix expiry
        self._stats: Dict[str, Dict] = {}        # proxy → {ok, fail, ...}
        self._consecutive_failures: Dict[str, int] = {}

        self._load()

    # ─── Public API ───────────────────────────────────────────────────────────

    def get_proxy(self) -> Optional[str]:
        """Return the active proxy URL, or None if mode=off."""
        if self.mode == "off":
            return None
        if self.mode == "single":
            return self.proxy_url or None
        # rotate
        with self._lock:
            return self._current_proxy()

    def rotate(self) -> Optional[str]:
        """Force rotate to next available proxy. Return new proxy or None."""
        if self.mode != "rotate":
            return self.get_proxy()
        with self._lock:
            self._advance()
            p = self._current_proxy()
            logger.info(f"[proxy] Rotate → {_mask(p)}")
            return p

    def report_success(self, proxy: Optional[str]) -> None:
        if not proxy:
            return
        with self._lock:
            s = self._stats.setdefault(
                proxy, {"ok": 0, "fail": 0, "last_error": "", "last_ok_ts": 0.0})
            s["ok"] += 1
            s["last_ok_ts"] = time.time()
            self._consecutive_failures[proxy] = 0

    def report_failure(self, proxy: Optional[str], error: Exception) -> None:
        if not proxy:
            return
        err_str = str(error)
        is_429 = _is_429(err_str)

        with self._lock:
            s = self._stats.setdefault(
                proxy, {"ok": 0, "fail": 0, "last_error": "", "last_ok_ts": 0.0})
            s["fail"] += 1
            s["last_error"] = err_str[:200]

            consec = self._consecutive_failures.get(proxy, 0) + 1
            self._consecutive_failures[proxy] = consec

            # Blacklist jika >= 2 consecutive failures, atau 429
            if consec >= 2 or is_429:
                cooldown = self.cooldown_seconds * (2 if is_429 else 1)
                self._blacklist[proxy] = time.time() + cooldown
                logger.warning(
                    f"[proxy] Blacklist {_mask(proxy)} "
                    f"cooldown={cooldown}s reason={'429' if is_429 else 'consecutive_fail'}"
                )
                self._log_event(
                    "proxy_blacklist", proxy, reason="HTTP_429" if is_429 else "CONSECUTIVE_FAIL")

            if self.rotate_on_error:
                self._advance()
                new_p = self._current_proxy()
                if new_p and new_p != proxy:
                    self._log_event("proxy_rotate", proxy, new_p,
                                    reason="HTTP_429" if is_429 else "ERROR")

    def health_check(self, proxy: str) -> bool:
        """Return True if proxy can reach healthcheck_url within timeout."""
        try:
            import requests as _req
            resp = _req.get(
                self.healthcheck_url,
                proxies=_build_proxies(proxy),
                timeout=_HEALTHCHECK_TIMEOUT,
            )
            return resp.status_code < 500
        except Exception:
            return False

    def status(self) -> Dict:
        with self._lock:
            active = self._current_proxy()
            bl_count = sum(
                1 for exp in self._blacklist.values() if exp > time.time()
            )
            return {
                "mode": self.mode,
                "active_proxy": _mask(active) if active else None,
                "total_proxies": len(self._proxies),
                "blacklisted": bl_count,
                "stats": {
                    _mask(k): v for k, v in self._stats.items()
                },
            }

    def all_proxies(self) -> List[str]:
        with self._lock:
            return list(self._proxies)

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _load(self):
        """Load proxy list dari file dan single proxy_url."""
        if self.mode == "single" and self.proxy_url:
            self._proxies = [self.proxy_url]
            return

        if self.mode != "rotate":
            return

        if not os.path.exists(self.list_path):
            logger.warning(
                f"[proxy] List file tidak ditemukan: {self.list_path}")
            return

        loaded: List[str] = []
        with open(self.list_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    loaded.append(line)

        self._proxies = loaded
        logger.info(
            f"[proxy] Loaded {len(loaded)} proxies dari {self.list_path}")

    def _current_proxy(self) -> Optional[str]:
        """Kembalikan proxy aktif saat ini (tidak diblacklist)."""
        if not self._proxies:
            return None

        now = time.time()
        # Iterasi linear, mulai dari _idx, cari yang tidak diblacklist
        n = len(self._proxies)
        for _ in range(n):
            p = self._proxies[self._idx % n]
            exp = self._blacklist.get(p, 0)
            if exp <= now:
                return p
            self._idx += 1

        # Semua blacklist → fallback direct jika enabled
        if self.fallback_direct:
            logger.warning("[proxy] Semua proxy diblacklist, fallback direct")
            return None
        return None

    def _advance(self):
        """Maju ke proxy berikutnya."""
        if self._proxies:
            self._idx = (self._idx + 1) % len(self._proxies)

    def _log_event(self, event: str, proxy_prev: Optional[str],
                   proxy_new: Optional[str] = None, reason: str = ""):
        """Tulis structured log ke logs/proxy.jsonl."""
        try:
            import json
            os.makedirs("logs", exist_ok=True)
            entry = {
                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "event": event,
                "proxy_prev": _mask(proxy_prev),
                "proxy_new": _mask(proxy_new) if proxy_new else None,
                "reason": reason,
            }
            with open("logs/proxy.jsonl", "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _mask(proxy: Optional[str]) -> Optional[str]:
    """Sembunyikan credentials dari proxy URL untuk logging."""
    if not proxy:
        return None
    try:
        import re
        return re.sub(r"://[^@]+@", "://*:*@", proxy)
    except Exception:
        return proxy


def _is_429(error_str: str) -> bool:
    return "429" in error_str or "Too Many Requests" in error_str.lower()


def _build_proxies(proxy: str) -> Dict[str, str]:
    """Bangun dict proxies untuk requests."""
    if proxy.startswith("socks"):
        return {"http": proxy, "https": proxy}
    return {"http": proxy, "https": proxy}


# ─── Singleton ────────────────────────────────────────────────────────────────

_manager: Optional[ProxyManager] = None


def get_proxy_manager() -> ProxyManager:
    global _manager
    if _manager is None:
        try:
            from config import settings
            _manager = ProxyManager(
                mode=settings.PROXY_MODE,
                proxy_url=settings.PROXY_URL,
                list_path=settings.PROXY_LIST_PATH,
                timeout=settings.PROXY_TIMEOUT,
                cooldown_seconds=settings.PROXY_COOLDOWN_SECONDS,
                healthcheck_url=settings.PROXY_HEALTHCHECK_URL,
                rotate_on_error=settings.PROXY_ROTATE_ON_ERROR,
                fallback_direct=settings.PROXY_FALLBACK_DIRECT,
            )
        except Exception:
            _manager = ProxyManager(mode="off")
    return _manager
