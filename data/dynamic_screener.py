"""
Dynamic Pre-Screener — Filter saham dari IDX_UNIVERSE secara dinamis.

Alur kerja:
  1. Unduh data harian (2-5 hari terakhir) untuk seluruh IDX_UNIVERSE
     menggunakan yf.download() mode BATCH — jauh lebih cepat daripada
     mengunduh satu per satu.
  2. Terapkan 5 kriteria filter:
       (a) Harga penutupan >= min_price              (default: 100)
       (b) Volume MA5 > min_volume_ma5               (default: 10.000.000 lembar)
       (c) Nilai transaksi MA5 >= min_value_ma5      (default: 10.000.000.000 Rp)
       (d) |Perubahan harga 1 hari| >= min_price_change_pct (default: 2 %)
       (e) Volume hari ini / Volume MA5 >= 1 + vol_surge_pct (default: 1.3 ✓ = +30%)
  3. Kembalikan daftar ticker yang lolos filter, siap untuk analisis
     teknikal intraday penuh di StockScanner.

Catatan desain:
  - Semua kriteria bersifat CONFIGURABLE lewat constructor ataupun .env.
  - Kriteria (d) memakai nilai absolut (|change|) sehingga saham yang
    turun tajam pun tertangkap untuk sinyal SELL.
  - Batch download menghemat ~80 % waktu vs. download satu-satu.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from data.stock_list import IDX_UNIVERSE, get_yahoo_symbol

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Hasil pre-screen per saham
# ─────────────────────────────────────────────────────────────
@dataclass
class PreScreenResult:
    ticker: str            # tanpa .JK
    price: float           # harga penutupan terakhir
    volume_today: int      # volume hari terakhir (lembar)
    volume_ma5: float      # rata-rata volume 5 hari
    value_ma5: float       # rata-rata nilai transaksi 5 hari (Rp)
    price_change_pct: float  # perubahan harga 1 hari (%)
    vol_surge_ratio: float   # volume hari ini / volume MA5
    passed: bool           # True = lolos semua filter
    fail_reasons: List[str]  # alasan ditolak (jika passed=False)

    @property
    def vol_change_pct(self) -> float:
        """Volume surge dalam persen (mis. 1.45 → 45%)."""
        return (self.vol_surge_ratio - 1) * 100


# ─────────────────────────────────────────────────────────────
# Konfigurasi kriteria
# ─────────────────────────────────────────────────────────────
@dataclass
class ScreenerCriteria:
    """
    Kriteria pre-screening berorientasi profit untuk scalping IDX.

    Filosofi:
      - Harga 100–10.000: sweet-spot scalping IDX  tick lebih kecil,
        spread lebih wajar, volatilitas harian yang bisa dikelola.
      - Nilai transaksi Rp 5 M/hari: uang nyata beredar, bukan saham sepi.
      - Volume surge 15 %: tanda ada katalis atau smart-money masuk,
        cukup sensitif tanpa terlalu banyak noise.
      - Price change 0.5 %: tangkap pre-breakout & early-momentum SEBELUM
        saham sudah naik jauh  entry lebih baik, reward lebih besar.
    """
    # ── Rentang harga (IDX sweet-spot scalping) ──
    min_price: float = 100.0
    """Harga minimum Rp 100 — hindari penny-stock & saham sub-gocap."""

    max_price: Optional[float] = 10_000.0
    """Harga maksimum Rp 10.000 — hindari saham ultra-high-price dengan
    spread absolut besar yang memakan profit scalping."""

    # ── Likuiditas (pastikan bisa masuk & keluar cepat) ──
    min_volume_ma5: float = 3_000_000.0
    """Volume rata-rata 5 hari >= 3 juta lembar/hari.
    Lebih rendah dari versi lama agar saham mid-cap yang liquid masuk."""

    min_value_ma5: float = 5_000_000_000.0
    """Nilai transaksi rata-rata 5 hari >= Rp 5 miliar/hari.
    Filter utama likuiditas — uang yang benar-benar berputar."""

    # ── Momentum (tangkap pergerakan awal) ──
    min_price_change_pct: float = 0.5
    """|Perubahan harga 1 hari| >= 0.5 %.
    Rendah agar pre-breakout & early-mover tertangkap.
    Pakai nilai absolut  saham turun pun bisa jadi kandidat WASPADA."""

    min_vol_surge_pct: float = 15.0
    """Volume hari ini >= 15 % di atas rata-rata MA5 (ratio >= 1.15).
    Menandakan ada aktivitas tidak biasa / akumulasi diam-diam."""

    # ── EMA cross filter (konfirmasi trend intraday) ──
    require_ema_alignment: bool = False
    """Jika True: hanya lolos jika EMA9 > EMA20 (uptrend) ATAU
    EMA9 < EMA20 (downtrend). Filter ini diaktifkan di StockScanner,
    bukan di DynamicPreScreener (karena perlu data intraday)."""

    # ── ADX minimum (pastikan ada tren, bukan sideways) ──
    min_adx: float = 18.0
    """ADX >= 18 menunjukkan ada tren yang cukup kuat.
    Digunakan di SignalGenerator, bukan pre-screener."""


# ─────────────────────────────────────────────────────────────
# Pre-screener utama
# ─────────────────────────────────────────────────────────────
class DynamicPreScreener:
    """
    Melakukan pre-filtering universe IDX sebelum analisis teknikal.

    Contoh pemakaian:
        screener = DynamicPreScreener()
        candidates = screener.run()          # → List[str] ticker lolos
        detail     = screener.last_results   # → List[PreScreenResult]
    """

    def __init__(
        self,
        criteria: Optional[ScreenerCriteria] = None,
        universe: Optional[List[str]] = None,
        batch_size: int = 100,
    ):
        """
        Args:
            criteria    : Parameter filter. None = pakai default.
            universe    : Pool saham yang diperiksa.
                          None = IDX_UNIVERSE (seluruh ~400 saham).
            batch_size  : Jumlah ticker per request yf.download().
                          Lebih besar = lebih cepat, namun lebih rentan
                          timeout. Default 100.
        """
        self.criteria = criteria or ScreenerCriteria()
        self.universe: List[str] = universe or IDX_UNIVERSE
        self.batch_size = batch_size

        self.last_results: List[PreScreenResult] = []
        self.last_run_time: Optional[str] = None
        self._daily_cache: Optional[pd.DataFrame] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl_seconds: int = 300  # cache 5 menit

    # ── Batch download ────────────────────────────────────────

    def _download_batch(self, tickers_raw: List[str]) -> pd.DataFrame:
        """
        Unduh data harian 10 hari terakhir untuk satu batch ticker.
        Menggunakan yf.download() multi-ticker yang jauh lebih efisien.

        Kolom hasil:
          Banyak ticker → MultiIndex (field, ticker)
          1 ticker      → flat columns [Open, High, Low, Close, Volume]

        Catatan:
          - group_by TIDAK dipakai agar format kolom tetap (field, ticker),
            sesuai ekspektasi _compute_metrics.
          - threads=False untuk menghindari rate-limiting Yahoo Finance.
        """
        symbols = [get_yahoo_symbol(t) for t in tickers_raw]
        try:
            df = yf.download(
                tickers=" ".join(symbols),
                period="10d",
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=False,  # hindari rate-limit paralel
            )
            return df
        except Exception as e:
            logger.warning(
                f"Batch download gagal ({len(symbols)} ticker): {e}")
            return pd.DataFrame()

    def _fetch_all_daily(self) -> pd.DataFrame:
        """
        Unduh data untuk seluruh universe dalam beberapa batch.
        Hasil di-cache selama `_cache_ttl_seconds`.
        """
        # Validasi cache
        if (
            self._daily_cache is not None
            and self._cache_time is not None
            and (datetime.now() - self._cache_time).total_seconds() < self._cache_ttl_seconds
        ):
            logger.debug("Pre-screener: menggunakan cache data harian")
            return self._daily_cache

        logger.info(
            f"Pre-screener: mengunduh {len(self.universe)} saham dalam batch {self.batch_size}..."
        )

        frames: List[pd.DataFrame] = []
        batches = [
            self.universe[i: i + self.batch_size]
            for i in range(0, len(self.universe), self.batch_size)
        ]
        for idx, batch in enumerate(batches, 1):
            logger.debug(f"  Batch {idx}/{len(batches)}: {len(batch)} ticker")
            df = self._download_batch(batch)
            if not df.empty:
                frames.append(df)
            # Jeda antar batch agar tidak kena rate-limit Yahoo Finance
            if idx < len(batches):
                import time as _time
                _time.sleep(0.5)

        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames, axis=1)
        self._daily_cache = combined
        self._cache_time = datetime.now()
        return combined

    # ── Kalkulasi metrik per saham ────────────────────────────

    def _compute_metrics(
        self, ticker_raw: str, raw_df: pd.DataFrame
    ) -> Optional[Tuple[float, float, float, float, float]]:
        """
        Ekstrak (price, volume_today, volume_ma5, value_ma5, price_change_pct)
        dari DataFrame multi-ticker hasil yf.download().

        Returns None jika data tidak memadai.
        """
        symbol = get_yahoo_symbol(ticker_raw)

        try:
            # ── Coba ambil sub-frame ticker ─────────────────
            if isinstance(raw_df.columns, pd.MultiIndex):
                # Format standar: (field, ticker)
                level1_values = raw_df.columns.get_level_values(1)
                level0_values = raw_df.columns.get_level_values(0)

                if symbol in level1_values:
                    # Format benar: (field, ticker)
                    close = raw_df["Close"][symbol].dropna()
                    volume = raw_df["Volume"][symbol].dropna()
                elif symbol in level0_values:
                    # Format terbalik (ticker, field) — fallback
                    close = raw_df[symbol]["Close"].dropna()
                    volume = raw_df[symbol]["Volume"].dropna()
                else:
                    return None
            else:
                # Flat columns → satu ticker saja
                if "Close" not in raw_df.columns or "Volume" not in raw_df.columns:
                    return None
                close = raw_df["Close"].dropna()
                volume = raw_df["Volume"].dropna()

            if len(close) < 2 or len(volume) < 2:
                return None

            # ── Harga & perubahan ────────────────────────────
            price_now = float(close.iloc[-1])
            price_prev = float(close.iloc[-2])
            price_change_pct = ((price_now - price_prev) / price_prev) * 100

            # ── Volume metrics ───────────────────────────────
            vol_today = float(volume.iloc[-1])
            # MA5: rata-rata 5 hari SEBELUM hari ini (agar tidak bias)
            window = min(5, len(volume) - 1)
            vol_ma5 = float(
                volume.iloc[-1 - window: -1].mean()) if window > 0 else vol_today

            # Nilai transaksi (approximasi): close × volume
            # Kalau ada kolom VWAP/Amount pakai itu, tapi Yahoo tidak menyediakan
            tv_today = price_now * vol_today
            # value MA5
            c5 = close.iloc[-1 - window: -1]
            v5 = volume.iloc[-1 - window: -1]
            if len(c5) > 0:
                value_ma5 = float((c5 * v5).mean())
            else:
                value_ma5 = tv_today

            return price_now, vol_today, vol_ma5, value_ma5, price_change_pct

        except Exception as e:
            logger.debug(f"Gagal hitung metrik {symbol}: {e}")
            return None

    # ── Filter criteria ───────────────────────────────────────

    def _apply_filter(
        self,
        ticker: str,
        price: float,
        volume_today: float,
        volume_ma5: float,
        value_ma5: float,
        price_change_pct: float,
    ) -> PreScreenResult:
        """Terapkan semua kriteria, kembalikan PreScreenResult."""
        c = self.criteria
        fail: List[str] = []

        # (a) Harga minimum
        if price < c.min_price:
            fail.append(
                f"Harga Rp{price:.0f} < min Rp{c.min_price:.0f}"
            )

        # (a2) Harga maksimum (opsional)
        if c.max_price is not None and price > c.max_price:
            fail.append(
                f"Harga Rp{price:.0f} > max Rp{c.max_price:.0f}"
            )

        # (b) Volume MA5
        if volume_ma5 <= c.min_volume_ma5:
            fail.append(
                f"Avg Vol 5H {volume_ma5:,.0f} ≤ {c.min_volume_ma5:,.0f} lembar"
            )

        # (c) Value MA5
        if value_ma5 < c.min_value_ma5:
            fail.append(
                f"Avg Value 5H Rp{value_ma5/1e9:.2f}M < Rp{c.min_value_ma5/1e9:.0f}M"
            )

        # (d) Perubahan harga (absolut)
        if abs(price_change_pct) < c.min_price_change_pct:
            fail.append(
                f"|ΔHarga| {abs(price_change_pct):.2f}% < {c.min_price_change_pct:.1f}%"
            )

        # (e) Volume surge
        vol_surge_ratio = (
            volume_today / volume_ma5) if volume_ma5 > 0 else 0.0
        threshold = 1.0 + c.min_vol_surge_pct / 100.0
        if vol_surge_ratio < threshold:
            fail.append(
                f"Vol surge {vol_surge_ratio:.2f}x < {threshold:.2f}x "
                f"(+{c.min_vol_surge_pct:.0f}%)"
            )

        return PreScreenResult(
            ticker=ticker,
            price=price,
            volume_today=int(volume_today),
            volume_ma5=volume_ma5,
            value_ma5=value_ma5,
            price_change_pct=round(price_change_pct, 2),
            vol_surge_ratio=round(vol_surge_ratio, 3),
            passed=len(fail) == 0,
            fail_reasons=fail,
        )

    # ── Public API ────────────────────────────────────────────

    def run(self, verbose: bool = False) -> List[str]:
        """
        Jalankan pre-screener dan kembalikan list ticker yang lolos.

        Args:
            verbose: Jika True, log detail semua saham (lolos + tolak).

        Returns:
            List kode saham (tanpa .JK) yang memenuhi semua kriteria.
        """
        start = datetime.now()
        raw_df = self._fetch_all_daily()

        results: List[PreScreenResult] = []
        passed: List[str] = []

        for ticker in self.universe:
            metrics = self._compute_metrics(ticker, raw_df)
            if metrics is None:
                # Data tidak tersedia → skip tanpa log bising
                continue

            price, vol_today, vol_ma5, value_ma5, change_pct = metrics
            result = self._apply_filter(
                ticker, price, vol_today, vol_ma5, value_ma5, change_pct
            )
            results.append(result)

            if result.passed:
                passed.append(ticker)
                if verbose:
                    logger.info(
                        f"  ✅ {ticker:6s} | Rp{price:>7,.0f} | "
                        f"Δ{change_pct:+.1f}% | "
                        f"VolSurge {result.vol_surge_ratio:.2f}x | "
                        f"Value/day Rp{value_ma5/1e9:.1f}M"
                    )
            else:
                if verbose:
                    logger.debug(
                        f"  ❌ {ticker:6s} | TOLAK — {'; '.join(result.fail_reasons)}"
                    )

        elapsed = (datetime.now() - start).total_seconds()
        logger.info(
            f"Pre-screen selesai {elapsed:.1f}s | "
            f"Universe: {len(self.universe)} | "
            f"Kandidat lolos: {len(passed)}"
        )

        self.last_results = results
        self.last_run_time = datetime.now().isoformat()
        return passed

    def get_all_results(self) -> List[PreScreenResult]:
        """Kembalikan hasil detail semua saham (lolos maupun tidak)."""
        return self.last_results

    def get_passed_results(self) -> List[PreScreenResult]:
        """Hanya saham yang lolos filter."""
        return [r for r in self.last_results if r.passed]

    def get_failed_results(self) -> List[PreScreenResult]:
        """Hanya saham yang tidak lolos filter."""
        return [r for r in self.last_results if not r.passed]

    def summary(self) -> Dict:
        """Ringkasan hasil pre-screen terakhir."""
        total = len(self.last_results)
        passed_n = sum(1 for r in self.last_results if r.passed)
        criteria = self.criteria

        top_movers = sorted(
            [r for r in self.last_results if r.passed],
            key=lambda r: abs(r.price_change_pct),
            reverse=True,
        )[:5]

        top_volume = sorted(
            [r for r in self.last_results if r.passed],
            key=lambda r: r.vol_surge_ratio,
            reverse=True,
        )[:5]

        return {
            "run_time": self.last_run_time,
            "universe_size": len(self.universe),
            "evaluated": total,
            "passed": passed_n,
            "rejected": total - passed_n,
            "criteria": {
                "min_price": criteria.min_price,
                "min_volume_ma5": criteria.min_volume_ma5,
                "min_value_ma5": criteria.min_value_ma5,
                "min_price_change_pct": criteria.min_price_change_pct,
                "min_vol_surge_pct": criteria.min_vol_surge_pct,
            },
            "top_movers": [
                {
                    "ticker": r.ticker,
                    "price": r.price,
                    "change_pct": r.price_change_pct,
                    "vol_surge": round(r.vol_surge_ratio, 2),
                }
                for r in top_movers
            ],
            "top_volume_surge": [
                {
                    "ticker": r.ticker,
                    "price": r.price,
                    "change_pct": r.price_change_pct,
                    "vol_surge": round(r.vol_surge_ratio, 2),
                }
                for r in top_volume
            ],
        }
