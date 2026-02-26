"""
Job Scheduler - Data fetch harian + scan pagi hari

Jadwal baru (data-first, hemat API):
  
    04:00 WIB  (Senin-Jumat)                                     
       DataCrawler.update_latest()  perbarui candle terbaru    
       Semua interval: 5m, 15m, 1h, 1d                         
  
  
    06:00 WIB  (Senin-Jumat)                                     
       StockScanner.scan_all_async()                            
       Kirim max 10 BUY + max 10 WASPADA ke Telegram           
  
  
    Notifikasi Market (Senin-Jumat)                              
      09:00  Pasar BUKA                                         
      15:45  Pre-close reminder                                  
      16:00  Pasar TUTUP                                        
  
"""

import asyncio
import logging
from typing import List, Union
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import pytz

from screener.scanner import StockScanner
from data.fetcher import StockDataFetcher
from telegram_bot.notifier_runner import run_notification

logger = logging.getLogger(__name__)

WIB = pytz.timezone("Asia/Jakarta")

#  Limit sinyal harian
MAX_BUY_PER_DAY = 10   # Maksimal sinyal BUY yang dikirim setiap pagi
MAX_WASPADA_PER_DAY = 10  # Maksimal sinyal WASPADA yang dikirim setiap pagi
MIN_SCORE = 50   # Confidence minimum (%)


class ScanScheduler:
    """
    Scheduler untuk otomasi fetch data & pengiriman sinyal harian.

    Jadwal:
      04:00  Update store (ambil candle terbaru)
      06:00  Scan + kirim sinyal (max 10 BUY + 10 WASPADA)
      09:00  Notif pasar buka
      15:45  Notif pre-close
      16:00  Notif pasar tutup
    """

    def __init__(
        self,
        scanner: StockScanner,
        fetcher: StockDataFetcher,
        telegram_token: str,
        chat_ids: List[Union[str, int]],
        scan_interval_minutes: int = 15,   # diabaikan, tetap ada untuk kompatibilitas
    ):
        self.scanner = scanner
        self.fetcher = fetcher
        self.telegram_token = telegram_token
        self.chat_ids = chat_ids
        self.scheduler = AsyncIOScheduler(timezone=WIB)
        self._is_running = False

    def setup_jobs(self):
        """Daftarkan semua jobs ke scheduler."""

        #  04:00  Update data store
        self.scheduler.add_job(
            self._job_daily_fetch,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=4, minute=0,
                timezone=WIB,
            ),
            id="daily_fetch",
            name="04:00  Update Data Store",
            max_instances=1,
            misfire_grace_time=600,
        )

        #  06:00  Scan + kirim sinyal
        self.scheduler.add_job(
            self._job_morning_scan,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=6, minute=0,
                timezone=WIB,
            ),
            id="morning_scan",
            name="06:00  Scan Pagi + Kirim Sinyal",
            max_instances=1,
            misfire_grace_time=300,
        )

        #  09:00  Market open
        self.scheduler.add_job(
            self._job_market_open,
            trigger=CronTrigger(
                day_of_week="mon-fri", hour=9, minute=0, timezone=WIB
            ),
            id="market_open",
            name="09:00  Notif Market Open"
        )

        #  15:45  Pre-close reminder
        self.scheduler.add_job(
            self._job_pre_close,
            trigger=CronTrigger(
                day_of_week="mon-fri", hour=15, minute=45, timezone=WIB
            ),
            id="pre_close",
            name="15:45  Notif Pre-Close"
        )

        #  16:00  Market close
        self.scheduler.add_job(
            self._job_market_close,
            trigger=CronTrigger(
                day_of_week="mon-fri", hour=16, minute=0, timezone=WIB
            ),
            id="market_close",
            name="16:00  Notif Market Close"
        )

        logger.info(
            f"Scheduler siap: {len(self.scheduler.get_jobs())} job aktif")

    #  JOB: 04:00  Update data store

    async def _job_daily_fetch(self):
        """
        Jalankan setiap 04:00 WIB.
        Ambil candle terbaru dari Yahoo Finance untuk seluruh universe saham
        dan upsert ke Parquet store.  Tidak mengirim Telegram.
        """
        start_t = datetime.now(WIB).strftime("%H:%M WIB")
        logger.info(f"[04:00] Job daily_fetch dimulai ({start_t})")

        try:
            from data.crawler import get_crawler
            from data.stock_list import get_effective_universe

            crawler = get_crawler()
            universe = get_effective_universe()
            loop = asyncio.get_event_loop()

            # Update semua interval yang disimpan di store
            for interval in ("5m", "15m", "1h", "1d"):
                logger.info(f"[04:00] Update interval {interval} ...")
                result = await loop.run_in_executor(
                    None,
                    lambda iv=interval: crawler.update_latest(
                        universe, interval=iv
                    )
                )
                logger.info(
                    f"[04:00]  [{interval}] "
                    f"updated={result.get('updated', 0)}, "
                    f"new_rows={result.get('new_rows', 0)}, "
                    f"failed={result.get('failed', 0)}"
                )

            logger.info("[04:00] Data store berhasil diperbarui")

        except Exception as e:
            logger.error(f"[04:00] Error job daily_fetch: {e}", exc_info=True)
            try:
                from logs.error_tracker import tracker
                tracker.track("scheduler", "daily_fetch", e)
            except Exception:
                pass

    #  JOB: 06:00  Scan pagi + kirim sinyal

    async def _job_morning_scan(self):
        """
        Jalankan setiap 06:00 WIB.
        Scan seluruh universe dari store, kirim:
           Max 10 sinyal BUY  (confidence >= MIN_SCORE)
           Max 10 sinyal WASPADA (confidence >= MIN_SCORE)
        """
        start_t = datetime.now(WIB).strftime("%H:%M WIB")
        logger.info(f"[06:00] Job morning_scan dimulai ({start_t})")

        try:
            from telegram_bot.bot import TelegramNotifier
            from telegram_bot.formatter import TelegramFormatter

            notifier = TelegramNotifier(self.telegram_token, self.chat_ids)
            formatter = TelegramFormatter()

            #  Scan
            logger.info("[06:00] Memulai scan ...")
            signals = await self.scanner.scan_all_async(min_score=MIN_SCORE)

            buy_signals = [s for s in signals if s.signal_type ==
                           "BUY"][:MAX_BUY_PER_DAY]
            waspada_signals = [
                s for s in signals if s.signal_type == "WASPADA"][:MAX_WASPADA_PER_DAY]

            logger.info(
                f"[06:00] Scan selesai  "
                f"BUY: {len(buy_signals)}, WASPADA: {len(waspada_signals)}"
            )

            if not buy_signals and not waspada_signals:
                logger.info("[06:00] Tidak ada sinyal, tidak kirim Telegram")
                return

            #  Header ringkasan pagi
            tanggal = datetime.now(WIB).strftime("%d/%m/%Y")
            header = (
                f" <b>SINYAL PAGI  {tanggal}</b>\n"
                f"\n"
                f" BUY      : <b>{len(buy_signals)}</b> saham\n"
                f" WASPADA  : <b>{len(waspada_signals)}</b> saham\n"
                f" Min Score: {MIN_SCORE}/100\n\n"
                f" Data diperbarui pukul 04:00 WIB\n"
                f" Gunakan /buy atau /waspada untuk detil"
            )
            await notifier.send_message(header)
            await asyncio.sleep(2)

            #  Kirim detail sinyal BUY
            if buy_signals:
                await notifier.send_message(" <b>SINYAL BUY HARI INI:</b>")
                await asyncio.sleep(1)
                for sig in buy_signals:
                    await notifier.send_message(formatter.format_signal(sig))
                    await asyncio.sleep(1.2)

            #  Kirim rangkuman WASPADA (satu pesan ringkas)
            if waspada_signals:
                await asyncio.sleep(1)
                w_msg = " <b>SAHAM WASPADA HARI INI:</b>\n"
                w_msg += " <i>Hindari posisi baru pada saham berikut:</i>\n\n"
                for s in waspada_signals:
                    chg_icon = "" if s.change_pct < 0 else ""
                    w_msg += (
                        f" <b>{s.ticker_clean}</b> ({s.company_name[:18]}) "
                        f"{chg_icon} {s.change_pct:+.1f}% | "
                        f"RSI {s.rsi:.0f} | Skor {s.signal_score}\n"
                    )
                w_msg += "\n Gunakan /signal [KODE] untuk analisis detail"
                await notifier.send_message(w_msg)

            logger.info(
                f"[06:00] Sinyal terkirim: "
                f"{len(buy_signals)} BUY + {len(waspada_signals)} WASPADA"
            )

        except Exception as e:
            logger.error(
                f"[06:00] Error job morning_scan: {e}", exc_info=True)
            try:
                from logs.error_tracker import tracker
                tracker.track("scheduler", "morning_scan", e)
            except Exception:
                pass

    #  Alias backward-compat

    async def _job_fetch_and_scan(self):
        """Alias lama  arahkan ke morning_scan."""
        await self._job_morning_scan()

    async def _job_scan_and_notify(self):
        """Alias lama."""
        await self._job_morning_scan()

    #  Notifikasi market

    async def _job_market_open(self):
        """09:00  Notifikasi pasar buka."""
        logger.info("[SCHEDULER] Pasar BEI BUKA")
        try:
            from telegram_bot.bot import TelegramNotifier
            notifier = TelegramNotifier(self.telegram_token, self.chat_ids)
            tanggal = datetime.now(WIB).strftime("%d/%m/%Y")
            await notifier.send_message(
                f" <b>PASAR BEI DIBUKA!</b>\n"
                f" {tanggal}   09:00 WIB\n\n"
                f" Sinyal pagi sudah dikirim jam 06:00\n"
                f" Gunakan /buy untuk sinyal BUY hari ini\n"
                f" Gunakan /waspada untuk saham yang perlu dihindari\n"
                f" Gunakan /info [KODE] untuk analisis mendalam satu saham"
            )
        except Exception as e:
            logger.error(f"[SCHEDULER] Error market open notif: {e}")

    async def _job_pre_close(self):
        """15:45  Notifikasi 15 menit sebelum tutup."""
        logger.info("[SCHEDULER] Pre-close notification")
        try:
            from telegram_bot.bot import TelegramNotifier
            notifier = TelegramNotifier(self.telegram_token, self.chat_ids)
            await notifier.send_message(
                " <b>PASAR TUTUP DALAM 15 MENIT!</b>\n\n"
                " Sesi 2 berakhir pukul 16:00 WIB\n"
                " Pertimbangkan untuk:\n"
                " Menutup posisi intraday yang masih terbuka\n"
                " Lock profit jika sudah mencapai TP\n"
                " Jangan buka posisi baru terlalu dekat close\n\n"
                " <i>Manajemen risiko adalah segalanya!</i>"
            )
        except Exception as e:
            logger.error(f"[SCHEDULER] Error pre-close notif: {e}")

    async def _job_market_close(self):
        """16:00  Notifikasi pasar tutup."""
        logger.info("[SCHEDULER] Pasar BEI TUTUP")
        try:
            from telegram_bot.bot import TelegramNotifier
            notifier = TelegramNotifier(self.telegram_token, self.chat_ids)
            await notifier.send_message(
                " <b>PASAR BEI DITUTUP</b>\n\n"
                " 16:00 WIB  Sesi 2 berakhir\n"
                " Sinyal berikutnya dikirim besok pukul 06:00 WIB\n\n"
                " <i>Gunakan waktu untuk:\n"
                " Review trading hari ini\n"
                " Analisis watchlist untuk besok\n"
                " Cek /info [KODE] saham yang menarik</i>\n\n"
                "Sampai besok! "
            )
        except Exception as e:
            logger.error(f"[SCHEDULER] Error market close notif: {e}")

    #  Lifecycle

    def start(self):
        self.setup_jobs()
        self.scheduler.start()
        self._is_running = True
        logger.info("Scheduler berhasil dimulai")

    def stop(self):
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("Scheduler dihentikan")

    def get_jobs_info(self) -> list:
        jobs = []
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run.isoformat() if next_run else None,
            })
        return jobs
