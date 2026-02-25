"""
Signal Cache — Persistensi sinyal ke disk (JSON) agar data tidak hilang
saat server restart atau saat bot berjalan di proses berbeda dari API server.

Konsep:
  - Setiap kali scan selesai, hasil disimpan ke `data/store/signals_YYYY-MM-DD.json`
  - File menggunakan tanggal hari ini (WIB) sebagai nama → otomatis expire esok hari
  - Bot commands (/buy, /waspada) membaca dari disk jika in-memory kosong
  - Maksimal 1 file per hari; file lama auto-dibersihkan (simpan 7 hari terakhir)

Format JSON:
  {
    "saved_at": "2025-02-25T09:20:00",
    "scan_time": "2025-02-25T09:19:45",
    "signals": [ {...ScalpSignal fields...}, ... ]
  }
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import pytz

logger = logging.getLogger(__name__)

WIB = pytz.timezone("Asia/Jakarta")

# Direktori cache (sama dengan OHLCV store agar satu tempat)
_CACHE_DIR = Path(__file__).parent / "store"
_MAX_CACHE_FILES = 7   # simpan riwayat 7 hari


def _today_wib() -> str:
    """Tanggal hari ini dalam WIB, format YYYY-MM-DD."""
    return datetime.now(WIB).strftime("%Y-%m-%d")


def _cache_path(day: Optional[str] = None) -> Path:
    """Path file cache untuk tanggal tertentu (default: hari ini)."""
    return _CACHE_DIR / f"signals_{day or _today_wib()}.json"


def save_signals(signals: list, scan_time: Optional[str] = None) -> bool:
    """
    Simpan sinyal hasil scan ke disk.

    Args:
        signals  : List[ScalpSignal] — hasil scan
        scan_time: ISO timestamp scan (default: sekarang)

    Returns:
        True jika berhasil disimpan
    """
    if not signals:
        return False

    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _cache_path()

        payload = {
            "saved_at": datetime.now(WIB).isoformat(),
            "scan_time": scan_time or datetime.now(WIB).isoformat(),
            "date": _today_wib(),
            "total": len(signals),
            "signals": [_signal_to_dict(s) for s in signals],
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        logger.info(
            f"[SignalCache] {len(signals)} sinyal disimpan → {path.name}"
        )

        # Bersihkan file lama
        _prune_old_files()
        return True

    except Exception as e:
        logger.error(f"[SignalCache] Gagal simpan sinyal: {e}")
        return False


def load_signals_today() -> List:
    """
    Muat sinyal scan terakhir hari ini dari disk.

    Returns:
        List[ScalpSignal] atau [] jika tidak ada/sudah kadaluarsa
    """
    path = _cache_path()
    if not path.exists():
        logger.debug("[SignalCache] Tidak ada file cache hari ini")
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Verifikasi tanggal (hanya ambil sinyal hari ini)
        if data.get("date") != _today_wib():
            logger.debug("[SignalCache] Cache sudah kadaluarsa (beda hari)")
            return []

        raw_signals = data.get("signals", [])
        signals = [_dict_to_signal(d) for d in raw_signals if d]
        signals = [s for s in signals if s is not None]

        logger.info(
            f"[SignalCache] Memuat {len(signals)} sinyal dari disk "
            f"(disimpan {data.get('saved_at', 'N/A')})"
        )
        return signals

    except Exception as e:
        logger.error(f"[SignalCache] Gagal baca cache: {e}")
        return []


def get_cache_info() -> dict:
    """Informasi file cache yang ada."""
    files = sorted(_CACHE_DIR.glob("signals_*.json"), reverse=True)
    info = []
    for f in files[:7]:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
            info.append({
                "file": f.name,
                "date": d.get("date"),
                "total": d.get("total", 0),
                "saved_at": d.get("saved_at"),
            })
        except Exception:
            info.append({"file": f.name, "error": "corrupt"})
    today_path = _cache_path()
    return {
        "today_file": str(today_path),
        "today_exists": today_path.exists(),
        "history": info,
    }


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _signal_to_dict(signal) -> dict:
    """ScalpSignal → JSON-serializable dict."""
    try:
        from dataclasses import asdict  # noqa
        return asdict(signal)
    except Exception as e:
        logger.debug(f"[SignalCache] asdict failed: {e}")
        # Manual fallback
        return signal.__dict__.copy()


def _dict_to_signal(d: dict):
    """JSON dict → ScalpSignal."""
    try:
        from screener.signal_generator import ScalpSignal
        # Hapus field yang mungkin tidak ada di versi lama
        valid_fields = {f.name for f in ScalpSignal.__dataclass_fields__.values()}  # type: ignore
        clean = {k: v for k, v in d.items() if k in valid_fields}
        return ScalpSignal(**clean)
    except Exception as e:
        logger.debug(f"[SignalCache] dict→signal gagal: {e}")
        return None


def _prune_old_files():
    """Hapus file cache lebih lama dari _MAX_CACHE_FILES hari."""
    try:
        files = sorted(_CACHE_DIR.glob("signals_*.json"), reverse=True)
        for old in files[_MAX_CACHE_FILES:]:
            old.unlink()
            logger.debug(f"[SignalCache] Hapus cache lama: {old.name}")
    except Exception:
        pass
