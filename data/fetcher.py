"""
Data Fetcher - Mengambil data saham Indonesia dari Yahoo Finance
Mendukung realtime intraday dan historical data
"""

import yfinance as yf
import pandas as pd
import numpy as np
from typing import Optional, Dict, List
import logging
from datetime import datetime, timedelta
import time

from data.store import get_store

logger = logging.getLogger(__name__)

# Senyapkan log 'Failed to get ticker' bawaan yfinance
# agar tidak memenuhi output (error tetap ditangkap di level kita)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("yfinance.base").setLevel(logging.CRITICAL)
logging.getLogger("yfinance.utils").setLevel(logging.CRITICAL)
logging.getLogger("peewee").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.WARNING)


class StockDataFetcher:
    """
    Fetcher data saham menggunakan Yahoo Finance
    Saham Indonesia menggunakan suffix .JK (contoh: BBCA.JK)
    """

    def __init__(self):
        self.session_cache: Dict[str, pd.DataFrame] = {}
        self.cache_time: Dict[str, datetime] = {}
        self.cache_duration = 60  # detik
        # Persistent OHLCV store (Parquet per-ticker)
        try:
            self.store = get_store()
        except Exception:
            self.store = None

    def _is_cache_valid(self, ticker: str) -> bool:
        if ticker not in self.cache_time:
            return False
        elapsed = (datetime.now() - self.cache_time[ticker]).total_seconds()
        return elapsed < self.cache_duration

    def get_intraday_data(
        self,
        ticker: str,
        period: str = "1d",
        interval: str = "5m",
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        Ambil data intraday saham.

        Args:
            ticker: Kode saham (contoh: BBCA.JK)
            period: Periode data (1d, 5d)
            interval: Interval candle (1m, 2m, 5m, 15m, 30m, 60m)
            use_cache: Gunakan cache untuk mengurangi API call

        Returns:
            DataFrame dengan kolom: Open, High, Low, Close, Volume
        """
        cache_key = f"{ticker}_{period}_{interval}"

        if use_cache and self._is_cache_valid(cache_key):
            return self.session_cache[cache_key]

        # Retry hingga 3 kali dengan jeda eksponensial
        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                stock = yf.Ticker(ticker)
                df = stock.history(period=period, interval=interval)

                if df is None or df.empty:
                    # Coba fallback period lebih panjang agar indikator bisa dihitung
                    if attempt == 1 and period == "5d":
                        df = stock.history(period="1mo", interval=interval)
                    if df is None or df.empty:
                        logger.debug(
                            f"Tidak ada data untuk {ticker} (attempt {attempt})")
                        if attempt < 3:
                            time.sleep(1.0 * attempt)
                            continue
                        return None

                # Bersihkan data
                df = df.dropna(subset=["Open", "High", "Low", "Close"])
                df.index = pd.to_datetime(df.index)

                # Hapus kolom non-OHLCV (yfinance 1.x: Dividends, Stock Splits)
                _keep = [c for c in ["Open", "High", "Low",
                                     "Close", "Volume"] if c in df.columns]
                df = df[_keep]

                if df.empty:
                    logger.debug(f"Data {ticker} kosong setelah dropna")
                    return None

                # Simpan ke cache
                self.session_cache[cache_key] = df
                self.cache_time[cache_key] = datetime.now()

                # Simpan ke persistent store (non-blocking — jika error diabaikan)
                if self.store is not None:
                    try:
                        self.store.upsert(ticker, interval, df)
                    except Exception as _se:
                        logger.debug(f"Store upsert skip [{ticker}]: {_se}")

                return df

            except Exception as e:
                last_error = e
                logger.debug(f"Attempt {attempt}/3 gagal untuk {ticker}: {e}")
                if attempt < 3:
                    time.sleep(1.5 * attempt)

        logger.warning(
            f"Gagal ambil data {ticker} setelah 3 percobaan: {last_error}")
        return None

    def get_daily_data(
        self,
        ticker: str,
        period: str = "3mo",
        interval: str = "1d"
    ) -> Optional[pd.DataFrame]:
        """
        Ambil data harian saham untuk analisis trend.

        Args:
            ticker: Kode saham
            period: Periode (1mo, 3mo, 6mo, 1y)
            interval: Interval (1d, 1wk)
        """
        last_error: Optional[Exception] = None
        for attempt in range(1, 3):
            try:
                stock = yf.Ticker(ticker)
                df = stock.history(period=period, interval=interval)

                if df is None or df.empty:
                    if attempt < 2:
                        time.sleep(1.0)
                        continue
                    return None

                df = df.dropna(subset=["Open", "High", "Low", "Close"])
                # Hapus kolom non-OHLCV (yfinance 1.x: Dividends, Stock Splits)
                _keep = [c for c in ["Open", "High", "Low",
                                     "Close", "Volume"] if c in df.columns]
                df = df[_keep]
                if df.empty:
                    return None

                # Simpan ke persistent store
                if self.store is not None and interval in ("1d", "1wk"):
                    try:
                        self.store.upsert(ticker, "1d", df)
                    except Exception as _se:
                        logger.debug(
                            f"Store upsert (daily) skip [{ticker}]: {_se}")

                return df

            except Exception as e:
                last_error = e
                if attempt < 2:
                    time.sleep(1.5)

        logger.debug(f"Error data harian {ticker}: {last_error}")
        return None

    def get_current_price(self, ticker: str) -> Optional[Dict]:
        """
        Ambil harga terkini saham beserta info dasar.

        Returns:
            Dict berisi: price, open, high, low, volume, prev_close, change_pct
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.fast_info

            # Ambil juga data 1d untuk intraday reference
            df_today = self.get_intraday_data(
                ticker, period="1d", interval="5m")

            if df_today is None or df_today.empty:
                return None

            current_price = float(df_today["Close"].iloc[-1])
            open_price = float(df_today["Open"].iloc[0])
            high_price = float(df_today["High"].max())
            low_price = float(df_today["Low"].min())
            volume = int(df_today["Volume"].sum())

            # Hitung perubahan dari open
            change_pct = ((current_price - open_price) / open_price) * 100

            # Previous close
            try:
                prev_close = float(
                    info.previous_close) if info.previous_close else open_price
                change_from_prev = (
                    (current_price - prev_close) / prev_close) * 100
            except Exception:
                prev_close = open_price
                change_from_prev = change_pct

            return {
                "ticker": ticker,
                "price": current_price,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "volume": volume,
                "prev_close": prev_close,
                "change_pct": round(change_from_prev, 2),
                "change_intraday_pct": round(change_pct, 2),
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error harga terkini {ticker}: {e}")
            return None

    def get_bulk_prices(
        self,
        tickers: List[str],
        delay: float = 0.1
    ) -> Dict[str, Dict]:
        """
        Ambil harga untuk banyak saham sekaligus.

        Args:
            tickers: List kode saham
            delay: Jeda antar request (detik) untuk menghindari rate limit
        """
        results = {}

        for ticker in tickers:
            data = self.get_current_price(ticker)
            if data:
                results[ticker] = data
            time.sleep(delay)

        return results

    def get_market_info(self, ticker: str) -> Optional[Dict]:
        """
        Ambil info detail saham: market cap, PE ratio, dll.
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            return {
                "ticker": ticker,
                "name": info.get("longName", ticker),
                "sector": info.get("sector", "N/A"),
                "industry": info.get("industry", "N/A"),
                "market_cap": info.get("marketCap", 0),
                "pe_ratio": info.get("trailingPE", 0),
                "avg_volume": info.get("averageVolume", 0),
                "fifty_day_avg": info.get("fiftyDayAverage", 0),
                "two_hundred_day_avg": info.get("twoHundredDayAverage", 0),
            }
        except Exception as e:
            logger.error(f"Error info {ticker}: {e}")
            return None

    def is_market_open(self) -> bool:
        """
        Cek apakah pasar BEI sedang buka.
        Jam bursa: Senin-Jumat 09:00-16:00 WIB
        Sesi 1: 09:00-11:30
        Sesi 2: 13:30-16:00
        Pre-opening: 08:45-09:00
        """
        import pytz
        wib = pytz.timezone("Asia/Jakarta")
        now = datetime.now(wib)

        # Cek hari kerja (Senin=0, Minggu=6)
        if now.weekday() >= 5:
            return False

        hour = now.hour
        minute = now.minute
        time_decimal = hour + minute / 60

        # Sesi 1: 09:00 - 11:30
        sesi1 = 9.0 <= time_decimal <= 11.5
        # Sesi 2: 13:30 - 16:00
        sesi2 = 13.5 <= time_decimal <= 16.0

        return sesi1 or sesi2

    def get_market_status(self) -> Dict:
        """Ambil status pasar saat ini."""
        import pytz
        wib = pytz.timezone("Asia/Jakarta")
        now = datetime.now(wib)

        hour = now.hour
        minute = now.minute
        time_decimal = hour + minute / 60
        is_weekday = now.weekday() < 5

        if not is_weekday:
            status = "WEEKEND - Pasar Tutup"
            session = "closed"
        elif 8.75 <= time_decimal < 9.0:
            status = "PRE-OPENING"
            session = "pre_open"
        elif 9.0 <= time_decimal <= 11.5:
            status = "BUKA - Sesi 1"
            session = "session1"
        elif 11.5 < time_decimal < 13.5:
            status = "ISTIRAHAT SIANG"
            session = "break"
        elif 13.5 <= time_decimal <= 15.0:
            status = "BUKA - Sesi 2"
            session = "session2"
        elif 15.0 < time_decimal <= 15.15:
            status = "POST-CLOSING"
            session = "post_close"
        else:
            status = "TUTUP"
            session = "closed"

        return {
            "status": status,
            "session": session,
            "is_open": session in ["session1", "session2"],
            "time_wib": now.strftime("%H:%M:%S WIB"),
            "date": now.strftime("%A, %d %B %Y")
        }
