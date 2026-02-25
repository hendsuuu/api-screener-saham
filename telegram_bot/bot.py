"""
Telegram Bot Handler - Mengirim notifikasi sinyal ke Telegram
Menggunakan python-telegram-bot v20+
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import List, Optional, Union

from telegram import Bot, Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

from config import settings
from screener.signal_generator import ScalpSignal
from screener.scanner import StockScanner
from data.fetcher import StockDataFetcher
from data.stock_list import get_yahoo_symbol, IDX_UNIVERSE
from telegram_bot.formatter import TelegramFormatter

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN AUTH
# ─────────────────────────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    """Cek apakah user_id ada di ADMIN_CHAT_IDS."""
    return user_id in settings.ADMIN_CHAT_IDS


async def _require_admin(update: Update) -> bool:
    """Kirim pesan 403 jika bukan admin, kembalikan False."""
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text(
            "⛔ Perintah ini hanya untuk admin bot.",
            parse_mode=ParseMode.HTML,
        )
        return False
    return True


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
        self.app.add_handler(CommandHandler("info", self.cmd_info))
        self.app.add_handler(CommandHandler("buy", self.cmd_buy))
        self.app.add_handler(CommandHandler("waspada", self.cmd_waspada))
        self.app.add_handler(CommandHandler("sell", self.cmd_waspada))  # alias lama
        self.app.add_handler(CommandHandler("market", self.cmd_market))
        # Admin commands (hanya ADMIN_CHAT_IDS)
        self.app.add_handler(CommandHandler("admin", self.cmd_admin))

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
• Jam bursa: Sesi 1 (09:00–11:30) | Sesi 2 (13:30–16:00) WIB

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
            signals = await self.scanner.scan_all_async(
                min_score=settings.MIN_SIGNAL_SCORE
            )
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

            # Kirim top 3 sinyal BUY detail (auto-sorted by score)
            buy_signals = [s for s in signals if s.signal_type == "BUY"][:3]
            warn_signals = [s for s in signals if s.signal_type == "WASPADA"][:2]

            await asyncio.sleep(1)
            for signal in buy_signals:
                detail = self.formatter.format_signal(signal)
                await update.message.reply_text(detail, parse_mode=ParseMode.HTML)
                await asyncio.sleep(0.8)

            # Kirim max 2 sinyal WASPADA sebagai ringkasan satu pesan
            if warn_signals:
                await asyncio.sleep(0.5)
                warn_msg = "🔴 <b>SAHAM WASPADA SCAN INI:</b>\n"
                for s in warn_signals:
                    warn_msg += f"  • <b>{s.ticker_clean}</b> Rp {int(s.current_price):,} | RSI {s.rsi:.0f} | Skor {s.signal_score}\n"
                warn_msg += "\nGunakan /waspada untuk daftar lengkap"
                await update.message.reply_text(warn_msg, parse_mode=ParseMode.HTML)

        except Exception as e:
            logger.error(f"Error cmd_scan: {e}")
            await update.message.reply_text(
                f"❌ Error saat scan: {str(e)[:200]}",
                parse_mode=ParseMode.HTML
            )

    async def cmd_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tampilkan top sinyal dari scan terakhir (termasuk dari cache disk)."""
        top = self.scanner.get_top_signals(5)

        if not top:
            await update.message.reply_text(
                "ℹ️ Belum ada data scan hari ini.\n"
                "Gunakan /scan untuk mulai screening.",
                parse_mode=ParseMode.HTML
            )
            return

        await update.message.reply_text(
            f"📊 <b>TOP {len(top)} SINYAL HARI INI</b>",
            parse_mode=ParseMode.HTML
        )
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

    async def cmd_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Analisis mendalam satu saham.
        Contoh: /info BBCA

        Menampilkan:
          - Trend (bullish/bearish/sideways) + alignment EMA
          - Area support & resistance (swing high/low + EMA)
          - Potensi ke depan berdasarkan indikator
          - Risiko utama yang perlu diwaspadai
          - Confidence score beserta alasannya
        """
        if not context.args:
            await update.message.reply_text(
                "❌ Harap sertakan kode saham.\nContoh: <code>/info BBCA</code>",
                parse_mode=ParseMode.HTML
            )
            return

        ticker_raw = context.args[0].upper().strip().replace(".JK", "")

        await update.message.reply_text(
            f"🔍 Menganalisis <b>{ticker_raw}</b>...\n"
            f"⏳ Memuat data historis + hitung indikator...",
            parse_mode=ParseMode.HTML
        )

        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(
                None,
                lambda: self.scanner.analyze_stock_info(ticker_raw)
            )
            msg = self.formatter.format_info(info)
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

        except Exception as e:
            logger.error(f"cmd_info error ({ticker_raw}): {e}", exc_info=True)
            await update.message.reply_text(
                f"❌ Error saat analisis <b>{ticker_raw}</b>: {str(e)[:200]}",
                parse_mode=ParseMode.HTML
            )

    async def cmd_buy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tampilkan sinyal BUY saja (dari memory atau cache disk hari ini)."""
        buy_signals = self.scanner._get_results_with_cache(signal_type="BUY")

        if not buy_signals:
            await update.message.reply_text(
                "ℹ️ Tidak ada sinyal BUY hari ini.\n"
                "Gunakan /scan untuk memperbarui atau tunggu scan otomatis.",
                parse_mode=ParseMode.HTML
            )
            return

        scan_time = self.scanner.last_scan_time
        time_str = ""
        if scan_time:
            try:
                import pytz
                from datetime import datetime as _dt
                wib = pytz.timezone("Asia/Jakarta")
                ts = _dt.fromisoformat(scan_time).astimezone(wib)
                time_str = f"\n⏰ <i>Data scan: {ts.strftime('%H:%M WIB')}</i>"
            except Exception:
                pass

        msg = f"🟢 <b>SINYAL BUY HARI INI ({len(buy_signals)} saham):</b>{time_str}\n\n"
        for s in buy_signals[:10]:  # max 10 sinyal BUY
            def fmt(p): return f"Rp {int(p):,}".replace(",", ".")
            strength_icon = "💪" if s.strength == "STRONG" else "👍" if s.strength == "MODERATE" else "⚠️"
            msg += (
                f"{strength_icon} <b>{s.ticker_clean}</b> ({s.company_name[:20]}) | Skor: {s.signal_score}/100\n"
                f"   Entry: {fmt(s.entry_price)} | TP2: {fmt(s.tp2)} | SL: {fmt(s.sl)}\n\n"
            )

        msg += "💡 Gunakan /signal [KODE] untuk detail lengkap\n"
        msg += "🔍 Gunakan /info [KODE] untuk analisis mendalam"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    async def cmd_waspada(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tampilkan sinyal WASPADA (kondisi bearish, dari memory atau cache disk)."""
        warn_signals = self.scanner._get_results_with_cache(signal_type="WASPADA")

        if not warn_signals:
            await update.message.reply_text(
                "ℹ️ Tidak ada sinyal WASPADA hari ini.\n"
                "Gunakan /scan untuk memperbarui atau tunggu scan otomatis.",
                parse_mode=ParseMode.HTML
            )
            return

        scan_time = self.scanner.last_scan_time
        time_str = ""
        if scan_time:
            try:
                import pytz
                from datetime import datetime as _dt
                wib = pytz.timezone("Asia/Jakarta")
                ts = _dt.fromisoformat(scan_time).astimezone(wib)
                time_str = f" (scan {ts.strftime('%H:%M WIB')})"
            except Exception:
                pass

        msg = f"🔴 <b>SAHAM WASPADA ({len(warn_signals)} saham){time_str}:</b>\n"
        msg += "⚠️ <i>Di BEI tidak ada short-selling. Hindari posisi baru pada saham berikut:</i>\n\n"
        for s in warn_signals[:10]:  # max 10 sinyal WASPADA
            # reasons[1] adalah alasan pertama setelah pesan peringatan header
            alasan_idx = 1 if len(s.reasons) > 1 else 0
            alasan = s.reasons[alasan_idx][:70] if s.reasons else "kondisi teknikal memburuk"
            change_icon = "🔻" if s.change_pct < 0 else "🔺"
            msg += (
                f"• <b>{s.ticker_clean}</b> ({s.company_name[:18]}) "
                f"{change_icon} {s.change_pct:+.1f}% | RSI {s.rsi:.0f} | Skor {s.signal_score}\n"
                f"  ↳ {alasan}\n"
            )

        msg += "\n💡 Gunakan /signal [KODE] untuk analisis lengkap"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    # ── ADMIN COMMANDS ────────────────────────────────────────────────────────

    async def cmd_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Perintah admin pribadi.

        Penggunaan (chat pribadi dengan bot):
            /admin              → tampilkan menu admin
            /admin status       → status server + store stats + pasar
            /admin scan         → paksa scan + kirim hasil ke sini
            /admin store        → statistik data store
            /admin logs [N]     → N baris terakhir log (default 30)
            /admin prescreen    → jalankan pre-screener dan tampilkan info

        Hanya user yang ID-nya ada di ADMIN_CHAT_IDS (.env) yang bisa menggunakan.
        """
        if not await _require_admin(update):
            return

        subcmd = (context.args[0].lower() if context.args else "menu")

        # ── /admin (menu) ────────────────────────────────────────────────────
        if subcmd == "menu" or subcmd == "help":
            await update.message.reply_text(
                "🔧 <b>ADMIN MENU</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "/admin status       — Status server & store\n"
                "/admin scan         — Paksa scan sekarang\n"
                "/admin store        — Statistik data store\n"
                "/admin logs [N]     — Log terakhir (def 30 baris)\n"
                "/admin prescreen    — Jalankan pre-screener\n",
                parse_mode=ParseMode.HTML,
            )
            return

        # ── /admin status ────────────────────────────────────────────────────
        if subcmd == "status":
            market = self.fetcher.get_market_status()
            summary = self.scanner.get_market_summary()

            # Store stats
            try:
                from data.store import get_store
                st = get_store().stats()
                store_txt = (
                    f"📦 <b>Data Store</b>\n"
                    f"  Tickers : {st['total_tickers']}\n"
                    f"  Baris   : {st['total_rows']:,}\n"
                    f"  Disk    : {st['disk_mb']:.1f} MB\n"
                    f"  Terbaru : {st.get('newest','N/A')}\n"
                )
            except Exception as e:
                store_txt = f"📦 Store: Error ({e})\n"

            # Scan summary
            scan_txt = (
                f"📊 <b>Scan Terakhir</b>\n"
                f"  Total  : {summary.get('total_signals', 0)}\n"
                f"  BUY    : {summary.get('buy_signals', 0)}\n"
                f"  WASPADA: {summary.get('sell_signals', 0)}\n"
                f"  Waktu  : {summary.get('scan_time', 'N/A')}\n"
            )

            market_emoji = "🟢" if market.get("is_open") else "🔴"
            market_txt = (
                f"{market_emoji} <b>Pasar</b>: {market.get('status')}\n"
                f"  Waktu  : {market.get('time_wib','N/A')} WIB\n"
            )

            await update.message.reply_text(
                "🔧 <b>ADMIN STATUS</b>\n━━━━━━━━━━━━━━━━━\n"
                + market_txt + "\n"
                + scan_txt + "\n"
                + store_txt,
                parse_mode=ParseMode.HTML,
            )
            return

        # ── /admin scan ──────────────────────────────────────────────────────
        if subcmd == "scan":
            await update.message.reply_text(
                "⏳ <b>Memulai scan paksa...</b>", parse_mode=ParseMode.HTML
            )
            try:
                signals = await self.scanner.scan_all_async(min_score=50)
                market = self.fetcher.get_market_status()
                if not signals:
                    await update.message.reply_text(
                        "ℹ️ Tidak ada sinyal saat ini.", parse_mode=ParseMode.HTML
                    )
                    return
                summary_text = self.formatter.format_summary(signals, market)
                await update.message.reply_text(summary_text, parse_mode=ParseMode.HTML)
                for signal in signals[:3]:
                    await asyncio.sleep(0.5)
                    await update.message.reply_text(
                        self.formatter.format_signal(signal),
                        parse_mode=ParseMode.HTML,
                    )
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Error scan: {str(e)[:300]}", parse_mode=ParseMode.HTML
                )
            return

        # ── /admin store ─────────────────────────────────────────────────────
        if subcmd == "store":
            try:
                from data.store import get_store
                st = get_store().stats()
                lines = ["📦 <b>DATA STORE</b>\n━━━━━━━━━━━━━━━"]
                lines.append(f"Path    : <code>{st['store_path']}</code>")
                lines.append(f"Tickers : {st['total_tickers']}")
                lines.append(f"Baris   : {st['total_rows']:,}")
                lines.append(f"Disk    : {st['disk_mb']:.1f} MB")
                lines.append(f"Oldest  : {st.get('oldest','N/A')}")
                lines.append(f"Newest  : {st.get('newest','N/A')}")
                if st.get("intervals"):
                    lines.append("\n<b>Per Interval:</b>")
                    for iv, info in st["intervals"].items():
                        lines.append(
                            f"  [{iv}]  {info['tickers']} tickers  "
                            f"{info['rows']:,} rows  {info['mb']:.1f} MB"
                        )
                await update.message.reply_text(
                    "\n".join(lines), parse_mode=ParseMode.HTML
                )
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Error baca store: {e}", parse_mode=ParseMode.HTML
                )
            return

        # ── /admin logs [N] ──────────────────────────────────────────────────
        if subcmd == "logs":
            n = 30
            if len(context.args) >= 2:
                try:
                    n = int(context.args[1])
                except ValueError:
                    pass
            log_path = Path("logs/app.log")
            if not log_path.exists():
                await update.message.reply_text(
                    "❌ File log tidak ditemukan.", parse_mode=ParseMode.HTML
                )
                return
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                tail = "".join(lines[-n:])
                if len(tail) > 3800:
                    tail = "...\n" + tail[-3800:]
                await update.message.reply_text(
                    f"📋 <b>Log terakhir ({n} baris):</b>\n<pre>{tail}</pre>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Error baca log: {e}", parse_mode=ParseMode.HTML
                )
            return

        # ── /admin prescreen ─────────────────────────────────────────────────
        if subcmd == "prescreen":
            await update.message.reply_text(
                "⏳ Menjalankan pre-screener...", parse_mode=ParseMode.HTML
            )
            try:
                from data.dynamic_screener import DynamicPreScreener
                screener = DynamicPreScreener()
                candidates = await asyncio.get_event_loop().run_in_executor(
                    None, screener.run
                )
                total = len(candidates) if candidates else 0
                msg = (
                    f"✅ <b>Pre-screener selesai</b>\n"
                    f"Kandidat ditemukan: <b>{total}</b> saham\n"
                )
                if candidates:
                    preview = ", ".join(
                        c.replace(".JK", "") for c in (candidates[:15] if isinstance(candidates[0], str) else [c.get("ticker","") for c in candidates[:15]])
                    )
                    msg += f"Contoh: {preview}{'...' if total > 15 else ''}"
                await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Error prescreen: {str(e)[:300]}", parse_mode=ParseMode.HTML
                )
            return

        # ── Unknown subcmd ───────────────────────────────────────────────────
        await update.message.reply_text(
            f"❓ Sub-perintah tidak dikenal: <code>{subcmd}</code>\n"
            "Ketik /admin untuk daftar perintah.",
            parse_mode=ParseMode.HTML,
        )

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

    async def start_async(self):
        """
        Jalankan bot polling di atas event loop yang sudah berjalan.
        Cocok dipakai bersama FastAPI/uvicorn.
        """
        app = self.build_app()
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot polling dimulai (async mode).")

    async def stop_async(self):
        """Hentikan bot polling dengan bersih."""
        if self.app is None:
            return
        try:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            logger.info("Bot polling dihentikan.")
        except Exception as e:
            logger.warning(f"Error saat stop bot: {e}")

    def run_polling(self):
        """Jalankan bot dalam mode standalone polling (tanpa API server)."""
        app = self.build_app()
        logger.info("Bot berjalan dalam mode polling...")
        app.run_polling(drop_pending_updates=True)
