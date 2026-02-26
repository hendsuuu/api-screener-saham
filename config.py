"""
Konfigurasi aplikasi - dibaca dari .env
"""

import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # ─── Telegram ─────────────────────────────
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_IDS: List[str] = [
        cid.strip()
        for cid in os.getenv("TELEGRAM_CHAT_IDS", "").split(",")
        if cid.strip()
    ]

    # ─── Screener ─────────────────────────────
    SCAN_INTERVAL_MINUTES: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))
    MIN_SIGNAL_SCORE: int = int(os.getenv("MIN_SIGNAL_SCORE", "50"))
    MAX_SIGNALS_PER_SCAN: int = int(os.getenv("MAX_SIGNALS_PER_SCAN", "10"))
    MIN_VOLUME_RATIO: float = float(
        os.getenv("MIN_VOLUME_RATIO", "0.0"))  # 0.0 = dinonaktifkan

    # ─── Pre-screen Criteria (Dynamic Screener) ───
    # Harga minimum saham (Rp) — filter sub-gocap / penny stock
    PRESCREEN_MIN_PRICE: float = float(os.getenv("PRESCREEN_MIN_PRICE", "100"))
    # Volume MA5 minimum (lembar/hari) — 3 juta = liquid untuk scalping
    PRESCREEN_MIN_VOLUME_MA5: float = float(
        os.getenv("PRESCREEN_MIN_VOLUME_MA5", "3000000"))
    # Nilai transaksi MA5 minimum (Rp/hari) — Rp 5 miliar
    PRESCREEN_MIN_VALUE_MA5: float = float(
        os.getenv("PRESCREEN_MIN_VALUE_MA5", "5000000000"))
    # Minimum |perubahan harga 1 hari| (%) — 0.5% untuk tangkap pre-breakout
    PRESCREEN_MIN_PRICE_CHANGE_PCT: float = float(
        os.getenv("PRESCREEN_MIN_PRICE_CHANGE_PCT", "0.5")
    )
    # Volume hari ini vs MA5 harus naik minimal X% (default 15%)
    PRESCREEN_MIN_VOL_SURGE_PCT: float = float(
        os.getenv("PRESCREEN_MIN_VOL_SURGE_PCT", "15.0")
    )
    # Harga maksimum Rp 10.000 — avoid ultra-high-price stocks
    PRESCREEN_MAX_PRICE: float = float(
        os.getenv("PRESCREEN_MAX_PRICE", "10000"))

    # ─── Scalping Parameters ──────────────────
    TP1_PCT: float = float(os.getenv("TP1_PCT", "1.5"))
    TP2_PCT: float = float(os.getenv("TP2_PCT", "2.5"))
    TP3_PCT: float = float(os.getenv("TP3_PCT", "3.5"))
    SL_PCT: float = float(os.getenv("SL_PCT", "1.0"))
    MIN_RR_RATIO: float = float(os.getenv("MIN_RR_RATIO", "2.0"))

    # ─── Limit Sinyal Harian ──────────────────
    MAX_BUY_SIGNALS: int = int(os.getenv("MAX_BUY_SIGNALS", "10"))
    MAX_WASPADA_SIGNALS: int = int(os.getenv("MAX_WASPADA_SIGNALS", "10"))

    # ─── API ──────────────────────────────────
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    API_SECRET_KEY: str = os.getenv("API_SECRET_KEY")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # ─── Workers ──────────────────────────────
    MAX_SCAN_WORKERS: int = int(os.getenv("MAX_SCAN_WORKERS", "8"))
    # Jumlah worker uvicorn untuk production (HARUS 1 karena bot polling)
    UVICORN_WORKERS: int = int(os.getenv("UVICORN_WORKERS", "1"))

    # ─── Data Store ───────────────────────────
    # Direktori penyimpanan file Parquet historis OHLCV
    DATA_STORE_PATH: str = os.getenv("DATA_STORE_PATH", "data/store")
    # Berapa hari data yang disimpan (prune otomatis via manage.py)
    DATA_STORE_MAX_DAYS: int = int(os.getenv("DATA_STORE_MAX_DAYS", "365"))

    # ─── Crawler (Historical + Incremental) ──
    # Periode historis untuk crawl harian (1y / 2y / 5y)
    CRAWL_HISTORICAL_PERIOD: str = os.getenv("CRAWL_HISTORICAL_PERIOD", "5y")
    # Periode intraday 5m (yfinance max 60d untuk interval 5m)
    CRAWL_INTRADAY_PERIOD: str = os.getenv("CRAWL_INTRADAY_PERIOD", "60d")
    # Jumlah thread paralel untuk crawl
    CRAWL_WORKERS: int = int(os.getenv("CRAWL_WORKERS", "4"))
    # Jumlah ticker per batch saat yf.download
    CRAWL_BATCH_SIZE: int = int(os.getenv("CRAWL_BATCH_SIZE", "20"))
    # Jeda antar batch (detik) untuk menghindari rate-limit
    CRAWL_DELAY_SECONDS: float = float(os.getenv("CRAWL_DELAY_SECONDS", "0.5"))

    # ─── Admin Bot ────────────────────────────
    # Chat ID pribadi yang boleh mengirim perintah admin ke bot
    # Isi di .env: ADMIN_CHAT_IDS=123456789,987654321
    ADMIN_CHAT_IDS: List[int] = [
        int(x.strip())
        for x in os.getenv("ADMIN_CHAT_IDS", "").split(",")
        if x.strip().lstrip("-").isdigit()
    ]

    # ─── Proxy System ─────────────────────────────
    # off | single | rotate
    PROXY_MODE: str = os.getenv("PROXY_MODE", "off")
    PROXY_URL: str = os.getenv("PROXY_URL", "")
    PROXY_LIST_PATH: str = os.getenv("PROXY_LIST_PATH", "data/proxies.txt")
    PROXY_TIMEOUT: int = int(os.getenv("PROXY_TIMEOUT", "12"))
    PROXY_MAX_RETRY: int = int(os.getenv("PROXY_MAX_RETRY", "3"))
    PROXY_ROTATE_ON_ERROR: bool = (
        os.getenv("PROXY_ROTATE_ON_ERROR", "true").lower() == "true"
    )
    PROXY_FALLBACK_DIRECT: bool = (
        os.getenv("PROXY_FALLBACK_DIRECT", "true").lower() == "true"
    )
    PROXY_COOLDOWN_SECONDS: int = int(
        os.getenv("PROXY_COOLDOWN_SECONDS", "1200"))
    PROXY_HEALTHCHECK_URL: str = os.getenv(
        "PROXY_HEALTHCHECK_URL", "https://query1.finance.yahoo.com"
    )

    # ─── Adaptive Rate Limiter ────────────────────
    YF_BASE_DELAY: float = float(os.getenv("YF_BASE_DELAY", "0.3"))
    YF_MAX_DELAY: float = float(os.getenv("YF_MAX_DELAY", "3.0"))
    YF_SUCCESS_DECAY: float = float(os.getenv("YF_SUCCESS_DECAY", "0.05"))
    YF_ERROR_BOOST: float = float(os.getenv("YF_ERROR_BOOST", "0.35"))
    YF_429_EXTRA_BOOST: float = float(os.getenv("YF_429_EXTRA_BOOST", "0.8"))
    YF_ERROR_WINDOW: int = int(os.getenv("YF_ERROR_WINDOW", "30"))
    CRAWL_SHUFFLE_TICKERS: bool = (
        os.getenv("CRAWL_SHUFFLE_TICKERS", "true").lower() == "true"
    )
    CRAWL_DELAY_JITTER: float = float(os.getenv("CRAWL_DELAY_JITTER", "0.25"))

    def build_screener_criteria(self):
        """Buat ScreenerCriteria dari nilai config saat ini."""
        from data.dynamic_screener import ScreenerCriteria
        return ScreenerCriteria(
            min_price=self.PRESCREEN_MIN_PRICE,
            min_volume_ma5=self.PRESCREEN_MIN_VOLUME_MA5,
            min_value_ma5=self.PRESCREEN_MIN_VALUE_MA5,
            min_price_change_pct=self.PRESCREEN_MIN_PRICE_CHANGE_PCT,
            min_vol_surge_pct=self.PRESCREEN_MIN_VOL_SURGE_PCT,
            max_price=self.PRESCREEN_MAX_PRICE if self.PRESCREEN_MAX_PRICE > 0 else None,
            require_ema_alignment=False,  # aktifkan via .env jika ingin lebih ketat
            min_adx=float(os.getenv("PRESCREEN_MIN_ADX", "18.0")),
        )

    def validate(self):
        """Validasi konfigurasi wajib."""
        errors = []
        if not self.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN belum diset di .env")
        if not self.TELEGRAM_CHAT_IDS:
            errors.append("TELEGRAM_CHAT_IDS belum diset di .env")
        if errors:
            raise ValueError("\n".join(errors))
        return True


settings = Settings()
