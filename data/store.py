"""
Data Store — Persistent OHLCV storage menggunakan Apache Parquet.

Konsep utama: APPEND & DEDUPLICATE
  Ketika data baru masuk (misal 5 hari terakhir), data lama TIDAK dihapus.
  Baris yang timestampnya sudah ada di-skip; baris baru di-append.

  Ilustrasi:
    Data lama di disk  : candle timestamp [1, 2, 3, 4, 5]
    Data baru dari API : candle timestamp    [3, 4, 5, 6, 7]
    Hasil setelah merge: candle timestamp [1, 2, 3, 4, 5, 6, 7]

Struktur penyimpanan:
  data/store/
    5m/
      BBCA.parquet
      BBRI.parquet
      ...
    1d/
      BBCA.parquet
      BBRI.parquet
      ...

Kapasitas: ~500 saham × 5m × 1 tahun ≈ 300–400 MB Parquet
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# Verify pyarrow tersedia — berikan error jelas sekali di startup
try:
    import pyarrow  # noqa: F401
    _PARQUET_ENGINE = "pyarrow"
except ImportError:
    try:
        import fastparquet  # type: ignore  # noqa: F401
        _PARQUET_ENGINE = "fastparquet"
    except ImportError:
        _PARQUET_ENGINE = None
        logging.getLogger(__name__).critical(
            "! PARQUET ENGINE TIDAK DITEMUKAN. "
            "Jalankan: pip install pyarrow   "
            "Data OHLCV tidak akan tersimpan ke disk."
        )

logger = logging.getLogger(__name__)

# ─── Lokasi root store ────────────────────────────────────────────────────────
_DEFAULT_STORE_DIR = Path(__file__).parent / "store"


class DataStore:
    """
    Menyimpan data OHLCV per-ticker per-interval dalam format Parquet.

    Penggunaan:
        store = DataStore()
        store.upsert(ticker="BBCA", interval="5m", df=df_from_api)
        history = store.load(ticker="BBCA", interval="5m", days=30)
        stats = store.stats()
    """

    # Kolom OHLCV yang wajib ada
    REQUIRED_COLS = ["Open", "High", "Low", "Close", "Volume"]

    # Interval yang didukung
    SUPPORTED_INTERVALS = {"5m", "15m", "1h", "1d"}

    def __init__(self, store_dir: Optional[Path] = None):
        self.root = Path(store_dir) if store_dir else _DEFAULT_STORE_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        # Siapkan sub-direktori per interval
        for iv in self.SUPPORTED_INTERVALS:
            (self.root / iv).mkdir(exist_ok=True)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _path(self, ticker: str, interval: str) -> Path:
        """Kembalikan path file Parquet untuk ticker + interval."""
        clean = ticker.upper().replace(".JK", "")
        return self.root / interval / f"{clean}.parquet"

    def _normalize_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Pastikan DataFrame memiliki:
        - DatetimeIndex timezone-naive (UTC → strip tz)
        - Hanya kolom OHLCV (plus kolom tambahan yang ada)
        - Tidak ada NaN pada OHLCV
        """
        df = df.copy()

        # Strip timezone agar index bisa dibandingkan antar fetch
        if hasattr(df.index, "tz") and df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)

        df.index = pd.to_datetime(df.index)
        df.index.name = "Datetime"

        # Hapus baris NaN pada kolom kritis
        existing_required = [c for c in self.REQUIRED_COLS if c in df.columns]
        df = df.dropna(subset=existing_required)

        return df.sort_index()

    # ── Public API ────────────────────────────────────────────────────────────

    def upsert(
        self,
        ticker: str,
        interval: str,
        df: pd.DataFrame,
    ) -> int:
        """
        Gabungkan `df` dengan data yang sudah ada di disk.
        Baris dengan timestamp yang sudah ada akan di-overwrite dengan
        nilai baru (berguna jika candle sedang berjalan masih berubah-ubah).

        Returns:
            Jumlah baris baru yang benar-benar ditambahkan.
        """
        if _PARQUET_ENGINE is None:
            return 0  # Tidak bisa simpan tanpa engine
        if df is None or df.empty:
            return 0
        if interval not in self.SUPPORTED_INTERVALS:
            logger.debug(f"Interval {interval!r} tidak didukung, skip store")
            return 0

        path = self._path(ticker, interval)
        new_df = self._normalize_df(df)

        # ── Load data lama ───────────────────────────────────────────────────
        if path.exists():
            try:
                old_df = pd.read_parquet(path, engine=_PARQUET_ENGINE)
                old_df.index = pd.to_datetime(old_df.index)

                rows_before = len(old_df)

                # Combine: baris baru menimpa baris lama jika timestamp sama
                combined = pd.concat([old_df, new_df])
                combined = combined[~combined.index.duplicated(keep="last")]
                combined = combined.sort_index()

                rows_added = len(combined) - rows_before
            except Exception as e:
                logger.warning(f"Gagal baca store {path}, rebuild: {e}")
                combined = new_df
                rows_added = len(combined)
        else:
            combined = new_df
            rows_added = len(combined)

        # ── Simpan kembali ke disk ───────────────────────────────────────────
        try:
            combined.to_parquet(path, engine=_PARQUET_ENGINE, compression="snappy")
            if rows_added > 0:
                logger.debug(
                    f"Store [{ticker}|{interval}]: +{rows_added} baris baru "
                    f"→ total {len(combined)}"
                )
        except Exception as e:
            logger.error(f"Gagal simpan store {path}: {e}")

        return rows_added

    def load(
        self,
        ticker: str,
        interval: str,
        days: Optional[int] = None,
        from_date: Optional[datetime] = None,
    ) -> Optional[pd.DataFrame]:
        """
        Muat data historis dari disk.

        Args:
            ticker  : Kode saham (dengan atau tanpa .JK)
            interval: "5m", "1d", dll.
            days    : Ambil N hari terakhir (None = semua)
            from_date: Ambil sejak tanggal tertentu

        Returns:
            DataFrame atau None jika tidak ada data.
        """
        path = self._path(ticker, interval)
        if not path.exists():
            return None
        try:
            df = pd.read_parquet(path, engine=_PARQUET_ENGINE)
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()

            if from_date is not None:
                df = df[df.index >= pd.Timestamp(from_date)]
            elif days is not None:
                cutoff = datetime.utcnow() - timedelta(days=days)
                df = df[df.index >= cutoff]

            return df if not df.empty else None
        except Exception as e:
            logger.error(f"Gagal baca store {path}: {e}")
            return None

    def list_tickers(self, interval: str = "5m") -> List[str]:
        """Daftar semua ticker yang punya data tersimpan."""
        iv_dir = self.root / interval
        if not iv_dir.exists():
            return []
        return sorted(p.stem for p in iv_dir.glob("*.parquet"))

    def delete_ticker(self, ticker: str, interval: Optional[str] = None) -> int:
        """
        Hapus data satu ticker.
        interval=None → hapus semua interval untuk ticker ini.
        Returns jumlah file yang dihapus.
        """
        intervals = [interval] if interval else list(self.SUPPORTED_INTERVALS)
        deleted = 0
        for iv in intervals:
            p = self._path(ticker, iv)
            if p.exists():
                p.unlink()
                deleted += 1
        return deleted

    def trim(
        self,
        ticker: str,
        interval: str,
        keep_days: int = 365,
    ) -> int:
        """
        Hapus data lebih lama dari `keep_days` hari untuk satu ticker.
        Returns jumlah baris yang dihapus.
        """
        path = self._path(ticker, interval)
        if not path.exists():
            return 0
        try:
            df = pd.read_parquet(path, engine=_PARQUET_ENGINE)
            df.index = pd.to_datetime(df.index)
            cutoff = datetime.utcnow() - timedelta(days=keep_days)
            before = len(df)
            df = df[df.index >= cutoff]
            after = len(df)
            if before != after:
                df.to_parquet(path, engine=_PARQUET_ENGINE, compression="snappy")
            return before - after
        except Exception as e:
            logger.error(f"Gagal trim store {path}: {e}")
            return 0

    def stats(self) -> Dict:
        """
        Ringkasan statistik seluruh data store.

        Returns dict dengan:
          total_tickers  : jumlah ticker unik
          total_rows     : total baris OHLCV
          disk_mb        : ukuran total di disk (MB)
          intervals       : per-interval breakdown
          oldest          : timestamp candle tertua
          newest          : timestamp candle terbaru
        """
        total_rows = 0
        total_bytes = 0
        oldest: Optional[pd.Timestamp] = None
        newest: Optional[pd.Timestamp] = None
        intervals_info: Dict[str, Dict] = {}

        for iv in self.SUPPORTED_INTERVALS:
            iv_dir = self.root / iv
            if not iv_dir.exists():
                continue
            files = list(iv_dir.glob("*.parquet"))
            iv_rows = 0
            iv_bytes = 0
            for f in files:
                iv_bytes += f.stat().st_size
                try:
                    df = pd.read_parquet(f, engine=_PARQUET_ENGINE)
                    df.index = pd.to_datetime(df.index)
                    iv_rows += len(df)
                    total_rows += len(df)
                    if not df.empty:
                        f_oldest = df.index.min()
                        f_newest = df.index.max()
                        if oldest is None or f_oldest < oldest:
                            oldest = f_oldest
                        if newest is None or f_newest > newest:
                            newest = f_newest
                except Exception:
                    pass
            total_bytes += iv_bytes
            if files:
                intervals_info[iv] = {
                    "tickers": len(files),
                    "rows": iv_rows,
                    "mb": round(iv_bytes / 1_048_576, 2),
                }

        return {
            "store_path": str(self.root),
            "total_tickers": len(set(
                p.stem
                for iv in self.SUPPORTED_INTERVALS
                for p in (self.root / iv).glob("*.parquet")
                if (self.root / iv).exists()
            )),
            "total_rows": total_rows,
            "disk_mb": round(total_bytes / 1_048_576, 2),
            "oldest": oldest.isoformat() if oldest is not None else None,
            "newest": newest.isoformat() if newest is not None else None,
            "intervals": intervals_info,
        }


# ── Singleton instance ────────────────────────────────────────────────────────
_store: Optional[DataStore] = None


def get_store() -> DataStore:
    """Kembalikan instance DataStore singleton (menggunakan DATA_STORE_PATH dari settings)."""
    global _store
    if _store is None:
        try:
            from config import settings
            _store = DataStore(settings.DATA_STORE_PATH)
        except Exception:
            # Fallback ke default path jika settings belum siap
            _store = DataStore()
    return _store
