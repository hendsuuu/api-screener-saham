"""
Job Scheduler - Menjalankan scan otomatis pada interval tertentu
Hanya aktif saat jam bursa BEI
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

        # ╔══════════════════════════════════════╗
        # ║  SCAN OTOMATIS (setiap N menit)      ║
        # ╚══════════════════════════════════════╝
        # Sesi 1: 09:05 - 11:25
        self.scheduler.add_job(
            self._job_scan_and_notify,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour="9-11",
                minute=f"5,{5 + self.scan_interval},{5 + 2*self.scan_interval},{5 + 3*self.scan_interval}",
                timezone=WIB
            ),
            id="scan_sesi1",
            name="Scan Sesi 1",
            max_instances=1,
            misfire_grace_time=60
        )

        # Sesi 2: 13:35 - 14:45
        self.scheduler.add_job(
            self._job_scan_and_notify,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour="13,14",
                minute=f"35,50",
                timezone=WIB
            ),
            id="scan_sesi2",
            name="Scan Sesi 2",
            max_instances=1,
            misfire_grace_time=60
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

    async def _job_scan_and_notify(self):
        """Job utama: scan + kirim sinyal terbaik."""
        logger.info(
            f"[SCHEDULER] Memulai scan otomatis ({datetime.now(WIB).strftime('%H:%M WIB')})")

        if not self.fetcher.is_market_open():
            logger.info("[SCHEDULER] Pasar tutup, scan dilewati")
            return

        try:
            from telegram_bot.bot import TelegramNotifier
            from telegram_bot.formatter import TelegramFormatter

            notifier = TelegramNotifier(self.telegram_token, self.chat_ids)
            formatter = TelegramFormatter()

            # Scan semua saham
            signals = await self.scanner.scan_all_async(min_score=60)

            if not signals:
                logger.info("[SCHEDULER] Tidak ada sinyal memenuhi kriteria")
                return

            market = self.fetcher.get_market_status()

            # Kirim ringkasan
            await notifier.send_summary(signals, market)
            await asyncio.sleep(2)

            # Kirim top 3 sinyal detail
            top3 = signals[:3]
            sent = await notifier.send_signals_batch(top3, max_signals=3)
            logger.info(f"[SCHEDULER] {sent} sinyal dikirim ke Telegram")

        except Exception as e:
            logger.error(f"[SCHEDULER] Error job scan: {e}", exc_info=True)

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
                f"⏰ 09:00 WIB - Sesi 1 dimulai\n\n"
                f"📊 Screener aktif setiap 15 menit\n"
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
