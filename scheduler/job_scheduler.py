"""
Job Scheduler - Menjalankan update data & scan otomatis pada interval tertentu
Hanya aktif saat jam bursa BEI

Alur baru (data-first):
  ┌────────────────────────────────────────────────────────┐
  │  Setiap 15 menit (jam bursa)                           │
  │    1. DataCrawler.update_latest() → perbarui store     │
  │    2. StockScanner.scan_all()     → baca dari store    │
  │    3. TelegramNotifier            → kirim sinyal terbaik│
  └────────────────────────────────────────────────────────┘

Manfaat: scanner membaca data Parquet lokal (cepat, tanpa API call live).
"""

import asyncio
import logging
from typing import Optional, List, Union
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import pytz

from screener.scanner import StockScanner
from data.fetcher import StockDataFetcher
from telegram_bot.notifier_runner import run_notification

logger = logging.getLogger(__name__)

WIB = pytz.timezone("Asia/Jakarta")


class ScanScheduler:
    """
    Scheduler untuk otomasi scan dan pengiriman sinyal.

    Jadwal default:
    - Scan cepat   : Setiap 15 menit saat jam bursa
    - Scan penuh   : Setiap 30 menit saat jam bursa
    - Notif summary: 09:05, 11:00, 13:35, 14:30
    - Market open  : 09:00 (notif pasar buka)
    - Market close : 15:05 (notif pasar tutup)
    """

    def __init__(
        self,
        scanner: StockScanner,
        fetcher: StockDataFetcher,
        telegram_token: str,
        chat_ids: List[Union[str, int]],
        scan_interval_minutes: int = 15
    ):
        self.scanner = scanner
        self.fetcher = fetcher
        self.telegram_token = telegram_token
        self.chat_ids = chat_ids
        self.scan_interval = scan_interval_minutes
        self.scheduler = AsyncIOScheduler(timezone=WIB)
        self._is_running = False

    def setup_jobs(self):
        """Daftarkan semua jobs ke scheduler."""

        # ╔══════════════════════════════════════════════════════╗
        # ║  FETCH DATA + SCAN SETIAP 15 MENIT (jam bursa BEI) ║
        # ║  Urutan:                                             ║
        # ║    1. update_latest() → perbarui Parquet store      ║
        # ║    2. scan_all()      → baca dari store (cepat)     ║
        # ║    3. Kirim sinyal terbaik ke Telegram               ║
        # ╚══════════════════════════════════════════════════════╝
        self.scheduler.add_job(
            self._job_fetch_and_scan,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour="9-14",
                minute="5,20,35,50",
                timezone=WIB,
            ),
            id="fetch_and_scan_15min",
            name="Fetch Data + Scan 15 Menit",
            max_instances=1,
            misfire_grace_time=120,
        )

        # ╔══════════════════════════════════════╗
        # ║  NOTIFIKASI KHUSUS                   ║
        # ╚══════════════════════════════════════╝
        # Opening bell
        self.scheduler.add_job(
            self._job_market_open,
            trigger=CronTrigger(
                day_of_week="mon-fri", hour=9, minute=0, timezone=WIB
            ),
            id="market_open",
            name="Notif Market Open"
        )

        # Pre-close reminder (14:45)
        self.scheduler.add_job(
            self._job_pre_close,
            trigger=CronTrigger(
                day_of_week="mon-fri", hour=14, minute=45, timezone=WIB
            ),
            id="pre_close",
            name="Notif Pre-Close"
        )

        # Closing bell
        self.scheduler.add_job(
            self._job_market_close,
            trigger=CronTrigger(
                day_of_week="mon-fri", hour=15, minute=5, timezone=WIB
            ),
            id="market_close",
            name="Notif Market Close"
        )

        logger.info(
            f"Jobs terdaftar: {len(self.scheduler.get_jobs())} job aktif")

    async def _job_fetch_and_scan(self):
        """
        Job utama (data-first):
          1. Update Parquet store → ambil candle terbaru dari yfinance
          2. Scan saham    → baca dari store (cepat, tanpa API call live)
          3. Notifikasi    → kirim sinyal terbaik ke Telegram
        """
        now_str = datetime.now(WIB).strftime("%H:%M WIB")
        logger.info(f"[SCHEDULER] Job fetch+scan dimulai ({now_str})")

        if not self.fetcher.is_market_open():
            logger.info("[SCHEDULER] Pasar tutup, job dilewati")
            return

        try:
            from data.crawler import get_crawler
            from data.stock_list import IDX_UNIVERSE

            # ── Tahap 1: Update store ─────────────────────────────
            logger.info("[SCHEDULER] Tahap 1 — Update data store ...")
            crawler = get_crawler()
            loop = asyncio.get_event_loop()
            update_result = await loop.run_in_executor(
                None,
                lambda: crawler.update_latest(IDX_UNIVERSE, interval="5m")
            )
            logger.info(
                f"[SCHEDULER] Store diperbarui: "
                f"{update_result.get('updated', 0)} ticker, "
                f"+{update_result.get('new_rows', 0)} baris baru"
            )

            # ── Tahap 2: Scan dari store ─────────────────────────
            logger.info("[SCHEDULER] Tahap 2 — Scan saham dari store ...")
            from telegram_bot.bot import TelegramNotifier
            from telegram_bot.formatter import TelegramFormatter

            notifier = TelegramNotifier(self.telegram_token, self.chat_ids)
            formatter = TelegramFormatter()

            signals = await self.scanner.scan_all_async(min_score=60)

            if not signals:
                logger.info("[SCHEDULER] Tidak ada sinyal memenuhi kriteria")
                return

            market = self.fetcher.get_market_status()

            # ── Tahap 3: Notifikasi ──────────────────────────────
            await notifier.send_summary(signals, market)
            await asyncio.sleep(2)

            top_buy = [s for s in signals if s.signal_type == "BUY"][:3]
            if top_buy:
                sent = await notifier.send_signals_batch(top_buy, max_signals=3)
                logger.info(
                    f"[SCHEDULER] {sent} sinyal BUY dikirim ke Telegram")

            warn_count = sum(1 for s in signals if s.signal_type == "WASPADA")
            if warn_count:
                logger.info(
                    f"[SCHEDULER] {warn_count} sinyal WASPADA disertakan dalam summary"
                )

        except Exception as e:
            logger.error(
                f"[SCHEDULER] Error job fetch+scan: {e}", exc_info=True)
            try:
                from logs.error_tracker import tracker
                tracker.track("scheduler", "job_fetch_and_scan", e)
            except Exception:
                pass

    # ── Alias untuk kompatibilitas backward ──────────────────────────────────
    async def _job_scan_and_notify(self):
        """Alias menuju _job_fetch_and_scan (backward compat)."""
        await self._job_fetch_and_scan()

    async def _job_market_open(self):
        """Notifikasi pasar buka + scan awal."""
        logger.info("[SCHEDULER] Pasar BEI BUKA")
        try:
            from telegram_bot.bot import TelegramNotifier
            notifier = TelegramNotifier(self.telegram_token, self.chat_ids)

            now = datetime.now(WIB).strftime("%d/%m/%Y")
            await notifier.send_message(
                f"🟢 <b>PASAR BEI DIBUKA!</b>\n"
                f"📅 {now}\n"
                f"⏰ 09:00 WIB — Sesi 1 dimulai\n\n"
                f"🔄 Scan otomatis setiap <b>15 menit</b>\n"
                f"🟢 Sinyal BUY dilengkapi Entry / TP / SL\n"
                f"🔴 Sinyal WASPADA — kondisi bearish, hindari beli\n\n"
                f"💡 Gunakan /scan untuk sinyal terkini"
            )
        except Exception as e:
            logger.error(f"[SCHEDULER] Error market open notif: {e}")

    async def _job_pre_close(self):
        """Notifikasi 15 menit sebelum penutupan."""
        logger.info("[SCHEDULER] Pre-close notification")
        try:
            from telegram_bot.bot import TelegramNotifier
            notifier = TelegramNotifier(self.telegram_token, self.chat_ids)

            await notifier.send_message(
                "⚠️ <b>PERHATIAN: Pasar tutup dalam 15 MENIT!</b>\n\n"
                "⏰ Sesi 2 berakhir pukul 15:00 WIB\n"
                "💼 Pertimbangkan untuk :\n"
                "• Menutup posisi intraday\n"
                "• Lock profit jika sudah dapat TP\n"
                "• Jangan buka posisi baru terlalu dekat close\n\n"
                "🛡️ <i>Manajemen risiko adalah prioritas!</i>"
            )
        except Exception as e:
            logger.error(f"[SCHEDULER] Error pre-close notif: {e}")

    async def _job_market_close(self):
        """Notifikasi penutupan pasar."""
        logger.info("[SCHEDULER] Pasar BEI TUTUP")
        try:
            from telegram_bot.bot import TelegramNotifier
            notifier = TelegramNotifier(self.telegram_token, self.chat_ids)

            await notifier.send_message(
                "🔴 <b>PASAR BEI DITUTUP</b>\n\n"
                "⏰ 15:00 WIB - Sesi 2 berakhir\n"
                "📊 Screener berhenti hingga besok\n\n"
                "💡 <i>Gunakan waktu ini untuk:\n"
                "• Review trading hari ini\n"
                "• Analisis saham untuk besok\n"
                "• Update watchlist Anda</i>\n\n"
                "Sampai besok! 👋"
            )
        except Exception as e:
            logger.error(f"[SCHEDULER] Error market close notif: {e}")

    def start(self):
        """Mulai scheduler."""
        self.setup_jobs()
        self.scheduler.start()
        self._is_running = True
        logger.info("Scheduler berhasil dimulai")

    def stop(self):
        """Hentikan scheduler."""
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("Scheduler dihentikan")

    def get_jobs_info(self) -> list:
        """Informasi semua job aktif."""
        jobs = []
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run.isoformat() if next_run else None,
            })
        return jobs
