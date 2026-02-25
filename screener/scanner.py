"""
Stock Scanner - Runner utama screener saham
Melakukan scan semua saham dalam watchlist dan menghasilkan sinyal
"""

import asyncio
import logging
import time
from typing import List, Optional, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from data.fetcher import StockDataFetcher
from data.stock_list import SCALPING_WATCHLIST, get_yahoo_symbol
from screener.signal_generator import SignalGenerator, ScalpSignal

logger = logging.getLogger(__name__)


# Mapping nama perusahaan
COMPANY_NAMES = {
    "BBCA": "Bank Central Asia",
    "BBRI": "Bank Rakyat Indonesia",
    "BMRI": "Bank Mandiri",
    "BBNI": "Bank Negara Indonesia",
    "TLKM": "Telkom Indonesia",
    "ASII": "Astra International",
    "UNTR": "United Tractors",
    "ADRO": "Adaro Energy",
    "ANTM": "Aneka Tambang",
    "PTBA": "Bukit Asam",
    "ITMG": "Indo Tambangraya Megah",
    "INCO": "Vale Indonesia",
    "MDKA": "Merdeka Copper Gold",
    "GOTO": "GoTo Gojek Tokopedia",
    "BUKA": "Bukalapak",
    "EMTK": "Elang Mahkota Teknologi",
    "ICBP": "Indofood CBP Sukses Makmur",
    "INDF": "Indofood Sukses Makmur",
    "KLBF": "Kalbe Farma",
    "UNVR": "Unilever Indonesia",
    "SMGR": "Semen Indonesia",
    "INTP": "Indocement Tunggal Prakarsa",
    "PGAS": "Perusahaan Gas Negara",
    "INKP": "Indah Kiat Pulp & Paper",
    "TKIM": "Tjiwi Kimia",
    "BRPT": "Barito Pacific",
    "BRIS": "Bank Syariah Indonesia",
    "BBTN": "Bank Tabungan Negara",
    "MAPI": "Mitra Adiperkasa",
    "CPIN": "Charoen Pokphand Indonesia",
    "HMSP": "HM Sampoerna",
    "HRUM": "Harum Energy",
    "BYAN": "Bayan Resources",
    "MEDC": "Medco Energi Internasional",
    "ESSA": "ESSA Industries",
    "PTPP": "PP (Persero)",
    "WIKA": "Wijaya Karya",
}


class StockScanner:
    """
    Scanner otomatis yang melakukan scan keseluruhan watchlist
    dan menghasilkan sinyal scalping terbaik.
    """

    def __init__(self, max_workers: int = 5):
        self.fetcher = StockDataFetcher()
        self.generator = SignalGenerator()
        self.max_workers = max_workers
        self.last_scan_results: List[ScalpSignal] = []
        self.last_scan_time: Optional[str] = None

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
        signal_filter: Optional[str] = None  # "BUY", "SELL", atau None
    ) -> List[ScalpSignal]:
        """
        Scan semua saham dalam watchlist secara paralel.

        Args:
            watchlist: List kode saham (opsional, default: SCALPING_WATCHLIST)
            min_score: Skor minimum sinyal yang ditampilkan (0-100)
            min_volume_ratio: Minimum rasio volume
            signal_filter: Filter jenis sinyal ("BUY"/"SELL"/None)

        Returns:
            List sinyal terurut dari skor tertinggi
        """
        if watchlist is None:
            watchlist = SCALPING_WATCHLIST

        logger.info(f"Memulai scan {len(watchlist)} saham...")
        start_time = time.time()

        signals = []

        # Scan paralel dengan ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ticker = {
                executor.submit(self.scan_single_stock, ticker): ticker
                for ticker in watchlist
            }

            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    signal = future.result(timeout=30)
                    if signal is not None:
                        signals.append(signal)
                except Exception as e:
                    logger.error(f"Error future {ticker}: {e}")

        # Filter sinyal
        filtered = []
        for sig in signals:
            if sig.signal_score < min_score:
                continue
            if sig.volume_ratio < min_volume_ratio:
                continue
            if signal_filter and sig.signal_type != signal_filter:
                continue
            filtered.append(sig)

        # Urutkan berdasarkan skor (tertinggi dulu)
        filtered.sort(key=lambda x: x.signal_score, reverse=True)

        elapsed = time.time() - start_time
        logger.info(
            f"Scan selesai dalam {elapsed:.1f}s | "
            f"Total: {len(watchlist)} | Sinyal: {len(filtered)}"
        )

        self.last_scan_results = filtered
        from datetime import datetime
        self.last_scan_time = datetime.now().isoformat()

        return filtered

    def get_top_signals(self, n: int = 5) -> List[ScalpSignal]:
        """Ambil N sinyal teratas dari scan terakhir."""
        return self.last_scan_results[:n]

    def get_market_summary(self) -> Dict:
        """
        Ringkasan kondisi pasar berdasarkan scan terakhir.
        """
        if not self.last_scan_results:
            return {"status": "Belum ada data scan"}

        total = len(self.last_scan_results)
        buy_count = sum(
            1 for s in self.last_scan_results if s.signal_type == "BUY")
        sell_count = sum(
            1 for s in self.last_scan_results if s.signal_type == "SELL")
        strong_count = sum(
            1 for s in self.last_scan_results if s.strength == "STRONG")
        avg_score = sum(
            s.signal_score for s in self.last_scan_results) / total if total > 0 else 0

        # Hitung rata-rata RSI sebagai indikator market breadth
        avg_rsi = sum(s.rsi for s in self.last_scan_results) / \
            total if total > 0 else 50

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
                for s in self.last_scan_results
                if s.signal_type == "BUY"
            ][:3],
            "top_sells": [
                {"ticker": s.ticker_clean, "score": s.signal_score,
                    "entry": s.entry_price, "tp2": s.tp2}
                for s in self.last_scan_results
                if s.signal_type == "SELL"
            ][:3],
        }

    async def scan_all_async(
        self,
        watchlist: Optional[List[str]] = None,
        min_score: int = 55,
        signal_filter: Optional[str] = None
    ) -> List[ScalpSignal]:
        """Versi async dari scan_all untuk digunakan di FastAPI."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.scan_all(watchlist, min_score, 1.2, signal_filter)
        )
        return result
