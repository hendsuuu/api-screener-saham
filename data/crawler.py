"""
Data Crawler — Crawl historis OHLCV untuk seluruh IDX Universe.

Dua mode operasi:
  1. Crawl historis (sekali / jarang) — ambil 5 tahun data harian + 60 hari
     intraday 5m untuk semua saham. Dijalankan via:
         python manage.py get-data

  2. Incremental update (setiap 15 menit) — hanya ambil candle terbaru sejak
     timestamp terakhir yang tersimpan. Dijalankan otomatis oleh scheduler.

Arsitektur:
  ┌─────────────────────────────────────────────────────┐
  │  DataCrawler.crawl_historical()                     │
  │    → batch yf.download() per 20 saham               │
  │    → DataStore.upsert() tiap batch                  │
  │    → progress bar + error tracking                  │
  │                                                     │
  │  DataCrawler.crawl_intraday()                       │
  │    → per-ticker yf.Ticker.history() (60d 5m)        │
  │    → DataStore.upsert() setelah tiap ticker         │
  │                                                     │
  │  DataCrawler.update_latest()                        │
  │    → load last timestamp dari store per ticker      │
  │    → fetch hanya data setelah timestamp tersebut   │
  │    → cocok untuk update 15-menit oleh scheduler    │
  └─────────────────────────────────────────────────────┘
"""

from __future__ import annotations
import warnings

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

import random

import pandas as pd
import yfinance as yf

from data.store import DataStore, get_store
from data.stock_list import IDX_UNIVERSE, get_yahoo_symbol
from network.yf_client import get_yf_client
from network.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

# Matikan noise yfinance
warnings.filterwarnings("ignore", category=FutureWarning)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("peewee").setLevel(logging.CRITICAL)


# ─── Status crawl (global, thread-safe) ───────────────────────────────────────

class _CrawlStatus:
    """Thread-safe progress tracker untuk crawl aktif."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self, total: int = 0, label: str = ""):
        with self._lock:
            self.label = label
            self.state = "idle"        # idle | running | done | error
            self.total = total
            self.done = 0
            self.success = 0
            self.failed = 0
            self.errors: List[Dict] = []
            self.started_at: Optional[str] = None
            self.finished_at: Optional[str] = None
            self.current_ticker: str = ""

    def start(self, total: int, label: str = ""):
        with self._lock:
            self.label = label
            self.state = "running"
            self.total = total
            self.done = 0
            self.success = 0
            self.failed = 0
            self.errors = []
            self.started_at = datetime.now().isoformat()
            self.finished_at = None
            self.current_ticker = ""

    def tick(self, ticker: str, ok: bool, error: Optional[str] = None):
        with self._lock:
            self.done += 1
            self.current_ticker = ticker
            if ok:
                self.success += 1
            else:
                self.failed += 1
                if error:
                    self.errors.append({
                        "ticker": ticker,
                        "error": error,
                        "time": datetime.now().isoformat(),
                    })

    def finish(self):
        with self._lock:
            self.state = "done"
            self.finished_at = datetime.now().isoformat()
            self.current_ticker = ""

    def to_dict(self) -> Dict:
        with self._lock:
            pct = round(self.done / self.total * 100, 1) if self.total else 0
            elapsed = None
            if self.started_at:
                start = datetime.fromisoformat(self.started_at)
                elapsed = round((datetime.now() - start).total_seconds())
            return {
                "label": self.label,
                "state": self.state,
                "progress_pct": pct,
                "done": self.done,
                "total": self.total,
                "success": self.success,
                "failed": self.failed,
                "current_ticker": self.current_ticker,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "elapsed_sec": elapsed,
                "recent_errors": self.errors[-10:],
            }


_status = _CrawlStatus()


# ─── Helper ────────────────────────────────────────────────────────────────────

def _yf_tickers(tickers_raw: List[str]) -> List[str]:
    """Konversi ke format Yahoo Finance (.JK)."""
    return [get_yahoo_symbol(t) for t in tickers_raw]


# Kolom OHLCV yang dipertahankan (sisanya dibuang)
_OHLCV_COLS = {"Open", "High", "Low", "Close", "Volume"}


def _clean_df(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Standarisasi DataFrame hasil yfinance 1.x.

    Perubahan yfinance 1.2.0:
      - Ticker.history() menambah kolom 'Dividends' dan 'Stock Splits'
      - yf.download() batch: xs() menghasilkan kolom alphabetical
      - Index bertz (Asia/Jakarta) — akan di-strip saat upsert ke store
    """
    if df is None or df.empty:
        return None
    df = df.copy()

    # Guard: MultiIndex seharusnya sudah di-extract di level pemanggil
    if isinstance(df.columns, pd.MultiIndex):
        # Coba flatten — ambil level yang berisi nama OHLCV
        for lvl in range(df.columns.nlevels):
            vals = set(df.columns.get_level_values(lvl))
            if vals & _OHLCV_COLS:
                df.columns = df.columns.get_level_values(lvl)
                break
        else:
            return None

    # Buang kolom non-OHLCV (Dividends, Stock Splits, Adj Close, dll.)
    extra = [c for c in df.columns if c not in _OHLCV_COLS]
    if extra:
        df = df.drop(columns=extra, errors="ignore")

    # Pastikan kolom kritis ada
    if not {"Open", "High", "Low", "Close"}.issubset(df.columns):
        return None

    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df.index = pd.to_datetime(df.index)
    df.index.name = "Datetime"
    return df if not df.empty else None


# ─── Main Crawler ──────────────────────────────────────────────────────────────

class DataCrawler:
    """
    Crawl & update data OHLCV untuk saham IDX.

    Penggunaan:
        crawler = DataCrawler()

        # Sekali: crawl historis penuh
        result = crawler.crawl_historical(IDX_UNIVERSE, period="5y")
        result = crawler.crawl_intraday(IDX_UNIVERSE, period="60d")

        # Rutin: update inkremental (15 menit oleh scheduler)
        result = crawler.update_latest(IDX_UNIVERSE, interval="5m")
    """

    def __init__(
        self,
        store: Optional[DataStore] = None,
        workers: int = 4,
        batch_size: int = 20,
        delay_seconds: float = 0.5,
    ):
        self.store = store or get_store()
        self.workers = workers
        self.batch_size = batch_size
        self.delay_seconds = delay_seconds  # kept for backward compat
        # Network / rate-limit layer
        try:
            self.yf = get_yf_client()
        except Exception:
            self.yf = None
        try:
            self.limiter = get_rate_limiter()
        except Exception:
            self.limiter = None

    # ─── Crawl historis harian ─────────────────────────────────────────────

    def crawl_historical(
        self,
        universe: Optional[List[str]] = None,
        period: str = "5y",
        interval: str = "1d",
        workers: Optional[int] = None,
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """
        Download data historis untuk semua saham via yf.download() batch.

        Args:
            universe   : List kode saham (IDX_UNIVERSE jika None)
            period     : Periode historis ("1y", "2y", "5y", dll.)
            interval   : Interval OHLCV ("1d", "1h")
            workers    : Override jumlah thread (default self.workers)
            progress_cb: Callback(done, total, ticker) untuk CLI progress bar

        Returns:
            {"success": int, "failed": int, "errors": List[str]}
        """
        tickers_raw = universe or IDX_UNIVERSE
        n_workers = workers or self.workers

        logger.info(
            f"[Crawler] Mulai crawl historis {len(tickers_raw)} saham "
            f"(period={period}, interval={interval})"
        )
        _status.start(total=len(tickers_raw),
                      label=f"historical-{interval}-{period}")

        # Opsional: acak urutan ticker agar pola request tidak terdeteksi
        try:
            from config import settings as _s
            _shuffle = getattr(_s, 'CRAWL_SHUFFLE_TICKERS', True)
        except Exception:
            _shuffle = True
        if _shuffle:
            combined = list(zip(tickers_raw, _yf_tickers(tickers_raw)))
            random.shuffle(combined)
            if combined:
                tickers_raw, yf_tickers_shuffled = zip(*combined)
                tickers_raw = list(tickers_raw)
                yf_tickers_list = list(yf_tickers_shuffled)
            else:
                yf_tickers_list = _yf_tickers(tickers_raw)
        else:
            yf_tickers_list = _yf_tickers(tickers_raw)

        # Bagi menjadi batch
        yf_tickers = yf_tickers_list
        batches: List[Tuple[List[str], List[str]]] = []
        for i in range(0, len(tickers_raw), self.batch_size):
            raw_batch = tickers_raw[i:i + self.batch_size]
            yf_batch = yf_tickers[i:i + self.batch_size]
            batches.append((raw_batch, yf_batch))

        all_errors: List[str] = []
        total_success = 0
        total_failed = 0
        processed = 0

        # Fast-fail detection: jika 1 batch gagal karena timeout/network
        # error, YF kemungkinan memblokir IP VPS atau semua proxy mati.
        # Fallback per-ticker di-skip agar crawl tidak macet berjam-jam.
        _consec_net_fail = 0
        _NET_FAIL_THRESHOLD = 1
        _ip_blocked = False

        for raw_batch, yf_batch in batches:
            batch_label = ", ".join(raw_batch[:3]) + (
                f" +{len(raw_batch)-3}" if len(raw_batch) > 3 else ""
            )
            logger.debug(f"[Crawler] Batch: {batch_label}")

            batch_net_error: Optional[str] = None
            try:
                # yfinance 1.2.0: TIDAK pakai group_by; MultiIndex sekarang
                # (Price, Ticker) — level 0 = tipe harga, level 1 = ticker
                if self.yf is not None:
                    raw = self.yf.download(
                        yf_batch,
                        period=period,
                        interval=interval,
                        auto_adjust=True,
                        progress=False,
                    )
                else:
                    raw = yf.download(
                        tickers=yf_batch,
                        period=period,
                        interval=interval,
                        auto_adjust=True,
                        progress=False,
                    )
            except Exception as e:
                batch_net_error = str(e)
                logger.warning(f"[Crawler] Batch download error: {e}")
                raw = None  # Fallback ke per-ticker di bawah

            batch_ok = (
                raw is not None
                and not raw.empty
                and isinstance(raw.columns, pd.MultiIndex)
            )

            if batch_ok:
                # Batch berhasil → reset counter
                _consec_net_fail = 0
                _ip_blocked = False

            if batch_ok and len(yf_batch) > 1:
                # yfinance 1.2.0 batch: level 1 berisi nama ticker
                tickers_in_raw = set(raw.columns.get_level_values(1))
                for raw_ticker, yf_ticker in zip(raw_batch, yf_batch):
                    try:
                        if yf_ticker not in tickers_in_raw:
                            raise KeyError(
                                f"{yf_ticker} tidak ada di batch result")
                        # xs() mengekstrak semua kolom untuk satu ticker
                        df = raw.xs(yf_ticker, axis=1, level=1).copy()
                        df = _clean_df(df)
                        if df is not None and not df.empty:
                            rows = self.store.upsert(raw_ticker, interval, df)
                            _status.tick(raw_ticker, ok=True)
                            total_success += 1
                            logger.debug(
                                f"[Crawler] {raw_ticker}: +{rows} baris")
                        else:
                            _status.tick(raw_ticker, ok=False,
                                         error="empty_after_clean")
                            total_failed += 1
                    except Exception as te:
                        err_msg = str(te)
                        _status.tick(raw_ticker, ok=False, error=err_msg)
                        all_errors.append(f"{raw_ticker}: {err_msg}")
                        total_failed += 1

            elif batch_ok and len(yf_batch) == 1:
                # Single ticker dari batch download
                raw_ticker = raw_batch[0]
                yf_ticker = yf_batch[0]
                try:
                    # Single ticker download tidak punya level 1 — flatten
                    if raw.columns.nlevels > 1:
                        df = raw.xs(yf_ticker, axis=1, level=1).copy()
                    else:
                        df = raw.copy()
                    df = _clean_df(df)
                    if df is not None and not df.empty:
                        rows = self.store.upsert(raw_ticker, interval, df)
                        _status.tick(raw_ticker, ok=True)
                        total_success += 1
                        logger.debug(f"[Crawler] {raw_ticker}: +{rows} baris")
                    else:
                        _status.tick(raw_ticker, ok=False, error="empty")
                        total_failed += 1
                except Exception as te:
                    _status.tick(raw_ticker, ok=False, error=str(te))
                    total_failed += 1

            else:
                # Batch download gagal atau kosong
                # Deteksi network error (timeout/connection) vs empty data
                _NET_ERR_KWDS = ("timeout", "connection", "ssl", "remote",
                                 "eof", "socket", "reset", "refused")
                _is_net_error = batch_net_error is not None and any(
                    kw in batch_net_error.lower() for kw in _NET_ERR_KWDS
                )
                # Mode rotate + batch silent-empty (proxy mati, tidak raise) →
                # tetap hitung sebagai network fail agar fast-fail cepat
                _proxy_mode = "off"
                try:
                    from config import settings as _s
                    _proxy_mode = getattr(_s, "PROXY_MODE", "off")
                except Exception:
                    pass
                if not _is_net_error and raw is None and _proxy_mode == "rotate":
                    _is_net_error = True

                if _is_net_error:
                    _consec_net_fail += 1
                    if _consec_net_fail >= _NET_FAIL_THRESHOLD:
                        _ip_blocked = True

                _block_msg = (
                    "IP_BLOCKED: Yahoo Finance memblokir IP ini / semua proxy mati. "
                    "Set PROXY_MODE=off untuk coba direct, atau ganti PROXY_URL."
                )

                if _ip_blocked:
                    # Skip fallback per-ticker agar crawl tidak macet berjam-jam
                    for raw_ticker, _ in zip(raw_batch, yf_batch):
                        _status.tick(raw_ticker, ok=False, error=_block_msg)
                        total_failed += 1
                    if _block_msg not in all_errors:
                        all_errors.append(_block_msg)
                        logger.critical(
                            "\n[Crawler] ⚠️  IP VPS DIBLOKIR / SEMUA PROXY MATI ⚠️\n"
                            "  Crawl dihentikan untuk menghindari loop berjam-jam.\n"
                            "  Opsi solusi (di file .env VPS):\n"
                            "    1. Coba direct: PROXY_MODE=off\n"
                            "    2. Proxy tunggal: PROXY_MODE=single + PROXY_URL=...\n"
                            "    3. Filter proxy: python manage.py proxy health\n"
                        )
                else:
                    # Fallback per-ticker — dengan deteksi consecutive failure
                    # agar bisa break out cepat jika semua proxy mati.
                    # NOTE: yf_client.history() swallow exception → return None
                    # sehingga error string selalu "empty_data". Kita hitung
                    # consecutive failure (apapun errornya) sebagai signal.
                    _consec_ticker_fail = 0
                    _TICKER_FAIL_THRESHOLD = 3  # 3 ticker gagal berturut → stop
                    for raw_ticker, yf_ticker in zip(raw_batch, yf_batch):
                        if _ip_blocked:
                            _status.tick(raw_ticker, ok=False,
                                         error=_block_msg)
                            total_failed += 1
                            continue
                        ok, err = self._fetch_single(
                            raw_ticker, yf_ticker, period=period, interval=interval)
                        _status.tick(raw_ticker, ok=ok, error=err)
                        if ok:
                            total_success += 1
                            _consec_ticker_fail = 0   # reset saat ada yang sukses
                        else:
                            total_failed += 1
                            if err:
                                all_errors.append(f"{raw_ticker}: {err}")
                            _consec_ticker_fail += 1
                            if _consec_ticker_fail >= _TICKER_FAIL_THRESHOLD:
                                _ip_blocked = True
                                _consec_net_fail += 1
                                logger.warning(
                                    f"[Crawler] {_consec_ticker_fail} ticker berturut "
                                    f"gagal di fallback → fast-fail sisa batch"
                                )

            processed += len(raw_batch)
            if progress_cb:
                progress_cb(processed, len(tickers_raw), batch_label)

            # Rate limiter: adaptive delay; fallback ke self.delay_seconds
            if self.limiter is not None:
                self.limiter.wait_sync()
            else:
                time.sleep(self.delay_seconds)

        _status.finish()
        result = {
            "success": total_success,
            "failed": total_failed,
            "total": len(tickers_raw),
            "errors": all_errors[:50],  # trim panjang
        }
        logger.info(
            f"[Crawler] Selesai historis: {total_success} OK / {total_failed} gagal"
        )
        return result

    # ─── Crawl intraday ────────────────────────────────────────────────────

    def crawl_intraday(
        self,
        universe: Optional[List[str]] = None,
        period: str = "60d",
        interval: str = "5m",
        workers: Optional[int] = None,
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """
        Download data intraday (5m / 15m / 1h) untuk semua saham.

        yfinance membatasi:
          5m  → max 60 hari
          15m → max 60 hari
          1h  → max 730 hari

        Catatan: batch yf.download tidak stabil untuk interval pendek,
        sehingga di sini digunakan Ticker.history() secara paralel.

        Args:
            universe: List kode saham
            period  : Periode ("5d", "30d", "60d")
            interval: "5m", "15m", "1h"
            workers : Thread pool size

        Returns:
            {"success": int, "failed": int, "errors": [...]}
        """
        tickers_raw = universe or IDX_UNIVERSE
        n_workers = workers or self.workers

        logger.info(
            f"[Crawler] Crawl intraday {len(tickers_raw)} saham "
            f"(period={period}, interval={interval}, workers={n_workers})"
        )
        _status.start(
            total=len(tickers_raw),
            label=f"intraday-{interval}-{period}"
        )

        all_errors: List[str] = []
        total_success = 0
        total_failed = 0

        def _task(idx_raw: Tuple[int, str, str]) -> Tuple[str, bool, Optional[str]]:
            idx, raw_ticker, yf_ticker = idx_raw
            ok, err = self._fetch_single(
                raw_ticker, yf_ticker, period=period, interval=interval)
            return raw_ticker, ok, err

        yf_tickers_list = _yf_tickers(tickers_raw)
        tasks = list(enumerate(zip(tickers_raw, yf_tickers_list)))
        tasks = [(i, r, y) for i, (r, y) in tasks]

        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            for fut in as_completed(
                [pool.submit(_task, t) for t in tasks]
            ):
                try:
                    raw_ticker, ok, err = fut.result(timeout=60)
                    _status.tick(raw_ticker, ok=ok, error=err)
                    if ok:
                        total_success += 1
                    else:
                        total_failed += 1
                        if err:
                            all_errors.append(f"{raw_ticker}: {err}")
                    if progress_cb:
                        progress_cb(
                            total_success + total_failed,
                            len(tickers_raw),
                            raw_ticker
                        )
                except Exception as fe:
                    total_failed += 1
                    logger.debug(f"[Crawler] Future error: {fe}")

        _status.finish()
        result = {
            "success": total_success,
            "failed": total_failed,
            "total": len(tickers_raw),
            "errors": all_errors[:50],
        }
        logger.info(
            f"[Crawler] Selesai intraday: {total_success} OK / {total_failed} gagal"
        )
        return result

    # ─── Incremental update ────────────────────────────────────────────────

    def update_latest(
        self,
        universe: Optional[List[str]] = None,
        interval: str = "5m",
        max_gap_minutes: int = 60,
        workers: Optional[int] = None,
    ) -> Dict:
        """
        Update inkremental: hanya ambil candle baru sejak timestamp terakhir.

        Cocok untuk dijalankan setiap 15 menit oleh scheduler.
        Ticker yang belum punya data di store akan di-skip (jika belum crawl).

        Args:
            universe       : List ticker (IDX_UNIVERSE jika None)
            interval       : "5m" (default)
            max_gap_minutes: Jika gap > nilai ini, fetch lebih banyak (fallback "5d")
            workers        : Thread pool size

        Returns:
            {"updated": int, "skipped": int, "failed": int, "new_rows": int}
        """
        tickers_raw = universe or IDX_UNIVERSE
        # lebih agresif untuk update kecil
        n_workers = workers or max(self.workers, 8)

        logger.debug(
            f"[Crawler] Update inkremental {len(tickers_raw)} saham ({interval})"
        )

        updated = 0
        skipped = 0
        failed = 0
        new_rows_total = 0
        errors: List[str] = []

        def _update_one(raw_ticker: str) -> Tuple[str, str, int, Optional[str]]:
            """
            Returns: (ticker, status, new_rows, error_msg)
            status: "updated" | "skipped" | "failed"
            """
            yf_ticker = get_yahoo_symbol(raw_ticker)

            # Cek apakah ada data di store
            existing = self.store.load(raw_ticker, interval, days=7)
            if existing is None or existing.empty:
                # Belum ada data → fetch 5 hari terakhir
                period_to_fetch = "5d"
            else:
                # Ada data: hitung gap sejak candle terakhir
                last_ts = existing.index.max()
                gap = datetime.utcnow() - last_ts.to_pydatetime().replace(tzinfo=None)
                gap_minutes = gap.total_seconds() / 60

                if gap_minutes < 5:
                    # Data sudah fresh (<5 menit), skip
                    return raw_ticker, "skipped", 0, None

                if gap_minutes > max_gap_minutes:
                    period_to_fetch = "5d"
                else:
                    period_to_fetch = "1d"  # fetch 1 hari sudah cukup

            # Fetch
            ok, err = self._fetch_single(
                raw_ticker, yf_ticker, period=period_to_fetch, interval=interval)

            if not ok:
                return raw_ticker, "failed", 0, err

            # Hitung baris baru
            new_data = self.store.load(raw_ticker, interval, days=2)
            new_rows = 0
            if existing is not None and new_data is not None:
                new_rows = max(0, len(new_data) - len(existing))
            elif new_data is not None:
                new_rows = len(new_data)

            return raw_ticker, "updated", new_rows, None

        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futs = {pool.submit(_update_one, t): t for t in tickers_raw}
            for fut in as_completed(futs):
                try:
                    _, status, new_rows, err = fut.result(timeout=45)
                    if status == "updated":
                        updated += 1
                        new_rows_total += new_rows
                    elif status == "skipped":
                        skipped += 1
                    else:
                        failed += 1
                        if err:
                            errors.append(err)
                except Exception as fe:
                    failed += 1
                    logger.debug(f"[Crawler] Update future error: {fe}")

        result = {
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
            "new_rows": new_rows_total,
            "interval": interval,
            "errors": errors[:20],
        }
        logger.info(
            f"[Crawler] Update selesai: {updated} diperbarui, "
            f"{skipped} skip, {failed} gagal, +{new_rows_total} baris"
        )
        return result

    # ─── Internal helpers ──────────────────────────────────────────────────

    def _fetch_single(
        self,
        raw_ticker: str,
        yf_ticker: str,
        period: str,
        interval: str,
        retries: int = 3,
    ) -> Tuple[bool, Optional[str]]:
        """
        Fetch satu saham dengan retry, simpan ke store.

        Returns:
            (ok: bool, error_message: Optional[str])
        """
        try:
            # YFClient menangani retry + proxy + rate limiter secara internal
            if self.yf is not None:
                df = self.yf.history(
                    yf_ticker, period=period, interval=interval,
                    auto_adjust=True)
            else:
                # Fallback tanpa YFClient
                last_err: Optional[str] = None
                for attempt in range(1, retries + 1):
                    try:
                        stock = yf.Ticker(yf_ticker)
                        df = stock.history(
                            period=period, interval=interval,
                            auto_adjust=True)
                        if df is not None and not df.empty:
                            break
                        if attempt < retries:
                            time.sleep(1.0 * attempt)
                    except Exception as ex:
                        last_err = str(ex)
                        if attempt < retries:
                            time.sleep(1.5 * attempt)
                        df = None
                else:
                    # Log ke error tracker jika tersedia
                    try:
                        from logs.error_tracker import tracker
                        tracker.track(
                            raw_ticker,
                            f"yfinance.{interval}",
                            last_err or "unknown")
                    except Exception:
                        pass
                    return False, last_err

            if df is None or df.empty:
                return False, "empty_data"

            df = _clean_df(df)
            if df is None:
                return False, "empty_after_clean"

            self.store.upsert(raw_ticker, interval, df)
            return True, None

        except Exception as e:
            err_msg = str(e)
            logger.debug(f"[Crawler] {raw_ticker}: {err_msg}")
            # Log ke error tracker jika tersedia
            try:
                from logs.error_tracker import tracker
                tracker.track(raw_ticker, f"yfinance.{interval}", err_msg)
            except Exception:
                pass
            return False, err_msg


# ─── Progress summary ──────────────────────────────────────────────────────────

def get_crawl_status() -> Dict:
    """Kembalikan status crawl saat ini (thread-safe)."""
    return _status.to_dict()


# ─── Singleton ────────────────────────────────────────────────────────────────

_crawler: Optional[DataCrawler] = None


def get_crawler() -> DataCrawler:
    """Return singleton DataCrawler dengan settings dari config."""
    global _crawler
    if _crawler is None:
        try:
            from config import settings
            _crawler = DataCrawler(
                workers=settings.CRAWL_WORKERS,
                batch_size=settings.CRAWL_BATCH_SIZE,
                delay_seconds=settings.CRAWL_DELAY_SECONDS,
            )
        except Exception:
            _crawler = DataCrawler()
    return _crawler
