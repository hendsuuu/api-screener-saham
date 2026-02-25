"""
Telegram Message Formatter - Format notifikasi sinyal scalping
Menggunakan HTML formatting untuk Telegram
"""

from screener.signal_generator import ScalpSignal
from datetime import datetime
from typing import List, Dict


class TelegramFormatter:
    """Format pesan sinyal scalping untuk Telegram."""

    @staticmethod
    def format_signal(signal: ScalpSignal) -> str:
        """
        Format sinyal scalping lengkap dengan Entry/TP/SL.
        Menggunakan HTML mode Telegram.
        """
        # Emoji berdasarkan jenis sinyal
        if signal.signal_type == "BUY":
            signal_emoji = "🟢"
            signal_text = "BUY / LONG"
            action_text = "BELI"
            tp_direction = "▲"
        else:
            signal_emoji = "🔴"
            signal_text = "SELL / SHORT"
            action_text = "JUAL"
            tp_direction = "▼"

        # Emoji kekuatan sinyal
        strength_emoji = {
            "STRONG": "💪 STRONG",
            "MODERATE": "👍 MODERATE",
            "WEAK": "⚠️ WEAK"
        }.get(signal.strength, "❓")

        # Bar indikator skor (visual)
        score_bar = "█" * (signal.signal_score // 10) + \
            "░" * (10 - signal.signal_score // 10)

        # Format harga Indonesia (tambah titik ribuan)
        def fmt_price(p: float) -> str:
            return f"Rp {int(p):,}".replace(",", ".")

        # Format perubahan harga
        change_sign = "+" if signal.change_pct >= 0 else ""
        change_emoji = "📈" if signal.change_pct >= 0 else "📉"

        # Hitung nilai rupiah TP/SL per lot (1 lot = 100 lembar)
        lot_multiplier = 100
        entry_rupiah_lot = signal.entry_price * lot_multiplier
        tp2_profit_lot = (signal.tp2 - signal.entry_price) * lot_multiplier
        sl_loss_lot = abs(signal.sl - signal.entry_price) * lot_multiplier

        # Trend emoji
        trend_map = {
            "UPTREND": "⬆️ Uptrend Kuat",
            "UPTREND_WEAK": "↗️ Uptrend Lemah",
            "DOWNTREND": "⬇️ Downtrend Kuat",
            "DOWNTREND_WEAK": "↘️ Downtrend Lemah",
            "SIDEWAYS": "↔️ Sideways",
        }
        trend_display = trend_map.get(signal.trend, signal.trend)

        # VWAP
        vwap_emoji = "✅" if (
            (signal.signal_type == "BUY" and signal.price_vs_vwap == "ABOVE") or
            (signal.signal_type == "SELL" and signal.price_vs_vwap == "BELOW")
        ) else "⚠️"

        # RSI display
        rsi_emoji = "🟢" if 30 < signal.rsi < 70 else (
            "🔴" if signal.rsi > 70 or signal.rsi < 30 else "🟡")

        # MACD
        macd_emoji = "🟢" if signal.macd_signal == "BULLISH" else (
            "🔴" if signal.macd_signal == "BEARISH" else "🟡")

        # Build pesan
        now = datetime.now().strftime("%d/%m/%Y %H:%M WIB")

        msg = f"""
{signal_emoji} <b>SINYAL SCALP {signal_text}</b> {signal_emoji}
━━━━━━━━━━━━━━━━━━━━
🏷 <b>{signal.ticker_clean}</b> | {signal.company_name}
⏰ {now}

📊 <b>SKOR SINYAL: {signal.signal_score}/100</b>
<code>[{score_bar}]</code>
🏋️ Kekuatan: {strength_emoji}

━━━━━━━━━━━━━━━━━━━━
💰 <b>HARGA ENTRY</b>
🎯 Entry Point  : <b>{fmt_price(signal.entry_price)}</b>
📍 Zone Entry   : {fmt_price(signal.entry_zone_low)} - {fmt_price(signal.entry_zone_high)}

{tp_direction} <b>TAKE PROFIT</b>
✅ TP1 (+{1.5:.1f}%): <b>{fmt_price(signal.tp1)}</b>
✅ TP2 (+{signal.target_pct:.1f}%): <b>{fmt_price(signal.tp2)}</b>  ⭐ Target Utama
✅ TP3 (+{3.5:.1f}%): <b>{fmt_price(signal.tp3)}</b>  🚀 Target Maksimal

🛑 <b>STOP LOSS</b>
❌ SL (-{signal.sl_pct:.1f}%)  : <b>{fmt_price(signal.sl)}</b>

⚖️ <b>RISK : REWARD</b>
📐 R:R Ratio    : <b>1 : {signal.rr_ratio:.1f}</b>
📈 Target Profit: <b>+{signal.target_pct:.1f}%</b>
🛡️ Maks Risiko  : <b>-{signal.sl_pct:.1f}%</b>

━━━━━━━━━━━━━━━━━━━━
💵 <b>ESTIMASI PER LOT (100 lembar)</b>
Modal Entry     : Rp {int(entry_rupiah_lot):,}
Profit TP2      : +Rp {int(tp2_profit_lot):,}
Maks Loss SL    : -Rp {int(sl_loss_lot):,}

━━━━━━━━━━━━━━━━━━━━
📈 <b>DATA HARGA HARI INI</b>
💲 Harga Saat Ini: {fmt_price(signal.current_price)}
📂 Open    : {fmt_price(signal.open_price)}
⬆️ High    : {fmt_price(signal.high_day)}
⬇️ Low     : {fmt_price(signal.low_day)}
{change_emoji} Change : {change_sign}{signal.change_pct:.2f}%
📊 Volume  : {signal.volume:,} lot

━━━━━━━━━━━━━━━━━━━━
🔬 <b>ANALISIS TEKNIKAL</b>
📊 Trend    : {trend_display}
{rsi_emoji} RSI(9)  : {signal.rsi:.1f}
{macd_emoji} MACD    : {signal.macd_signal}
📈 Volume   : {signal.volume_ratio:.1f}x avg
{vwap_emoji} VWAP    : {fmt_price(signal.vwap)} ({signal.price_vs_vwap})
📉 Bollinger: {signal.bb_position} Band
🕯 Candle   : {signal.candle_pattern}
📐 ATR      : {fmt_price(signal.atr)} ({signal.atr_pct:.2f}%)

━━━━━━━━━━━━━━━━━━━━
🗺 <b>SUPPORT & RESISTANCE</b>
🔴 Resistance: {fmt_price(signal.resistance)}
🟢 Support   : {fmt_price(signal.support)}

━━━━━━━━━━━━━━━━━━━━
📝 <b>ALASAN SINYAL</b>
""".strip()

        for reason in signal.reasons[:6]:  # Max 6 alasan
            msg += f"\n{reason}"

        msg += f"""

━━━━━━━━━━━━━━━━━━━━
⚠️ <i>Disclaimer: Sinyal ini hanya untuk referensi edukasi. 
Selalu lakukan analisis sendiri sebelum trading.
Manajemen risiko adalah kunci utama!</i>
#IDXSaham #{signal.ticker_clean} #{signal.signal_type} #Scalping"""

        return msg

    @staticmethod
    def format_summary(signals: List[ScalpSignal], market_status: Dict) -> str:
        """
        Format ringkasan hasil scan ke pesan Telegram.
        """
        now = datetime.now().strftime("%d/%m/%Y %H:%M WIB")

        buy_signals = [s for s in signals if s.signal_type == "BUY"]
        sell_signals = [s for s in signals if s.signal_type == "SELL"]
        strong_signals = [s for s in signals if s.strength == "STRONG"]

        status_emoji = "🟢" if market_status.get("is_open") else "🔴"

        msg = f"""
🔍 <b>LAPORAN SCREENER SAHAM IDX</b>
━━━━━━━━━━━━━━━━━━━━
⏰ {now}
{status_emoji} Status Pasar: {market_status.get('status', 'N/A')}

📊 <b>RINGKASAN SCAN</b>
🟢 Sinyal BUY  : {len(buy_signals)} saham
🔴 Sinyal SELL : {len(sell_signals)} saham
💪 Sinyal KUAT : {len(strong_signals)} saham
""".strip()

        if buy_signals:
            msg += "\n\n🟢 <b>TOP BUY PICKS:</b>"
            for i, s in enumerate(buy_signals[:5], 1):
                def fmt_price(p):
                    return f"Rp {int(p):,}".replace(",", ".")
                strength_icon = "💪" if s.strength == "STRONG" else "👍"
                msg += (
                    f"\n{i}. {strength_icon} <b>{s.ticker_clean}</b> | "
                    f"Entry: {fmt_price(s.entry_price)} | "
                    f"TP2: {fmt_price(s.tp2)} (+{s.target_pct}%) | "
                    f"SL: {fmt_price(s.sl)} | "
                    f"Skor: {s.signal_score}/100"
                )

        if sell_signals:
            msg += "\n\n🔴 <b>TOP SELL PICKS:</b>"
            for i, s in enumerate(sell_signals[:5], 1):
                def fmt_price(p):
                    return f"Rp {int(p):,}".replace(",", ".")
                strength_icon = "💪" if s.strength == "STRONG" else "👍"
                msg += (
                    f"\n{i}. {strength_icon} <b>{s.ticker_clean}</b> | "
                    f"Entry: {fmt_price(s.entry_price)} | "
                    f"TP2: {fmt_price(s.tp2)} (-{s.target_pct}%) | "
                    f"SL: {fmt_price(s.sl)} | "
                    f"Skor: {s.signal_score}/100"
                )

        msg += """

━━━━━━━━━━━━━━━━━━━━
💡 <i>Ketik /signal [KODE] untuk detail lengkap
Contoh: /signal BBCA</i>
#IDXScreener #SahamIndonesia #Scalping"""

        return msg

    @staticmethod
    def format_market_closed() -> str:
        """Pesan ketika pasar sedang tutup."""
        return """
🔴 <b>PASAR BURSA SEDANG TUTUP</b>

📅 Jam Bursa BEI:
• Sesi 1 : 09:00 - 11:30 WIB
• Sesi 2 : 13:30 - 15:00 WIB
• Hari   : Senin - Jumat

⏳ Screener akan aktif otomatis saat pasar buka.

💡 <i>Gunakan waktu ini untuk analisis & persiapan watchlist!</i>
""".strip()

    @staticmethod
    def format_help() -> str:
        """Pesan bantuan command bot."""
        return """
🤖 <b>SAHAM SCALPER BOT - PANDUAN</b>
━━━━━━━━━━━━━━━━━━━━

<b>📋 PERINTAH TERSEDIA:</b>

/start       - Mulai bot
/scan        - Scan semua saham (butuh ~1 menit)
/top         - Tampilkan 5 sinyal terbaik
/signal [KD] - Detail sinyal saham tertentu
             Contoh: /signal BBCA
/buy         - Tampilkan sinyal BUY saja
/sell        - Tampilkan sinyal SELL saja
/market      - Status pasar & ringkasan
/help        - Tampilkan bantuan ini

━━━━━━━━━━━━━━━━━━━━
<b>📊 PENJELASAN SINYAL:</b>
• Entry Zone : Range harga optimal masuk
• TP1 (+1.5%): Take Profit konservatif
• TP2 (+2.5%): Target utama ⭐
• TP3 (+3.5%): Target maksimal
• SL         : Stop Loss (batas rugi)

<b>⚙️ STRATEGI:</b>
• Gunakan TP parsial untuk lock profit
• Geser SL ke breakeven setelah capai TP1
• Volume tinggi = konfirmasi sinyal lebih kuat

━━━━━━━━━━━━━━━━━━━━
⚠️ <i>Bot ini hanya alat bantu analisis.
Keputusan trading tetap di tangan Anda!</i>
""".strip()
