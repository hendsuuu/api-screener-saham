"""
Signal Generator - Kalkulasi Entry, Take Profit, Stop Loss
Strategi: Scalper Intraday target profit 2-3%
Risk:Reward rasio minimum 1:2
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from datetime import datetime
from screener.indicators import TechnicalIndicators


@dataclass
class ScalpSignal:
    """
    Hasil sinyal scalping dengan detail Entry/TP/SL.
    """
    ticker: str
    ticker_clean: str                   # tanpa .JK
    company_name: str
    signal_type: str                    # BUY / SELL
    strength: str                       # STRONG / MODERATE / WEAK

    # Harga-harga kunci
    entry_price: float
    entry_zone_low: float               # Range entry bawah
    entry_zone_high: float              # Range entry atas

    tp1: float                          # Take Profit 1 (+1.5%)
    tp2: float                          # Take Profit 2 (+2.5%)
    tp3: float                          # Take Profit 3 (+3.5%)
    sl: float                           # Stop Loss

    # Risk-Reward
    rr_ratio: float                     # Risk:Reward ratio
    target_pct: float                   # Target profit utama (%)
    sl_pct: float                       # Jarak stop loss (%)

    # Indikator pendukung
    rsi: float
    macd_signal: str                    # BULLISH / BEARISH / NEUTRAL
    volume_ratio: float                 # Volume vs rata-rata
    trend: str                          # UPTREND / DOWNTREND / SIDEWAYS
    bb_position: str                    # UPPER / MIDDLE / LOWER / SQUEEZE

    # ATR untuk volatility
    atr: float
    atr_pct: float                      # ATR sebagai % harga

    # Info harga saat ini
    current_price: float
    open_price: float
    high_day: float
    low_day: float
    change_pct: float
    volume: int

    # Konfirmasi candlestick
    candle_pattern: str

    # Vwap analysis
    vwap: float
    price_vs_vwap: str                  # ABOVE / BELOW

    # Skor sinyal 0-100
    signal_score: int

    # Alasan sinyal
    reasons: List[str] = field(default_factory=list)

    # Timestamp
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Support & Resistance
    support: float = 0.0
    resistance: float = 0.0


class SignalGenerator:
    """
    Generator sinyal scalping intraday berbasis multi-indikator.

    Strategi:
    - Time frame utama: 5 menit
    - Time frame konfirmasi: 15 menit
    - Target: 2-3% profit
    - SL: 1.0-1.5% (ATR-based)
    - Risk:Reward minimum 1:2
    """

    def __init__(self):
        self.ind = TechnicalIndicators()

        # Konfigurasi scalping
        self.config = {
            "tp1_pct": 1.5,     # TP1: +1.5%
            "tp2_pct": 2.5,     # TP2: +2.5%
            "tp3_pct": 3.5,     # TP3: +3.5%
            "sl_pct": 1.0,      # SL default: -1%
            "sl_atr_mult": 1.5,  # SL = 1.5x ATR (dinamis)
            "min_rr": 2.0,      # Minimum Risk:Reward 1:2
            "min_volume_ratio": 1.2,  # Minimal volume 1.2x rata-rata
            "rsi_oversold": 35,
            "rsi_overbought": 65,
        }

    def _calculate_support_resistance(
        self,
        df: pd.DataFrame,
        lookback: int = 20
    ) -> Tuple[float, float]:
        """Hitung level support dan resistance sederhana."""
        recent = df.tail(lookback)
        support = float(recent["Low"].min())
        resistance = float(recent["High"].max())
        return support, resistance

    def _get_trend(
        self,
        df: pd.DataFrame
    ) -> str:
        """Tentukan trend berdasarkan EMA 9/20/50."""
        close = df["Close"]
        ema9 = self.ind.ema(close, 9)
        ema20 = self.ind.ema(close, 20)
        ema50 = self.ind.ema(close, 50)

        curr_price = close.iloc[-1]
        e9 = ema9.iloc[-1]
        e20 = ema20.iloc[-1]
        e50 = ema50.iloc[-1]

        if e9 > e20 > e50 and curr_price > e9:
            return "UPTREND"
        elif e9 < e20 < e50 and curr_price < e9:
            return "DOWNTREND"
        elif abs(e9 - e20) / e20 < 0.005:
            return "SIDEWAYS"
        elif curr_price > e20:
            return "UPTREND_WEAK"
        else:
            return "DOWNTREND_WEAK"

    def _score_signal(
        self,
        rsi: float,
        macd_bull: bool,
        vol_ratio: float,
        trend: str,
        candle: str,
        adx_val: float,
        signal_type: str
    ) -> Tuple[int, List[str]]:
        """
        Hitung skor sinyal 0-100 dan kumpulkan alasan.

        Bobot:
        - Trend alignment: 25 poin
        - MACD konfirmasi: 20 poin
        - RSI kondisi: 20 poin
        - Volume: 15 poin
        - ADX trend strength: 10 poin
        - Candlestick: 10 poin
        """
        score = 0
        reasons = []

        # 1. Trend alignment (25 poin)
        if signal_type == "BUY":
            if trend == "UPTREND":
                score += 25
                reasons.append(
                    "✅ Trend naik kuat (EMA 9/20/50 bullish alignment)")
            elif trend == "UPTREND_WEAK":
                score += 15
                reasons.append("⚠️ Trend naik lemah")
            elif trend == "SIDEWAYS":
                score += 5
                reasons.append("↔️ Sideways - waspadai false breakout")
        else:
            if trend == "DOWNTREND":
                score += 25
                reasons.append("✅ Trend turun kuat (EMA bearish alignment)")
            elif trend == "DOWNTREND_WEAK":
                score += 15

        # 2. MACD (20 poin)
        if (signal_type == "BUY" and macd_bull) or (signal_type == "SELL" and not macd_bull):
            score += 20
            reasons.append("✅ MACD konfirmasi sinyal")
        else:
            reasons.append("⚠️ MACD berlawanan dengan sinyal")

        # 3. RSI (20 poin)
        if signal_type == "BUY":
            if 30 <= rsi <= 55:
                score += 20
                reasons.append(f"✅ RSI {rsi:.1f} - zona beli ideal (30-55)")
            elif rsi < 30:
                score += 15
                reasons.append(f"✅ RSI {rsi:.1f} - oversold (peluang rebound)")
            elif rsi <= 65:
                score += 10
                reasons.append(f"⚠️ RSI {rsi:.1f} - mendekati overbought")
            else:
                reasons.append(f"🚫 RSI {rsi:.1f} - overbought, hindari beli")
        else:
            if 45 <= rsi <= 70:
                score += 20
                reasons.append(f"✅ RSI {rsi:.1f} - zona jual ideal")
            elif rsi > 70:
                score += 15
                reasons.append(
                    f"✅ RSI {rsi:.1f} - overbought (peluang koreksi)")

        # 4. Volume (15 poin)
        if vol_ratio >= 2.0:
            score += 15
            reasons.append(
                f"✅ Volume {vol_ratio:.1f}x rata-rata - momentum sangat kuat")
        elif vol_ratio >= 1.5:
            score += 10
            reasons.append(
                f"✅ Volume {vol_ratio:.1f}x rata-rata - konfirmasi kuat")
        elif vol_ratio >= 1.2:
            score += 6
            reasons.append(f"⚠️ Volume {vol_ratio:.1f}x rata-rata - cukup")
        else:
            reasons.append(
                f"🚫 Volume {vol_ratio:.1f}x rata-rata - lemah, waspada")

        # 5. ADX strength (10 poin)
        if adx_val >= 40:
            score += 10
            reasons.append(f"✅ ADX {adx_val:.1f} - trend sangat kuat")
        elif adx_val >= 25:
            score += 7
            reasons.append(f"✅ ADX {adx_val:.1f} - trend kuat")
        elif adx_val >= 15:
            score += 3
            reasons.append(f"⚠️ ADX {adx_val:.1f} - trend lemah")
        else:
            reasons.append(f"🚫 ADX {adx_val:.1f} - tidak ada trend jelas")

        # 6. Candlestick pattern (10 poin)
        bullish_patterns = ["HAMMER_BULLISH", "BULLISH_ENGULFING",
                            "MORNING_STAR_BULLISH", "MARUBOZU_BULLISH"]
        bearish_patterns = ["SHOOTING_STAR_BEARISH",
                            "BEARISH_ENGULFING", "MARUBOZU_BEARISH"]

        if signal_type == "BUY" and candle in bullish_patterns:
            score += 10
            reasons.append(f"✅ Pola candle: {candle}")
        elif signal_type == "SELL" and candle in bearish_patterns:
            score += 10
            reasons.append(f"✅ Pola candle: {candle}")
        elif candle == "DOJI":
            reasons.append("⚠️ Doji - ketidakpastian pasar")

        return min(score, 100), reasons

    def _get_signal_strength(self, score: int) -> str:
        if score >= 75:
            return "STRONG"
        elif score >= 55:
            return "MODERATE"
        else:
            return "WEAK"

    def generate_buy_signal(
        self,
        ticker: str,
        df_5m: pd.DataFrame,
        company_name: str = ""
    ) -> Optional[ScalpSignal]:
        """
        Generate sinyal BUY untuk scalping.

        Kondisi masuk BUY:
        1. Trend bullish (EMA alignment)
        2. RSI tidak overbought (< 65)
        3. MACD bullish crossover atau histogram positif
        4. Volume di atas rata-rata
        5. Harga di atas VWAP
        6. Stochastic keluar dari oversold
        """
        if len(df_5m) < 50:
            return None

        close = df_5m["Close"]
        current_price = float(close.iloc[-1])

        # Hitung semua indikator
        rsi_val = float(self.ind.rsi(close, 9).iloc[-1])
        macd_line, signal_line, histogram = self.ind.macd(close, 12, 26, 9)
        macd_bull = histogram.iloc[-1] > 0 and histogram.iloc[-1] > histogram.iloc[-2]
        vwap_val = float(self.ind.vwap(df_5m).iloc[-1])
        vol_ratio = float(self.ind.volume_ratio(df_5m, 20).iloc[-1])
        atr_val = float(self.ind.atr(df_5m, 14).iloc[-1])
        bb_upper, bb_mid, bb_lower = self.ind.bollinger_bands(close, 20, 2)
        adx_val, plus_di, minus_di = self.ind.adx(df_5m, 14)
        adx = float(adx_val.iloc[-1]) if not np.isnan(adx_val.iloc[-1]) else 15
        k_stoch, d_stoch = self.ind.stochastic(df_5m, 14, 3)
        candle_pattern = self.ind.detect_candlestick_pattern(df_5m)
        trend = self._get_trend(df_5m)
        support, resistance = self._calculate_support_resistance(df_5m)

        # Kondisi wajib BUY
        if rsi_val > 70:
            return None  # Overbought, skip
        if not macd_bull and histogram.iloc[-1] < -0.5:
            return None  # MACD sangat bearish

        # Skor sinyal
        score, reasons = self._score_signal(
            rsi_val, macd_bull, vol_ratio, trend, candle_pattern, adx, "BUY"
        )

        if score < 45:
            return None  # Sinyal terlalu lemah

        # ─── Kalkulasi Entry, TP, SL ───
        # Entry: harga saat ini atau sedikit di bawah (konfirmasi breakout)
        entry = current_price
        entry_zone_low = entry * (1 - 0.002)    # -0.2% dari entry
        entry_zone_high = entry * (1 + 0.003)   # +0.3% dari entry

        # TP berbasis persentase target
        tp1 = round(entry * (1 + self.config["tp1_pct"] / 100), 0)
        tp2 = round(entry * (1 + self.config["tp2_pct"] / 100), 0)
        tp3 = round(entry * (1 + self.config["tp3_pct"] / 100), 0)

        # SL berbasis ATR (dinamis) — ambil mana yang lebih kecil
        sl_atr = entry - (atr_val * self.config["sl_atr_mult"])
        sl_pct_val = entry * (1 - self.config["sl_pct"] / 100)
        # Tidak lebih rendah dari support
        sl = max(sl_atr, sl_pct_val, support * 0.998)

        sl_distance = entry - sl
        tp_distance = tp2 - entry
        rr_ratio = tp_distance / sl_distance if sl_distance > 0 else 0

        # Jika RR < minimum, skip
        if rr_ratio < self.config["min_rr"]:
            # Sesuaikan SL agar RR terpenuhi
            sl = entry - (tp_distance / self.config["min_rr"])
            rr_ratio = self.config["min_rr"]

        sl_pct = ((entry - sl) / entry) * 100

        # VWAP position
        price_vs_vwap = "ABOVE" if current_price > vwap_val else "BELOW"
        if price_vs_vwap == "ABOVE":
            reasons.append(
                f"✅ Harga di atas VWAP ({vwap_val:.0f}) - bullish bias")

        # Bollinger position
        bb_pct = (current_price - float(bb_lower.iloc[-1])) / (
            float(bb_upper.iloc[-1]) - float(bb_lower.iloc[-1]))
        if bb_pct < 0.3:
            bb_pos = "LOWER"
            reasons.append("✅ Dekat lower Bollinger - potensi rebound")
        elif bb_pct > 0.7:
            bb_pos = "UPPER"
        else:
            bb_pos = "MIDDLE"

        open_price = float(df_5m["Open"].iloc[0])
        high_day = float(df_5m["High"].max())
        low_day = float(df_5m["Low"].min())
        volume = int(df_5m["Volume"].sum())
        change_pct = (
            (current_price - float(df_5m["Close"].iloc[-2])) / float(df_5m["Close"].iloc[-2])) * 100

        ticker_clean = ticker.replace(".JK", "")

        return ScalpSignal(
            ticker=ticker,
            ticker_clean=ticker_clean,
            company_name=company_name or ticker_clean,
            signal_type="BUY",
            strength=self._get_signal_strength(score),
            entry_price=round(entry, 0),
            entry_zone_low=round(entry_zone_low, 0),
            entry_zone_high=round(entry_zone_high, 0),
            tp1=round(tp1, 0),
            tp2=round(tp2, 0),
            tp3=round(tp3, 0),
            sl=round(sl, 0),
            rr_ratio=round(rr_ratio, 2),
            target_pct=self.config["tp2_pct"],
            sl_pct=round(sl_pct, 2),
            rsi=round(rsi_val, 1),
            macd_signal="BULLISH" if macd_bull else "NEUTRAL",
            volume_ratio=round(vol_ratio, 2),
            trend=trend,
            bb_position=bb_pos,
            atr=round(atr_val, 0),
            atr_pct=round((atr_val / current_price) * 100, 2),
            current_price=round(current_price, 0),
            open_price=round(open_price, 0),
            high_day=round(high_day, 0),
            low_day=round(low_day, 0),
            change_pct=round(change_pct, 2),
            volume=volume,
            candle_pattern=candle_pattern,
            vwap=round(vwap_val, 0),
            price_vs_vwap=price_vs_vwap,
            signal_score=score,
            reasons=reasons,
            support=round(support, 0),
            resistance=round(resistance, 0),
        )

    def generate_sell_signal(
        self,
        ticker: str,
        df_5m: pd.DataFrame,
        company_name: str = ""
    ) -> Optional[ScalpSignal]:
        """
        Deteksi kondisi BEARISH dan kembalikan sinyal WASPADA.

        Di pasar saham Indonesia TIDAK ada mekanisme short-selling reguler,
        sehingga sinyal ini BUKAN perintah jual/short — melainkan PERINGATAN
        bahwa kondisi teknikal memburuk.

        Berguna untuk:
        - Menghindari beli di kondisi downtrend
        - Mengingatkan pemegang saham untuk pertimbangkan cut-loss
        - Early warning sebelum koreksi lebih dalam
        """
        if len(df_5m) < 50:
            return None

        close = df_5m["Close"]
        current_price = float(close.iloc[-1])

        rsi_val = float(self.ind.rsi(close, 9).iloc[-1])
        macd_line, signal_line, histogram = self.ind.macd(close, 12, 26, 9)
        macd_bear = histogram.iloc[-1] < 0 and histogram.iloc[-1] < histogram.iloc[-2]
        vwap_val = float(self.ind.vwap(df_5m).iloc[-1])
        vol_ratio = float(self.ind.volume_ratio(df_5m, 20).iloc[-1])
        atr_val = float(self.ind.atr(df_5m, 14).iloc[-1])
        adx_val, plus_di, minus_di = self.ind.adx(df_5m, 14)
        adx = float(adx_val.iloc[-1]) if not np.isnan(adx_val.iloc[-1]) else 15
        candle_pattern = self.ind.detect_candlestick_pattern(df_5m)
        trend = self._get_trend(df_5m)
        support, resistance = self._calculate_support_resistance(df_5m)
        bb_upper, bb_mid, bb_lower = self.ind.bollinger_bands(close, 20, 2)

        # Filter: jangan generate waspada jika kondisi tidak jelas bearish
        if rsi_val < 30:
            return None  # Sudah oversold, bukan bearish baru
        if not macd_bear and histogram.iloc[-1] > 0.5:
            return None  # MACD masih bullish

        score, reasons = self._score_signal(
            rsi_val, not macd_bear, vol_ratio, trend, candle_pattern, adx, "SELL"
        )

        if score < 45:
            return None

        # Tambahkan peringatan konteks IDX di paling awal
        reasons.insert(0,
                       "⚠️ Ini SINYAL WASPADA — di BEI tidak ada short selling. "
                       "Hindari posisi baru atau pertimbangkan kurangi eksposur."
                       )

        price_vs_vwap = "ABOVE" if current_price > vwap_val else "BELOW"
        if price_vs_vwap == "BELOW":
            reasons.append(
                f"🔴 Harga di bawah VWAP ({vwap_val:.0f}) — tekanan jual dominan")

        bb_pct = (current_price - float(bb_lower.iloc[-1])) / (
            float(bb_upper.iloc[-1]) - float(bb_lower.iloc[-1]))
        bb_pos = "UPPER" if bb_pct > 0.7 else (
            "LOWER" if bb_pct < 0.3 else "MIDDLE")
        if bb_pos == "UPPER":
            reasons.append(
                "🔴 Harga menyentuh upper Bollinger Band — berisiko koreksi")

        open_price = float(df_5m["Open"].iloc[0])
        high_day = float(df_5m["High"].max())
        low_day = float(df_5m["Low"].min())
        volume = int(df_5m["Volume"].sum())
        change_pct = (
            (current_price - float(df_5m["Close"].iloc[-2])) / float(df_5m["Close"].iloc[-2])) * 100
        ticker_clean = ticker.replace(".JK", "")

        return ScalpSignal(
            ticker=ticker,
            ticker_clean=ticker_clean,
            company_name=company_name or ticker_clean,
            signal_type="WASPADA",
            strength=self._get_signal_strength(score),
            # Tidak ada entry/TP/SL untuk WASPADA
            entry_price=round(current_price, 0),
            entry_zone_low=0.0,
            entry_zone_high=0.0,
            tp1=0.0,
            tp2=0.0,
            tp3=0.0,
            sl=0.0,
            rr_ratio=0.0,
            target_pct=0.0,
            sl_pct=0.0,
            rsi=round(rsi_val, 1),
            macd_signal="BEARISH" if macd_bear else "NEUTRAL",
            volume_ratio=round(vol_ratio, 2),
            trend=trend,
            bb_position=bb_pos,
            atr=round(atr_val, 0),
            atr_pct=round((atr_val / current_price) * 100, 2),
            current_price=round(current_price, 0),
            open_price=round(open_price, 0),
            high_day=round(high_day, 0),
            low_day=round(low_day, 0),
            change_pct=round(change_pct, 2),
            volume=volume,
            candle_pattern=candle_pattern,
            vwap=round(vwap_val, 0),
            price_vs_vwap=price_vs_vwap,
            signal_score=score,
            reasons=reasons,
            support=round(support, 0),
            resistance=round(resistance, 0),
        )
