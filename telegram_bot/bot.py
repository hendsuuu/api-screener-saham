"""
Telegram Bot Handler - Mengirim notifikasi sinyal ke Telegram
Menggunakan python-telegram-bot v20+
"""

import asyncio
import logging
from typing import List, Optional, Union

from telegram import Bot, Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

from screener.signal_generator import ScalpSignal
from screener.scanner import StockScanner
from data.fetcher import StockDataFetcher
from data.stock_list import get_yahoo_symbol, IDX_UNIVERSE
from telegram_bot.formatter import TelegramFormatter

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Pengelola notifikasi Telegram.
    Mengirim sinyal ke grup atau chat pribadi.
    """

    def __init__(self, token: str, chat_ids: List[Union[str, int]]):
        """
        Args:
            token: Token bot dari @BotFather
            chat_ids: List chat ID grup atau user yang menerima notif
                      Grup: gunakan negatif ID (-100xxx)
                      Pribadi: gunakan user ID positif
        """
        self.token = token
        self.chat_ids = [str(cid) for cid in chat_ids]
        self.bot = Bot(token=token)
        self.formatter = TelegramFormatter()

    async def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: str = ParseMode.HTML
    ) -> bool:
        """
        Kirim pesan ke satu chat atau semua target.

        Args:
            text: Isi pesan (HTML)
            chat_id: ID target (None = kirim ke semua)
        """
        targets = [chat_id] if chat_id else self.chat_ids

        success = True
        for cid in targets:
            try:
                # Potong pesan jika terlalu panjang (limit Telegram 4096 char)
                if len(text) > 4096:
                    chunks = [text[i:i+4096]
                              for i in range(0, len(text), 4096)]
                    for chunk in chunks:
                        await self.bot.send_message(
                            chat_id=cid,
                            text=chunk,
                            parse_mode=parse_mode
                        )
                else:
                    await self.bot.send_message(
                        chat_id=cid,
                        text=text,
                        parse_mode=parse_mode
                    )
                logger.info(f"Pesan terkirim ke {cid}")
            except TelegramError as e:
                logger.error(f"Gagal kirim ke {cid}: {e}")
                success = False

        return success

    async def send_signal(self, signal: ScalpSignal) -> bool:
        """Kirim satu sinyal scalping ke semua target."""
        text = self.formatter.format_signal(signal)
        return await self.send_message(text)

    async def send_signals_batch(self, signals: List[ScalpSignal], max_signals: int = 5) -> int:
        """
        Kirim batch sinyal ke semua target.

        Args:
            signals: List sinyal terurut dari yang terbaik
            max_signals: Maksimal sinyal yang dikirim

        Returns:
            Jumlah sinyal yang berhasil dikirim
        """
        sent = 0
        top_signals = signals[:max_signals]

        for signal in top_signals:
            success = await self.send_signal(signal)
            if success:
                sent += 1
            # Jeda 1 detik antar pesan untuk menghindari rate limit
            await asyncio.sleep(1)

        return sent

    async def send_summary(self, signals: List[ScalpSignal], market_status: dict) -> bool:
        """Kirim ringkasan hasil scan."""
        text = self.formatter.format_summary(signals, market_status)
        return await self.send_message(text)

    async def send_market_closed(self) -> bool:
        """Kirim notifikasi pasar tutup."""
        text = self.formatter.format_market_closed()
        return await self.send_message(text)

    async def test_connection(self) -> bool:
        """Test koneksi bot ke Telegram."""
        try:
            me = await self.bot.get_me()
            logger.info(f"Bot terhubung: @{me.username}")
            return True
        except TelegramError as e:
            logger.error(f"Gagal terhubung ke Telegram: {e}")
            return False


class TelegramBotHandler:
    """
    Handler command interaktif bot Telegram.
    User bisa request sinyal secara manual.
    """

    def __init__(
        self,
        token: str,
        chat_ids: List[Union[str, int]],
        scanner: Optional[StockScanner] = None
    ):
        self.token = token
        self.chat_ids = chat_ids
        self.scanner = scanner or StockScanner()
        self.fetcher = StockDataFetcher()
        self.notifier = TelegramNotifier(token, chat_ids)
        self.formatter = TelegramFormatter()
        self.app: Optional[Application] = None

    def build_app(self) -> Application:
        """Buat dan konfigurasi aplikasi bot."""
        self.app = Application.builder().token(self.token).build()

        # Daftarkan command handlers
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("scan", self.cmd_scan))
        self.app.add_handler(CommandHandler("top", self.cmd_top))
        self.app.add_handler(CommandHandler("signal", self.cmd_signal))
        self.app.add_handler(CommandHandler("buy", self.cmd_buy))
        self.app.add_handler(CommandHandler("waspada", self.cmd_waspada))
        self.app.add_handler(CommandHandler("sell", self.cmd_waspada))  # alias lama
        self.app.add_handler(CommandHandler("market", self.cmd_market))

        # Handler pesan tidak dikenal
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND,
                           self.handle_unknown)
        )

        return self.app

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pesan selamat datang."""
        welcome = """
� <b>IDX SCALPER BOT</b> 🇨🇮
━━━━━━━━━━━━━━━━━━━━
🤖 Bot screener saham IDX untuk strategi <b>scalping intraday</b>.

<b>🟢 Sinyal BUY — Lengkap dengan:</b>
• Entry Zone, TP1/TP2/TP3, Stop Loss
• Risk:Reward minimum 1:2
• Estimasi profit per lot (100 lembar)

<b>🔴 Sinyal WASPADA — Peringatan teknikal:</b>
• Kondisi bearish terdeteksi — hindari beli
• <i>Di BEI tidak ada short-selling</i>, jadi TIDAK ada
  sinyal jual/short. Hanya peringatan.

<b>⚙️ Cara kerja:</b>
• Pre-screen ~342 saham IDX setiap scan
• Analisis teknikal 5m: RSI, MACD, BB, VWAP, ADX, SuperTrend
• Notifikasi otomatis setiap <b>15 menit</b> saat bursa buka
• Jam bursa: Sesi 1 (09:00–11:30) | Sesi 2 (13:30–15:00) WIB

Ketik /help untuk daftar lengkap perintah.
Ketik /scan untuk mulai scan sekarang!
""".strip()
        await update.message.reply_text(welcome, parse_mode=ParseMode.HTML)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tampilkan bantuan."""
        await update.message.reply_text(
            self.formatter.format_help(),
            parse_mode=ParseMode.HTML
        )

    async def cmd_market(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Status pasar dan ringkasan."""
        market = self.fetcher.get_market_status()
        summary = self.scanner.get_market_summary()

        status_emoji = "🟢" if market.get("is_open") else "🔴"
        msg = f"""
{status_emoji} <b>STATUS PASAR BEI</b>
━━━━━━━━━━━━━━━━━━━━
📅 {market.get('date')}
⏰ {market.get('time_wib')}
📊 Status : <b>{market.get('status')}</b>
""".strip()

        if summary.get("total_signals", 0) > 0:
            buy_n = summary.get('buy_signals', 0)
            warn_n = summary.get('sell_signals', 0)  # masih dikembalikan sebagai sell_signals dari scanner
            msg += f"""

📈 <b>RINGKASAN SCAN TERAKHIR</b>
🎯 Market Bias    : {summary.get('market_bias')}
📊 Total Sinyal   : {summary.get('total_signals')}
🟢 BUY            : {buy_n}
🔴 WASPADA        : {warn_n}
⏰ Scan Time      : {summary.get('scan_time', 'N/A')}"""

        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    async def cmd_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Jalankan scan manual."""
        await update.message.reply_text(
            "⏳ <b>Memulai scan...</b>\nProses ini membutuhkan ~1-2 menit. Harap tunggu...",
            parse_mode=ParseMode.HTML
        )

        try:
            signals = await self.scanner.scan_all_async(min_score=50)
            market = self.fetcher.get_market_status()

            if not signals:
                await update.message.reply_text(
                    "ℹ️ Tidak ada sinyal yang memenuhi kriteria saat ini.\n"
                    "Pasar mungkin sedang sideways atau data terbatas.",
                    parse_mode=ParseMode.HTML
                )
                return

            # Kirim ringkasan
            summary_text = self.formatter.format_summary(signals, market)
            await update.message.reply_text(summary_text, parse_mode=ParseMode.HTML)

            # Kirim top 3 sinyal terbaik
            await asyncio.sleep(1)
            for signal in signals[:3]:
                detail = self.formatter.format_signal(signal)
                await update.message.reply_text(detail, parse_mode=ParseMode.HTML)
                await asyncio.sleep(0.8)

        except Exception as e:
            logger.error(f"Error cmd_scan: {e}")
            await update.message.reply_text(
                f"❌ Error saat scan: {str(e)[:200]}",
                parse_mode=ParseMode.HTML
            )

    async def cmd_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tampilkan top sinyal dari scan terakhir."""
        top = self.scanner.get_top_signals(5)

        if not top:
            await update.message.reply_text(
                "ℹ️ Belum ada data scan. Gunakan /scan terlebih dahulu.",
                parse_mode=ParseMode.HTML
            )
            return

        for signal in top:
            detail = self.formatter.format_signal(signal)
            await update.message.reply_text(detail, parse_mode=ParseMode.HTML)
            await asyncio.sleep(0.5)

    async def cmd_signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Dapatkan sinyal untuk saham tertentu. Contoh: /signal BBCA"""
        if not context.args:
            await update.message.reply_text(
                "❌ Harap sertakan kode saham.\nContoh: <code>/signal BBCA</code>",
                parse_mode=ParseMode.HTML
            )
            return

        ticker_raw = context.args[0].upper().strip()
        ticker = get_yahoo_symbol(ticker_raw)

        await update.message.reply_text(
            f"⏳ Menganalisis <b>{ticker_raw}</b>...",
            parse_mode=ParseMode.HTML
        )

        try:
            signal = self.scanner.scan_single_stock(ticker_raw)

            if signal:
                detail = self.formatter.format_signal(signal)
                await update.message.reply_text(detail, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(
                    f"ℹ️ Tidak ada sinyal kuat untuk <b>{ticker_raw}</b> saat ini.\n"
                    f"Kondisi mungkin sideways atau tidak memenuhi kriteria.",
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            await update.message.reply_text(
                f"❌ Error: {str(e)[:200]}",
                parse_mode=ParseMode.HTML
            )

    async def cmd_buy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tampilkan sinyal BUY saja."""
        buy_signals = [
            s for s in self.scanner.last_scan_results if s.signal_type == "BUY"]

        if not buy_signals:
            await update.message.reply_text(
                "ℹ️ Tidak ada sinyal BUY. Gunakan /scan untuk memperbarui.",
                parse_mode=ParseMode.HTML
            )
            return

        msg = "🟢 <b>SINYAL BUY AKTIF:</b>\n\n"
        for s in buy_signals[:5]:
            def fmt(p):
                return f"Rp {int(p):,}".replace(",", ".")
            msg += (
                f"• <b>{s.ticker_clean}</b> | "
                f"Entry: {fmt(s.entry_price)} | TP2: {fmt(s.tp2)} | SL: {fmt(s.sl)} | "
                f"Skor: {s.signal_score}/100\n"
            )

        msg += "\n💡 Gunakan /signal [KODE] untuk detail lengkap"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    async def cmd_waspada(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tampilkan sinyal WASPADA (kondisi bearish)."""
        warn_signals = [
            s for s in self.scanner.last_scan_results if s.signal_type == "WASPADA"]

        if not warn_signals:
            await update.message.reply_text(
                "ℹ️ Tidak ada sinyal WASPADA saat ini. Gunakan /scan untuk memperbarui.",
                parse_mode=ParseMode.HTML
            )
            return

        msg = "🔴 <b>SAHAM KONDISI WASPADA:</b>\n"
        msg += "⚠️ <i>Di BEI tidak ada short-selling. Hindari posisi baru pada saham berikut:</i>\n\n"
        for s in warn_signals[:8]:
            alasan = s.reasons[1][:60] if len(s.reasons) > 1 else "kondisi teknikal memburuk"
            msg += (
                f"• <b>{s.ticker_clean}</b> ({s.company_name}) | "
                f"Harga: Rp {int(s.current_price):,} | "
                f"Skor: {s.signal_score}/100\n"
                f"  ↳ {alasan}\n"
            )

        msg += "\n💡 Gunakan /signal [KODE] untuk analisis lengkap"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    async def handle_unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle pesan yang bukan command."""
        text = update.message.text.upper().strip().replace(".JK", "")
        # Kalau user kirim kode saham langsung, langsung analisis
        if len(text) <= 6 and text.isalpha():
            context.args = [text]
            await self.cmd_signal(update, context)
        else:
            await update.message.reply_text(
                "❓ Perintah tidak dikenali.\nKetik /help untuk daftar perintah.",
                parse_mode=ParseMode.HTML
            )

    def run_polling(self):
        """Jalankan bot dalam mode polling (untuk development)."""
        app = self.build_app()
        logger.info("Bot berjalan dalam mode polling...")
        app.run_polling(drop_pending_updates=True)
