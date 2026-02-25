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
    def format_info(info: dict) -> str:
        """
        Format hasil analyze_stock_info() menjadi pesan Telegram HTML.
        Menampilkan: trend, EMA, S/R, potensi, risiko, confidence, dan alasan.
        """
        def fmt(p: float) -> str:
            return f"Rp {int(p):,}".replace(",", ".")

        ticker = info.get("ticker", "?")
        company = info.get("company_name", ticker)[:25]
        price = info.get("last_price", 0.0)
        chg = info.get("change_pct", 0.0)
        trend = info.get("trend", "UNKNOWN")
        td = info.get("trend_detail", "-")
        e9 = info.get("ema9", 0.0)
        e20 = info.get("ema20", 0.0)
        e50 = info.get("ema50", 0.0)
        sup = info.get("support", 0.0)
        res = info.get("resistance", 0.0)
        sup2 = info.get("support2", 0.0)
        res2 = info.get("resistance2", 0.0)
        rsi = info.get("rsi", 50.0)
        rsi_z = info.get("rsi_zone", "-")
        macd_s = info.get("macd_signal", "-")
        bb_p = info.get("bb_position", "-")
        vol_r = info.get("volume_ratio", 1.0)
        adx = info.get("adx", 0.0)
        atr_pct = info.get("atr_pct", 0.0)
        potential = info.get("potential", "NETRAL")
        pot_detail = info.get("potential_detail", [])
        risk = info.get("risk", "SEDANG")
        risk_detail = info.get("risk_detail", [])
        conf = info.get("confidence", 0)
        conf_r = info.get("confidence_reasons", [])
        cross_up = info.get("ema_cross_up", False)
        cross_dn = info.get("ema_cross_down", False)
        mcross_up = info.get("macd_cross_up", False)
        mcross_dn = info.get("macd_cross_down", False)
        source = info.get("data_source", "")

        from datetime import datetime
        now = datetime.now().strftime("%d/%m/%Y %H:%M")

        # Trend icon
        trend_icon = {
            "BULLISH":       "📈 BULLISH",
            "UPTREND_WEAK":  "↗️ UPTREND LEMAH",
            "BEARISH":       "📉 BEARISH",
            "DOWNTREND_WEAK": "↘️ DOWNTREND LEMAH",
            "SIDEWAYS":      "↔️ SIDEWAYS",
        }.get(trend, f"❓ {trend}")

        chg_icon = "🔺" if chg >= 0 else "🔻"
        macd_icon = "🟢" if macd_s == "BULLISH" else "🔴"
        rsi_icon = "🔴" if rsi > 70 else ("🟢" if rsi < 35 else "🟡")
        vol_icon = "🔥" if vol_r >= 1.5 else ("✅" if vol_r >= 1.0 else "⚠️")
        adx_icon = "✅" if adx >= 25 else ("⚠️" if adx < 18 else "🟡")

        conf_bar = "█" * (conf // 10) + "░" * (10 - conf // 10)

        # Potential & risk colors
        pot_icon = {
            "BULLISH":              "🟢",
            "POTENSI REVERSAL NAIK": "⚡",
            "BEARISH":              "🔴",
            "SIDEWAYS / WAIT":      "↔️",
        }.get(potential, "❓")

        risk_icon = {"RENDAH-SEDANG": "🟢",
                     "SEDANG": "🟡", "TINGGI": "🔴"}.get(risk, "🟡")

        msg = (
            f"🔍 <b>INFO SAHAM: {ticker}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷 <b>{ticker}</b> | {company}\n"
            f"⏰ {now} WIB\n\n"

            f"💰 <b>HARGA</b>\n"
            f"💲 Terakhir : {fmt(price)}\n"
            f"{chg_icon} Perubahan : {chg:+.2f}%\n\n"

            f"📊 <b>TREND & EMA</b>\n"
            f"🎯 Trend : <b>{trend_icon}</b>\n"
            f"ℹ️ Detail : {td}\n"
            f"📐 EMA9  : {fmt(e9)}\n"
            f"📐 EMA20 : {fmt(e20)}\n"
            f"📐 EMA50 : {fmt(e50)}\n"
        )

        if cross_up:
            msg += "⚡ <b>EMA9 baru cross UP EMA20!</b> (sinyal bullish)\n"
        if cross_dn:
            msg += "⚠️ <b>EMA9 baru cross DOWN EMA20!</b> (sinyal bearish)\n"

        msg += (
            f"\n🗺 <b>SUPPORT & RESISTANCE</b>\n"
            f"🔴 Resistance 1: {fmt(res)} (+{(res-price)/price*100:.1f}%)\n"
            f"🔴 Resistance 2: {fmt(res2)} (+{(res2-price)/price*100:.1f}%)\n"
            f"🟢 Support 1   : {fmt(sup)} (-{(price-sup)/price*100:.1f}%)\n"
            f"🟢 Support 2   : {fmt(sup2)} (-{(price-sup2)/price*100:.1f}%)\n\n"

            f"🔬 <b>INDIKATOR</b>\n"
            f"{rsi_icon} RSI(9)   : {rsi:.1f} — {rsi_z}\n"
            f"{macd_icon} MACD     : {macd_s}"
        )

        if mcross_up:
            msg += " ⚡ fresh bullish cross"
        if mcross_dn:
            msg += " ⚠️ fresh bearish cross"
        msg += f"\n"

        msg += (
            f"📈 Bollinger : {bb_p}\n"
            f"{vol_icon} Volume   : {vol_r:.1f}x rata-rata\n"
            f"{adx_icon} ADX      : {adx:.0f} ({'Tren Kuat' if adx >= 25 else 'Sideways' if adx < 18 else 'Moderat'})\n"
            f"〰️ ATR/Hrg  : {atr_pct:.1f}% (fluktuasi wajar per candle)\n\n"

            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{pot_icon} <b>POTENSI KE DEPAN: {potential}</b>\n"
        )
        for pd_line in pot_detail:
            msg += f"  {pd_line}\n"

        msg += (
            f"\n{risk_icon} <b>RISIKO: {risk}</b>\n"
        )
        for rd_line in risk_detail[:4]:
            msg += f"  {rd_line}\n"

        msg += (
            f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>CONFIDENCE: {conf}/100</b>\n"
            f"<code>[{conf_bar}]</code>\n"
        )

        if conf < 50:
            msg += "⚠️ <i>Confidence rendah — kenapa?</i>\n"
        for reason in conf_r[:6]:
            msg += f"  {reason}\n"

        # Lampirkan ScalpSignal jika ada
        sig = info.get("signal_obj")
        if sig:
            sig_icon = "🟢 BUY" if sig.signal_type == "BUY" else "🔴 WASPADA"
            msg += (
                f"\n━━━━━━━━━━━━━━━━━━━━\n"
                f"⚡ <b>SINYAL AKTIF: {sig_icon}</b> (Skor {sig.signal_score}/100)\n"
                f"Gunakan /signal {ticker} untuk detail entry/TP/SL lengkap\n"
            )
        else:
            msg += (
                f"\nℹ️ Tidak ada sinyal aktif saat ini (confidence < threshold)\n"
            )

        msg += (
            f"\n⚠️ <i>Analisis ini bukan rekomendasi investasi.\n"
            f"Selalu gunakan manajemen risiko!</i>\n"
            f"#IDXSaham #{ticker}"
        )

        return msg.strip()

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
/info [KD]    — Ringkasan mendalam: trend, S/R, potensi, risiko
               Contoh: <code>/info BBCA</code>
/buy          — Daftar sinyal BUY hari ini (max 10)
/waspada      — Daftar saham kondisi WASPADA hari ini (max 10)
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
<b>⚙️ JADWAL PENGIRIMAN SINYAL:</b>
• 04:00 WIB — Update data candle terbaru (otomatis)
• 06:00 WIB — Kirim max 10 BUY + 10 WASPADA (otomatis)
• 09:00 WIB — Notif pasar buka
• 14:45 WIB — Reminder pre-close
• 15:05 WIB — Notif pasar tutup

<b>📊 INDIKATOR YANG DIGUNAKAN:</b>
RSI(9) • MACD(12/26/9) • Bollinger Bands • VWAP
ADX • EMA 9/20/50 • ATR • Stochastic • SuperTrend

━━━━━━━━━━━━━━━━━━━━
⚠️ <i>Bot ini murni alat bantu analisis teknikal.
Keputusan trading tetap sepenuhnya di tangan Anda!</i>
""".strip()
