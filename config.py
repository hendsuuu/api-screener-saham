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
    # Chat IDs dipisah koma: -100123456789,987654321
    TELEGRAM_CHAT_IDS: List[str] = [
        cid.strip()
        for cid in os.getenv("TELEGRAM_CHAT_IDS", "").split(",")
        if cid.strip()
    ]

    # ─── Screener ─────────────────────────────
    # Interval scan (menit) saat pasar buka
    SCAN_INTERVAL_MINUTES: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))
    # Skor minimum sinyal yang dikirim notif
    MIN_SIGNAL_SCORE: int = int(os.getenv("MIN_SIGNAL_SCORE", "60"))
    # Maksimal sinyal dikirim per scan
    MAX_SIGNALS_PER_SCAN: int = int(os.getenv("MAX_SIGNALS_PER_SCAN", "3"))
    # Minimum rasio volume vs rata-rata
    MIN_VOLUME_RATIO: float = float(os.getenv("MIN_VOLUME_RATIO", "1.2"))

    # ─── Scalping Parameters ──────────────────
    TP1_PCT: float = float(os.getenv("TP1_PCT", "1.5"))   # +1.5%
    TP2_PCT: float = float(os.getenv("TP2_PCT", "2.5"))   # +2.5%
    TP3_PCT: float = float(os.getenv("TP3_PCT", "3.5"))   # +3.5%
    SL_PCT: float = float(os.getenv("SL_PCT", "1.0"))     # -1.0%
    MIN_RR_RATIO: float = float(os.getenv("MIN_RR_RATIO", "2.0"))  # 1:2 RR

    # ─── API ──────────────────────────────────
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    API_SECRET_KEY: str = os.getenv("API_SECRET_KEY", "changeme-secret-key")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # ─── Workers ──────────────────────────────
    # Thread pool untuk scan paralel
    MAX_SCAN_WORKERS: int = int(os.getenv("MAX_SCAN_WORKERS", "8"))

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
