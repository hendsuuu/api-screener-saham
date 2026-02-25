"""
Konfigurasi aplikasi - dibaca dari .env
"""

import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # ─── Telegram ─────────────────────────────
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_IDS: List[str] = [
        cid.strip()
        for cid in os.getenv("TELEGRAM_CHAT_IDS", "").split(",")
        if cid.strip()
    ]

    # ─── Screener ─────────────────────────────
    SCAN_INTERVAL_MINUTES: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))
    MIN_SIGNAL_SCORE: int = int(os.getenv("MIN_SIGNAL_SCORE", "60"))
    MAX_SIGNALS_PER_SCAN: int = int(os.getenv("MAX_SIGNALS_PER_SCAN", "3"))
    MIN_VOLUME_RATIO: float = float(os.getenv("MIN_VOLUME_RATIO", "1.2"))

    # ─── Pre-screen Criteria (Dynamic Screener) ───
    # Harga minimum saham (Rp) — filter sub-gocap / penny stock
    PRESCREEN_MIN_PRICE: float = float(os.getenv("PRESCREEN_MIN_PRICE", "100"))
    # Volume MA5 minimum (lembar/hari)
    PRESCREEN_MIN_VOLUME_MA5: float = float(
        os.getenv("PRESCREEN_MIN_VOLUME_MA5", "10000000"))
    # Nilai transaksi MA5 minimum (Rp/hari) — default 10 miliar
    PRESCREEN_MIN_VALUE_MA5: float = float(
        os.getenv("PRESCREEN_MIN_VALUE_MA5", "10000000000"))
    # Minimum |perubahan harga 1 hari| (%)
    # Pakai nilai absolut agar saham turun pun terdeteksi untuk sinyal SELL.
    # Turunkan ke 1.5 jika ingin menangkap pre-breakout lebih awal.
    PRESCREEN_MIN_PRICE_CHANGE_PCT: float = float(
        os.getenv("PRESCREEN_MIN_PRICE_CHANGE_PCT", "2.0")
    )
    # Volume hari ini vs MA5 harus naik minimal X% (default 30%)
    PRESCREEN_MIN_VOL_SURGE_PCT: float = float(
        os.getenv("PRESCREEN_MIN_VOL_SURGE_PCT", "30.0")
    )
    # Harga maksimum (opsional, 0 = nonaktif)
    PRESCREEN_MAX_PRICE: float = float(os.getenv("PRESCREEN_MAX_PRICE", "0"))

    # ─── Scalping Parameters ──────────────────
    TP1_PCT: float = float(os.getenv("TP1_PCT", "1.5"))
    TP2_PCT: float = float(os.getenv("TP2_PCT", "2.5"))
    TP3_PCT: float = float(os.getenv("TP3_PCT", "3.5"))
    SL_PCT: float = float(os.getenv("SL_PCT", "1.0"))
    MIN_RR_RATIO: float = float(os.getenv("MIN_RR_RATIO", "2.0"))

    # ─── API ──────────────────────────────────
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    API_SECRET_KEY: str = os.getenv("API_SECRET_KEY", "changeme-secret-key")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # ─── Workers ──────────────────────────────
    MAX_SCAN_WORKERS: int = int(os.getenv("MAX_SCAN_WORKERS", "8"))

    # ─── Data Store ───────────────────────────
    # Direktori penyimpanan file Parquet historis OHLCV
    DATA_STORE_PATH: str = os.getenv("DATA_STORE_PATH", "data/store")
    # Berapa hari data yang disimpan (prune otomatis via manage.py)
    DATA_STORE_MAX_DAYS: int = int(os.getenv("DATA_STORE_MAX_DAYS", "365"))

    # ─── Admin Bot ────────────────────────────
    # Chat ID pribadi yang boleh mengirim perintah admin ke bot
    # Isi di .env: ADMIN_CHAT_IDS=123456789,987654321
    ADMIN_CHAT_IDS: List[int] = [
        int(x.strip())
        for x in os.getenv("ADMIN_CHAT_IDS", "").split(",")
        if x.strip().lstrip("-").isdigit()
    ]

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
