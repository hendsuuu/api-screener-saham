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
        Format sinyal: BUY tampilkan Entry/TP/SL lengkap,
        WASPADA tampilkan peringatan + alasan saja (tanpa TP/SL).
        """
        if signal.signal_type == "WASPADA":
            return TelegramFormatter._format_warning(signal)
        return TelegramFormatter._format_buy(signal)

    @staticmethod
    def _format_warning(signal: ScalpSignal) -> str:
        """Format pesan WASPADA — kondisi bearish, tanpa entry/TP/SL."""
        strength_emoji = {
            "STRONG": "💪 KUAT",
            "MODERATE": "👍 SEDANG",
            "WEAK": "⚠️ LEMAH"
        }.get(signal.strength, "❓")

        score_bar = "█" * (signal.signal_score // 10) + \
            "░" * (10 - signal.signal_score // 10)

        def fmt_price(p: float) -> str:
            return f"Rp {int(p):,}".replace(",", ".")

        change_sign = "+" if signal.change_pct >= 0 else ""
        change_emoji = "📈" if signal.change_pct >= 0 else "📉"

        trend_map = {
            "UPTREND": "⬆️ Uptrend",
            "UPTREND_WEAK": "↗️ Uptrend Lemah",
            "DOWNTREND": "⬇️ Downtrend Kuat",
            "DOWNTREND_WEAK": "↘️ Downtrend Lemah",
            "SIDEWAYS": "↔️ Sideways",
        }
        trend_display = trend_map.get(signal.trend, signal.trend)
        macd_emoji = "🟢" if signal.macd_signal == "BULLISH" else (
            "🔴" if signal.macd_signal == "BEARISH" else "🟡")
        rsi_emoji = "🟢" if 30 < signal.rsi < 70 else "🔴"
        now = datetime.now().strftime("%d/%m/%Y %H:%M WIB")

        msg = f"""
🔴 <b>SINYAL WASPADA</b> 🔴
━━━━━━━━━━━━━━━━━━━━
🏷 <b>{signal.ticker_clean}</b> | {signal.company_name}
⏰ {now}

⚠️ <b>KONDISI TEKNIKAL MEMBURUK</b>
📊 Skor Teknikal   : <b>{signal.signal_score}/100</b>
<code>[{score_bar}]</code>
🏋️ Skala Peringatan: {strength_emoji}

━━━━━━━━━━━━━━━━━━━━
💰 <b>DATA HARGA HARI INI</b>
💲 Harga Saat Ini : {fmt_price(signal.current_price)}
📂 Open     : {fmt_price(signal.open_price)}
⬆️ High     : {fmt_price(signal.high_day)}
⬇️ Low      : {fmt_price(signal.low_day)}
{change_emoji} Change   : {change_sign}{signal.change_pct:.2f}%
📊 Volume   : {signal.volume:,} lot

━━━━━━━━━━━━━━━━━━━━
🔬 <b>INDIKATOR TEKNIKAL</b>
📊 Trend    : {trend_display}
{rsi_emoji} RSI(9)   : {signal.rsi:.1f}
{macd_emoji} MACD     : {signal.macd_signal}
📈 Volume   : {signal.volume_ratio:.1f}x avg
📉 Bollinger: {signal.bb_position} Band
📉 VWAP     : {fmt_price(signal.vwap)} ({signal.price_vs_vwap})
↔️ ATR      : {fmt_price(signal.atr)} ({signal.atr_pct:.2f}%)

━━━━━━━━━━━━━━━━━━━━
🗺 <b>SUPPORT & RESISTANCE</b>
🔴 Resistance: {fmt_price(signal.resistance)}
🟢 Support   : {fmt_price(signal.support)}

━━━━━━━━━━━━━━━━━━━━
📝 <b>ALASAN PERINGATAN</b>
""".strip()

        for reason in signal.reasons[:7]:
            msg += f"\n{reason}"

        msg += f"""

━━━━━━━━━━━━━━━━━━━━
🚧 <b>APA YANG HARUS DILAKUKAN?</b>
• Jangan membuka posisi BUY baru pada saham ini
• Jika sudah pegang: pertimbangkan cut-loss atau protect profit
• Tunggu konfirmasi reversal sebelum re-entry

⚠️ <i>Di BEI tidak ada short-selling. Sinyal ini murni PERINGATAN,
bukan rekomendasi transaksi. Selalu gunakan manajemen risiko!</i>
#IDXSaham #{signal.ticker_clean} #Waspada #BEI"""

        return msg

    @staticmethod
    def _format_buy(signal: ScalpSignal) -> str:
        """Format pesan BUY lengkap dengan Entry, TP, SL."""
        strength_emoji = {
            "STRONG": "💪 STRONG",
            "MODERATE": "👍 MODERATE",
            "WEAK": "⚠️ WEAK"
        }.get(signal.strength, "❓")

        score_bar = "█" * (signal.signal_score // 10) + \
            "░" * (10 - signal.signal_score // 10)

        def fmt_price(p: float) -> str:
            return f"Rp {int(p):,}".replace(",", ".")

        change_sign = "+" if signal.change_pct >= 0 else ""
        change_emoji = "📈" if signal.change_pct >= 0 else "📉"

        lot_multiplier = 100
        entry_rupiah_lot = signal.entry_price * lot_multiplier
        tp2_profit_lot = (signal.tp2 - signal.entry_price) * lot_multiplier
        sl_loss_lot = abs(signal.sl - signal.entry_price) * lot_multiplier

        trend_map = {
            "UPTREND": "⬆️ Uptrend Kuat",
            "UPTREND_WEAK": "↗️ Uptrend Lemah",
            "DOWNTREND": "⬇️ Downtrend Kuat",
            "DOWNTREND_WEAK": "↘️ Downtrend Lemah",
            "SIDEWAYS": "↔️ Sideways",
        }
        trend_display = trend_map.get(signal.trend, signal.trend)

        vwap_emoji = "✅" if signal.price_vs_vwap == "ABOVE" else "⚠️"
        rsi_emoji = "🟢" if 30 < signal.rsi < 70 else (
            "🔴" if signal.rsi > 70 or signal.rsi < 30 else "🟡")
        macd_emoji = "🟢" if signal.macd_signal == "BULLISH" else (
            "🔴" if signal.macd_signal == "BEARISH" else "🟡")
        now = datetime.now().strftime("%d/%m/%Y %H:%M WIB")

        msg = f"""
🟢 <b>SINYAL BUY</b> 🟢
━━━━━━━━━━━━━━━━━━━━
🏷 <b>{signal.ticker_clean}</b> | {signal.company_name}
⏰ {now}

📊 <b>SKOR SINYAL: {signal.signal_score}/100</b>
<code>[{score_bar}]</code>
🏋️ Kekuatan: {strength_emoji}

━━━━━━━━━━━━━━━━━━━━
💰 <b>HARGA ENTRY</b>
🎯 Entry Point    : <b>{fmt_price(signal.entry_price)}</b>
📍 Zone Entry     : {fmt_price(signal.entry_zone_low)} – {fmt_price(signal.entry_zone_high)}

▲ <b>TAKE PROFIT</b>
✅ TP1 (+1.5%)   : <b>{fmt_price(signal.tp1)}</b>
✅ TP2 (+{signal.target_pct:.1f}%)  : <b>{fmt_price(signal.tp2)}</b>  ⭐ Target Utama
✅ TP3 (+3.5%)   : <b>{fmt_price(signal.tp3)}</b>  🚀 Target Maksimal

🛑 <b>STOP LOSS</b>
❌ SL (-{signal.sl_pct:.1f}%)     : <b>{fmt_price(signal.sl)}</b>

⚖️ <b>RISK : REWARD</b>
📐 R:R Ratio      : <b>1 : {signal.rr_ratio:.1f}</b>
📈 Target Profit  : <b>+{signal.target_pct:.1f}%</b>
🛡️ Maks Risiko    : <b>-{signal.sl_pct:.1f}%</b>

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
{change_emoji} Change  : {change_sign}{signal.change_pct:.2f}%
📊 Volume  : {signal.volume:,} lot

━━━━━━━━━━━━━━━━━━━━
🔬 <b>ANALISIS TEKNIKAL</b>
📊 Trend    : {trend_display}
{rsi_emoji} RSI(9)   : {signal.rsi:.1f}
{macd_emoji} MACD     : {signal.macd_signal}
📈 Volume   : {signal.volume_ratio:.1f}x avg
{vwap_emoji} VWAP     : {fmt_price(signal.vwap)} ({signal.price_vs_vwap})
📉 Bollinger: {signal.bb_position} Band
🖕 Candle   : {signal.candle_pattern}
📐 ATR      : {fmt_price(signal.atr)} ({signal.atr_pct:.2f}%)

━━━━━━━━━━━━━━━━━━━━
🗺 <b>SUPPORT & RESISTANCE</b>
🔴 Resistance: {fmt_price(signal.resistance)}
🟢 Support   : {fmt_price(signal.support)}

━━━━━━━━━━━━━━━━━━━━
📝 <b>ALASAN SINYAL</b>
""".strip()

        for reason in signal.reasons[:6]:
            msg += f"\n{reason}"

        msg += f"""

━━━━━━━━━━━━━━━━━━━━
⚠️ <i>Disclaimer: Sinyal ini hanya referensi analisis teknikal.
Selalu lakukan riset sendiri. Manajemen risiko adalah kunci!</i>
#IDXSaham #{signal.ticker_clean} #BUY #Scalping"""

        return msg

    @staticmethod
    def format_summary(signals: List[ScalpSignal], market_status: Dict) -> str:
        """
        Format ringkasan hasil scan ke pesan Telegram.
        """
        now = datetime.now().strftime("%d/%m/%Y %H:%M WIB")

        buy_signals = [s for s in signals if s.signal_type == "BUY"]
        warn_signals = [s for s in signals if s.signal_type == "WASPADA"]
        strong_signals = [s for s in signals if s.strength == "STRONG"]

        status_emoji = "🟢" if market_status.get("is_open") else "🔴"

        msg = f"""
🔍 <b>LAPORAN SCREENER SAHAM IDX</b>
━━━━━━━━━━━━━━━━━━━━
⏰ {now}
{status_emoji} Status Pasar: {market_status.get('status', 'N/A')}

📊 <b>RINGKASAN SCAN</b>
🟢 Sinyal BUY     : {len(buy_signals)} saham
🔴 Sinyal WASPADA : {len(warn_signals)} saham
💪 Sinyal KUAT    : {len(strong_signals)} saham
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

        if warn_signals:
            msg += "\n\n🔴 <b>SAHAM WASPADA:</b>"
            for i, s in enumerate(warn_signals[:5], 1):
                msg += (
                    f"\n{i}. ⚠️ <b>{s.ticker_clean}</b> | "
                    f"Harga: Rp {int(s.current_price):,} | "
                    f"Skor Teknikal: {s.signal_score}/100 | "
                    + (s.reasons[1][:50] if len(s.reasons)
                       > 1 else "kondisi memburuk")
                )

        msg += """

━━━━━━━━━━━━━━━━━━━━
💡 <i>Ketik /signal [KODE] untuk detail sinyal BUY
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
🤖 <b>IDX SCALPER BOT — PANDUAN PENGGUNAAN</b>
━━━━━━━━━━━━━━━━━━━━

<b>📋 PERINTAH TERSEDIA:</b>

/start        — Pesan selamat datang
/scan         — Scan saham IDX sekarang (~2-3 menit)
/top          — 5 sinyal BUY terbaik dari scan terakhir
/signal [KD]  — Analisis detail satu saham
               Contoh: <code>/signal BBCA</code>
/buy          — Daftar sinyal BUY yang aktif
/waspada      — Daftar saham kondisi WASPADA
/market       — Status pasar BEI & ringkasan scan
/help         — Tampilkan bantuan ini

━━━━━━━━━━━━━━━━━━━━
<b>🟢 SINYAL BUY — Lengkap dengan:</b>
• Entry Zone  : Range harga optimal masuk
• TP1 (+1.5%) : Take Profit konservatif
• TP2 (+2.5%) : Target utama ⭐
• TP3 (+3.5%) : Target maksimal
• Stop Loss   : Batas rugi otomatis (ATR-based)
• R:R Ratio   : Minimum 1:2

<b>🔴 SINYAL WASPADA — Peringatan bearish:</b>
• Kondisi teknikal memburuk
• Hindari beli atau pertimbangkan kurangi posisi
• <b>Di BEI tidak ada short-selling</b>, tidak ada TP/SL

━━━━━━━━━━━━━━━━━━━━
<b>⚙️ STRATEGI SCALPING:</b>
• Timeframe utama    : 5 menit
• Target profit      : 2-3% per trade
• Gunakan TP parsial : jual sebagian di TP1, sisanya di TP2
• Geser SL ke BEP   : setelah harga capai TP1
• Volume tinggi      : konfirmasi sinyal lebih kuat
• Scan otomatis      : setiap 15 menit saat bursa buka

<b>📊 INDIKATOR YANG DIGUNAKAN:</b>
RSI(9) • MACD(12/26/9) • Bollinger Bands • VWAP
ADX • EMA 9/20/50 • ATR • Stochastic • SuperTrend

━━━━━━━━━━━━━━━━━━━━
⚠️ <i>Bot ini murni alat bantu analisis teknikal.
Keputusan trading tetap sepenuhnya di tangan Anda!</i>
""".strip()
