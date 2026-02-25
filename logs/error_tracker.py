"""
Error Tracker — Structured logging untuk error HTTP / yfinance.

Setiap kali fetch data gagal (timeout, HTTP error, data kosong, dll.),
error tersebut dicatat di:
  1. File logs/errors.jsonl — append, rotating 10 MB, retain 7 hari
  2. Ring buffer in-memory — 500 entry terakhir untuk query cepat via API

Format setiap entry (JSON):
  {
    "time"       : "2025-01-15T09:23:47.123",
    "ticker"     : "BBCA",
    "operation"  : "yfinance.5m",   # atau "api.scan", "prescreen", dll.
    "error_type" : "TimeoutError",
    "message"    : "...",
    "retry"      : 2,
    "extra"      : {}               # data tambahan opsional
  }

Penggunaan:
    from logs.error_tracker import tracker

    tracker.track("BBCA", "yfinance.5m", exception_obj)
    tracker.track("BBCA", "yfinance.5m", "empty_data")

    recent = tracker.get_recent(50)
    stats  = tracker.get_stats()
    tracker.clear()
"""

from __future__ import annotations

import collections
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Loguru setup ─────────────────────────────────────────────────────────────────
try:
    from loguru import logger as _loguru_logger
    _HAS_LOGURU = True
except ImportError:
    _HAS_LOGURU = False

# Direktori logs root (d:\api_saham\logs\)
_LOG_DIR = Path(__file__).parent.parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_JSONL_PATH = _LOG_DIR / "errors.jsonl"
_RING_MAX = 500   # Maksimum entry in-memory


# ─── Loguru JSONL sink ─────────────────────────────────────────────────────────

def _setup_loguru_sink():
    """Tambahkan sink Loguru ke file JSONL dengan rotation."""
    if not _HAS_LOGURU:
        return
    try:
        _loguru_logger.add(
            str(_JSONL_PATH),
            rotation="10 MB",
            retention="7 days",
            serialize=True,       # Output JSON tiap baris
            level="ERROR",
            enqueue=True,         # Thread-safe async write
            backtrace=False,
            diagnose=False,
        )
    except Exception as e:
        logging.getLogger(__name__).warning(f"Loguru sink setup failed: {e}")


_setup_loguru_sink()
_std_logger = logging.getLogger(__name__)


# ─── ErrorTracker ─────────────────────────────────────────────────────────────

class ErrorTracker:
    """
    Mencatat, menyimpan, dan menganalisis error fetch/scan secara struktural.

    Thread-safe. Bisa dipakai dari multiple thread (scanner, crawler, bot).
    """

    def __init__(self, ring_max: int = _RING_MAX):
        self._lock = threading.Lock()
        self._ring: collections.deque[Dict] = collections.deque(
            maxlen=ring_max)

    # ── Public API ─────────────────────────────────────────────────────────

    def track(
        self,
        ticker: str,
        operation: str,
        error: Union[str, Exception],
        retry: int = 0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Catat satu error event.

        Args:
            ticker   : Kode saham (contoh "BBCA") atau string lain ("system")
            operation: Label operasi ("yfinance.5m", "api.scan", "prescreen")
            error    : Exception object atau pesan string
            retry    : Nomor percobaan saat error terjadi (0 = percobaan pertama)
            extra    : Data tambahan opsional
        """
        if isinstance(error, Exception):
            error_type = type(error).__name__
            message = str(error)
        else:
            error_type = "Error"
            message = str(error)

        entry: Dict[str, Any] = {
            "time": datetime.now().isoformat(timespec="milliseconds"),
            "ticker": ticker.upper().replace(".JK", "") if ticker else "",
            "operation": operation,
            "error_type": error_type,
            "message": message[:500],  # Truncate panjang
            "retry": retry,
            "extra": extra or {},
        }

        # Simpan ke ring buffer
        with self._lock:
            self._ring.append(entry)

        # Tulis ke file JSONL (append)
        self._write_jsonl(entry)

        # Loguru ERROR (juga masuk ke file loguru jika sink aktif)
        if _HAS_LOGURU:
            _loguru_logger.opt(depth=1).error(
                f"[{operation}] {ticker}: {message} (retry={retry})"
            )
        else:
            _std_logger.error(
                f"[{operation}] {ticker}: {message} (retry={retry})"
            )

    def get_recent(self, n: int = 50) -> List[Dict]:
        """
        Kembalikan N error terakhir (terbaru di akhir).

        Args:
            n: Jumlah entry (max 500)
        """
        n = min(n, _RING_MAX)
        with self._lock:
            entries = list(self._ring)
        return entries[-n:]

    def get_stats(self) -> Dict:
        """
        Statistik error:
          - total: jumlah total error dalam buffer
          - by_ticker: {ticker: count} — top 20
          - by_operation: {operation: count}
          - by_error_type: {error_type: count}
          - by_hour: {hour_str: count} — 24 jam terakhir
          - last_error_at: timestamp error terakhir
        """
        with self._lock:
            entries = list(self._ring)

        if not entries:
            return {
                "total": 0,
                "by_ticker": {},
                "by_operation": {},
                "by_error_type": {},
                "by_hour": {},
                "last_error_at": None,
            }

        by_ticker: Dict[str, int] = {}
        by_op: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        by_hour: Dict[str, int] = {}

        now = datetime.now()
        cutoff_24h = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        for e in entries:
            t = e["ticker"]
            by_ticker[t] = by_ticker.get(t, 0) + 1
            op = e["operation"]
            by_op[op] = by_op.get(op, 0) + 1
            et = e["error_type"]
            by_type[et] = by_type.get(et, 0) + 1

            # Per-jam hari ini
            ts = e.get("time", "")
            if ts >= cutoff_24h:
                hour_str = ts[:13]  # "2025-01-15T09"
                by_hour[hour_str] = by_hour.get(hour_str, 0) + 1

        # Top 20 tickers
        top_tickers = dict(
            sorted(by_ticker.items(), key=lambda x: -x[1])[:20]
        )

        return {
            "total": len(entries),
            "by_ticker": top_tickers,
            "by_operation": by_op,
            "by_error_type": by_type,
            "by_hour": dict(sorted(by_hour.items())),
            "last_error_at": entries[-1]["time"] if entries else None,
        }

    def clear(self) -> int:
        """Hapus semua error dari ring buffer (bukan dari file)."""
        with self._lock:
            n = len(self._ring)
            self._ring.clear()
        return n

    def load_from_file(self, n: int = 500) -> int:
        """
        Muat ulang ring buffer dari file JSONL saat startup.
        Berguna agar history tidak hilang setelah restart.

        Returns:
            Jumlah entry yang berhasil dimuat.
        """
        if not _JSONL_PATH.exists():
            return 0
        loaded = 0
        lines: List[Dict] = []
        try:
            with open(_JSONL_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        # Loguru serialize=True membungkus di field "record"
                        raw = json.loads(line)
                        if "record" in raw:
                            msg = raw["record"].get("message", "")
                            ts = raw["record"].get("time", {})
                            ts_str = ts.get("repr", "")[:23] if isinstance(
                                ts, dict) else str(ts)[:23]
                            entry = {
                                "time": ts_str,
                                "ticker": "",
                                "operation": "replay",
                                "error_type": "LogEntry",
                                "message": msg[:500],
                                "retry": 0,
                                "extra": {},
                            }
                        else:
                            entry = raw
                        lines.append(entry)
                    except Exception:
                        pass
        except Exception as e:
            _std_logger.debug(f"ErrorTracker load_from_file: {e}")
            return 0

        # Ambil N terakhir
        for entry in lines[-n:]:
            self._ring.append(entry)
            loaded += 1
        return loaded

    # ── Private ────────────────────────────────────────────────────────────

    def _write_jsonl(self, entry: Dict) -> None:
        """Append satu entry ke file JSONL (tidak bergantung loguru)."""
        try:
            with open(_JSONL_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            _std_logger.debug(f"ErrorTracker write JSONL failed: {e}")


# ─── Singleton ────────────────────────────────────────────────────────────────

tracker = ErrorTracker()

# Muat history dari disk saat modul pertama kali diimpor
try:
    _loaded = tracker.load_from_file(n=200)
    if _loaded:
        _std_logger.debug(f"ErrorTracker: dimuat {_loaded} entry dari disk")
except Exception:
    pass
