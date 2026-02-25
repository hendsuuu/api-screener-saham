"""
Stock Scanner - Runner utama screener saham

Alur dua tahap:
  Tahap 1 — Pre-screen (DynamicPreScreener):
    Unduh data harian seluruh IDX_UNIVERSE (~400 saham) secara batch,
    kemudian filter berdasarkan kriteria likuiditas & momentum:
      • Harga penutupan >= min_price
      • Volume MA5 > min_volume_ma5
      • Nilai transaksi MA5 >= min_value_ma5
      • |Perubahan harga 1 hari| >= min_price_change_pct
      • Volume hari ini / Volume MA5 >= 1 + vol_surge_pct
    Hasil: 20–60 kandidat aktif.

  Tahap 2 — Full technical scan (StockScanner):
    Unduh data intraday 5-menit hanya untuk kandidat,
    hitung semua indikator, dan generate sinyal BUY/SELL
    lengkap dengan Entry, TP1/TP2/TP3, SL, dan scoring.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from data.fetcher import StockDataFetcher
from data.stock_list import (
    IDX_UNIVERSE, SCREENER_WATCHLIST,
    COMPANY_NAMES, get_yahoo_symbol,
)
from data.dynamic_screener import DynamicPreScreener, ScreenerCriteria
from screener.signal_generator import SignalGenerator, ScalpSignal

logger = logging.getLogger(__name__)


class StockScanner:
    """
    Scanner dua tahap:
      1. DynamicPreScreener  → filter universe harian (cepat, batch)
      2. Analisis teknikal   → intraday 5-menit hanya pada kandidat
    """

    def __init__(
        self,
        max_workers: int = 5,
        criteria: Optional[ScreenerCriteria] = None,
    ):
        self.fetcher = StockDataFetcher()
        self.generator = SignalGenerator()
        self.max_workers = max_workers
        self.pre_screener = DynamicPreScreener(
            criteria=criteria,
            universe=IDX_UNIVERSE,
        )
        self.last_scan_results: List[ScalpSignal] = []
        self.last_scan_time: Optional[str] = None
        self.last_prescreen_summary: Optional[Dict] = None

    def scan_single_stock(self, ticker_raw: str) -> Optional[ScalpSignal]:
        """
        Scan satu saham dan kembalikan sinyal terbaik (BUY/SELL).

        Args:
            ticker_raw: Kode saham tanpa suffix (contoh: BBCA)

        Returns:
            ScalpSignal jika ada sinyal, None jika tidak ada
        """
        ticker = get_yahoo_symbol(ticker_raw)
        company_name = COMPANY_NAMES.get(ticker_raw, ticker_raw)

        try:
            # Ambil data 5 menit untuk analisis
            df_5m = self.fetcher.get_intraday_data(
                ticker,
                period="5d",    # 5 hari untuk indikator yang butuh banyak data
                interval="5m"
            )

            if df_5m is None or len(df_5m) < 50:
                logger.debug(
                    f"Data tidak cukup untuk {ticker}: {len(df_5m) if df_5m is not None else 0} candle")
                return None

            # Coba generate sinyal BUY
            buy_signal = self.generator.generate_buy_signal(
                ticker, df_5m, company_name)

            # Coba generate sinyal SELL
            sell_signal = self.generator.generate_sell_signal(
                ticker, df_5m, company_name)

            # Pilih sinyal dengan skor lebih tinggi
            if buy_signal and sell_signal:
                return buy_signal if buy_signal.signal_score >= sell_signal.signal_score else sell_signal
            elif buy_signal:
                return buy_signal
            elif sell_signal:
                return sell_signal

            return None

        except Exception as e:
            logger.error(f"Error scan {ticker}: {e}")
            return None

    def scan_all(
        self,
        watchlist: Optional[List[str]] = None,
        min_score: int = 55,
        min_volume_ratio: float = 1.2,
        signal_filter: Optional[str] = None,  # "BUY", "SELL", atau None
        skip_prescreen: bool = False,
    ) -> List[ScalpSignal]:
        """
        Scan saham secara dua tahap.

        Tahap 1 — Pre-screen (otomatis jika watchlist=None):
            Filter IDX_UNIVERSE berdasarkan kriteria likuiditas & momentum.
            Saham yang tidak memenuhi kriteria TIDAK di-scan teknikal
            sehingga waktu proses jauh lebih efisien.

        Tahap 2 — Analisis teknikal pada kandidat:
            Intraday 5-menit → RSI, MACD, BB, VWAP, ADX, ATR → sinyal.

        Args:
            watchlist       : Daftar ticker manual (opsional).
                              None  → jadikan IDX_UNIVERSE sebagai pool,
                                      lalu jalankan pre-screener otomatis.
            min_score       : Skor minimum sinyal yang dikembalikan (0–100).
            min_volume_ratio: Filter tambahan rasio volume intraday.
            signal_filter   : "BUY" / "SELL" / None.
            skip_prescreen  : True = lewati tahap 1, langsung scan semua
                              ticker dalam watchlist (berguna untuk debug).

        Returns:
            List[ScalpSignal] terurut dari skor tertinggi.
        """
        start_time = time.time()

        # ── Tahap 1: tentukan kandidat ───────────────────────
        if watchlist is not None:
            # Watchlist manual → skip pre-screener
            candidates = watchlist
            logger.info(
                f"Scan manual: {len(candidates)} saham (pre-screen dilewati)"
            )
        elif skip_prescreen:
            candidates = IDX_UNIVERSE
            logger.info(
                f"Scan tanpa pre-screen: {len(candidates)} saham (debug mode)"
            )
        else:
            # DEFAULT: pre-screen IDX_UNIVERSE dulu
            logger.info(
                f"Tahap 1 — Pre-screen {len(IDX_UNIVERSE)} saham IDX..."
            )
            candidates = self.pre_screener.run(verbose=True)
            self.last_prescreen_summary = self.pre_screener.summary()

            if not candidates:
                logger.warning(
                    "Pre-screen tidak menghasilkan kandidat. "
                    "Pasar mungkin tutup atau data terbatas. "
                    "Fallback ke SCREENER_WATCHLIST."
                )
                candidates = SCREENER_WATCHLIST

            logger.info(
                f"Tahap 1 selesai: {len(candidates)} kandidat lolos pre-screen "
                f"(dari {len(IDX_UNIVERSE)} saham)"
            )

        # ── Tahap 2: analisis teknikal paralel ───────────────
        logger.info(
            f"Tahap 2 — Analisis teknikal {len(candidates)} kandidat...")

        signals: List[ScalpSignal] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ticker = {
                executor.submit(self.scan_single_stock, ticker): ticker
                for ticker in candidates
            }
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    signal = future.result(timeout=30)
                    if signal is not None:
                        signals.append(signal)
                except Exception as e:
                    logger.error(f"Error future {ticker}: {e}")

        # ── Filter & urutkan ─────────────────────────────────
        filtered = [
            sig for sig in signals
            if sig.signal_score >= min_score
            and sig.volume_ratio >= min_volume_ratio
            and (signal_filter is None or sig.signal_type == signal_filter)
        ]
        filtered.sort(key=lambda x: x.signal_score, reverse=True)

        elapsed = time.time() - start_time
        logger.info(
            f"Scan selesai {elapsed:.1f}s | "
            f"Kandidat: {len(candidates)} | "
            f"Sinyal ditemukan: {len(filtered)}"
        )

        self.last_scan_results = filtered
        from datetime import datetime
        self.last_scan_time = datetime.now().isoformat()

        # Simpan ke disk agar /buy dan /waspada bisa baca data
        # meskipun bot berjalan di proses terpisah atau server restart
        if filtered:
            try:
                from data.signal_cache import save_signals
                save_signals(filtered, self.last_scan_time)
            except Exception as _ce:
                logger.debug(f"Signal cache write skip: {_ce}")

        return filtered

    def get_top_signals(self, n: int = 5) -> List[ScalpSignal]:
        """Ambil N sinyal teratas dari scan terakhir (cek disk jika memory kosong)."""
        results = self._get_results_with_cache()
        return results[:n]

    def _get_results_with_cache(self, signal_type: Optional[str] = None) -> List[ScalpSignal]:
        """
        Kembalikan sinyal dari memory.
        Jika memory kosong (belum scan sejak restart), coba load dari cache disk.
        """
        if not self.last_scan_results:
            try:
                from data.signal_cache import load_signals_today
                cached = load_signals_today()
                if cached:
                    logger.info(
                        f"[Scanner] Memory kosong, load {len(cached)} sinyal dari cache disk"
                    )
                    self.last_scan_results = cached
                    # Ambil scan_time dari cache
                    if not self.last_scan_time:
                        self.last_scan_time = cached[0].timestamp if cached else None
            except Exception as e:
                logger.debug(f"[Scanner] Gagal load cache: {e}")

        results = self.last_scan_results
        if signal_type:
            results = [s for s in results if s.signal_type == signal_type]
        return results

    def get_market_summary(self) -> Dict:
        """
        Ringkasan kondisi pasar berdasarkan scan terakhir.
        Jika memory kosong, otomatis load dari cache disk.
        """
        results = self._get_results_with_cache()
        if not results:
            return {"status": "Belum ada data scan"}

        total = len(results)
        buy_count = sum(1 for s in results if s.signal_type == "BUY")
        # WASPADA adalah pengganti SELL di BEI
        sell_count = sum(1 for s in results if s.signal_type in ("WASPADA", "SELL"))
        strong_count = sum(1 for s in results if s.strength == "STRONG")
        avg_score = sum(s.signal_score for s in results) / total if total > 0 else 0
        avg_rsi = sum(s.rsi for s in results) / total if total > 0 else 50

        if buy_count > sell_count * 1.5:
            market_bias = "BULLISH"
        elif sell_count > buy_count * 1.5:
            market_bias = "BEARISH"
        else:
            market_bias = "MIXED/SIDEWAYS"

        return {
            "market_bias": market_bias,
            "total_signals": total,
            "buy_signals": buy_count,
            "sell_signals": sell_count,
            "strong_signals": strong_count,
            "avg_score": round(avg_score, 1),
            "avg_rsi": round(avg_rsi, 1),
            "scan_time": self.last_scan_time,
            "top_buys": [
                {"ticker": s.ticker_clean, "score": s.signal_score,
                    "entry": s.entry_price, "tp2": s.tp2}
                for s in results
                if s.signal_type == "BUY"
            ][:3],
            "top_sells": [
                {"ticker": s.ticker_clean, "score": s.signal_score,
                    "entry": s.entry_price}
                for s in results
                if s.signal_type in ("WASPADA", "SELL")
            ][:3],
        }

    async def scan_all_async(
        self,
        watchlist: Optional[List[str]] = None,
        min_score: int = 55,
        signal_filter: Optional[str] = None,
        skip_prescreen: bool = False,
    ) -> List[ScalpSignal]:
        """Versi async dari scan_all untuk digunakan di FastAPI."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.scan_all(
                watchlist, min_score, 1.2, signal_filter, skip_prescreen
            ),
        )
        return result

    def update_criteria(self, criteria: ScreenerCriteria) -> None:
        """Update kriteria pre-screener tanpa restart scanner."""
        self.pre_screener.criteria = criteria
        # Invalidasi cache agar filter baru langsung aktif
        self.pre_screener._daily_cache = None
        self.pre_screener._cache_time = None
        logger.info(f"Kriteria pre-screener diperbarui: {criteria}")
