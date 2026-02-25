"""
Technical Indicators untuk Analisis Saham
Digunakan untuk strategi scalping intraday
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple


class TechnicalIndicators:
    """
    Kumpulan indikator teknikal untuk scalping intraday.
    Semua metode menerima DataFrame OHLCV dan mengembalikan Series/nilai.
    """

    # ─────────────────────────────────────────
    # MOVING AVERAGES
    # ─────────────────────────────────────────

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        """Exponential Moving Average."""
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        """Simple Moving Average."""
        return series.rolling(window=period).mean()

    @staticmethod
    def vwap(df: pd.DataFrame) -> pd.Series:
        """
        Volume Weighted Average Price (VWAP).
        Indikator penting untuk institutional trading level.
        """
        typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
        cumulative_tp_vol = (typical_price * df["Volume"]).cumsum()
        cumulative_vol = df["Volume"].cumsum()
        return cumulative_tp_vol / cumulative_vol

    # ─────────────────────────────────────────
    # MOMENTUM INDICATORS
    # ─────────────────────────────────────────

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """
        Relative Strength Index (RSI).
        > 70: Overbought, < 30: Oversold
        Untuk scalping: gunakan RSI(7) atau RSI(9)
        """
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def macd(
        series: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        MACD (Moving Average Convergence Divergence).

        Returns:
            (macd_line, signal_line, histogram)
        """
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def stochastic(
        df: pd.DataFrame,
        k_period: int = 14,
        d_period: int = 3
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Stochastic Oscillator (%K dan %D).
        > 80: Overbought, < 20: Oversold
        """
        low_min = df["Low"].rolling(window=k_period).min()
        high_max = df["High"].rolling(window=k_period).max()

        k = 100 * (df["Close"] - low_min) / (high_max - low_min)
        d = k.rolling(window=d_period).mean()
        return k, d

    @staticmethod
    def cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
        """
        Commodity Channel Index (CCI).
        > 100: Potential buy signal (breakout)
        < -100: Potential sell signal
        """
        typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
        sma = typical_price.rolling(window=period).mean()
        mean_deviation = typical_price.rolling(window=period).apply(
            lambda x: np.abs(x - x.mean()).mean()
        )
        cci = (typical_price - sma) / (0.015 * mean_deviation)
        return cci

    @staticmethod
    def williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Williams %R.
        0 to -20: Overbought, -80 to -100: Oversold
        """
        high_max = df["High"].rolling(window=period).max()
        low_min = df["Low"].rolling(window=period).min()
        wr = -100 * (high_max - df["Close"]) / (high_max - low_min)
        return wr

    # ─────────────────────────────────────────
    # VOLATILITY INDICATORS
    # ─────────────────────────────────────────

    @staticmethod
    def bollinger_bands(
        series: pd.Series,
        period: int = 20,
        std_dev: float = 2.0
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Bollinger Bands.

        Returns:
            (upper_band, middle_band, lower_band)
        """
        middle = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        return upper, middle, lower

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Average True Range (ATR).
        Digunakan untuk menghitung jarak SL/TP yang dinamis.
        """
        high_low = df["High"] - df["Low"]
        high_close = abs(df["High"] - df["Close"].shift(1))
        low_close = abs(df["Low"] - df["Close"].shift(1))

        true_range = pd.concat(
            [high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.ewm(span=period, adjust=False).mean()
        return atr

    @staticmethod
    def keltner_channels(
        df: pd.DataFrame,
        ema_period: int = 20,
        atr_period: int = 10,
        multiplier: float = 2.0
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Keltner Channels - kombinasi EMA dan ATR.
        Berguna untuk konfirmasi breakout.
        """
        middle = TechnicalIndicators.ema(df["Close"], ema_period)
        atr_val = TechnicalIndicators.atr(df, atr_period)
        upper = middle + (multiplier * atr_val)
        lower = middle - (multiplier * atr_val)
        return upper, middle, lower

    # ─────────────────────────────────────────
    # VOLUME INDICATORS
    # ─────────────────────────────────────────

    @staticmethod
    def obv(df: pd.DataFrame) -> pd.Series:
        """
        On-Balance Volume (OBV).
        Mengukur buying/selling pressure berdasarkan volume.
        """
        obv = (np.sign(df["Close"].diff()) * df["Volume"]).fillna(0).cumsum()
        return obv

    @staticmethod
    def volume_ratio(df: pd.DataFrame, period: int = 20) -> pd.Series:
        """
        Volume Ratio - volume saat ini vs rata-rata.
        > 1.5: Volume tinggi (konfirmasi sinyal kuat)
        > 2.0: Volume sangat tinggi (momentum kuat)
        """
        avg_volume = df["Volume"].rolling(window=period).mean()
        return df["Volume"] / avg_volume

    @staticmethod
    def mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Money Flow Index (MFI) - RSI berbasis volume.
        > 80: Overbought, < 20: Oversold
        """
        typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
        money_flow = typical_price * df["Volume"]

        delta = typical_price.diff()
        positive_flow = money_flow.where(
            delta > 0, 0).rolling(window=period).sum()
        negative_flow = money_flow.where(
            delta < 0, 0).rolling(window=period).sum()

        mfr = positive_flow / negative_flow.replace(0, np.nan)
        mfi = 100 - (100 / (1 + mfr))
        return mfi

    # ─────────────────────────────────────────
    # TREND INDICATORS
    # ─────────────────────────────────────────

    @staticmethod
    def adx(df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Average Directional Index (ADX).
        > 25: Trend kuat, > 40: Trend sangat kuat

        Returns:
            (adx, plus_di, minus_di)
        """
        high = df["High"]
        low = df["Low"]
        close = df["Close"]

        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        atr_val = TechnicalIndicators.atr(df, period)

        plus_di = 100 * \
            (plus_dm.ewm(span=period, adjust=False).mean() / atr_val)
        minus_di = 100 * \
            (minus_dm.ewm(span=period, adjust=False).mean() / atr_val)

        dx = 100 * abs(plus_di - minus_di) / \
            (plus_di + minus_di).replace(0, np.nan)
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    @staticmethod
    def supertrend(
        df: pd.DataFrame,
        period: int = 10,
        multiplier: float = 3.0
    ) -> Tuple[pd.Series, pd.Series]:
        """
        SuperTrend indicator.
        Sangat efektif untuk scalping - memberikan sinyal beli/jual jelas.

        Returns:
            (supertrend_line, trend_direction) — direction: 1 = UP, -1 = DOWN
        """
        atr_val = TechnicalIndicators.atr(df, period)
        hl_avg = (df["High"] + df["Low"]) / 2

        upper_basic = hl_avg + (multiplier * atr_val)
        lower_basic = hl_avg - (multiplier * atr_val)

        upper_band = upper_basic.copy()
        lower_band = lower_basic.copy()

        for i in range(1, len(df)):
            if upper_basic.iloc[i] < upper_band.iloc[i - 1] or df["Close"].iloc[i - 1] > upper_band.iloc[i - 1]:
                upper_band.iloc[i] = upper_basic.iloc[i]
            else:
                upper_band.iloc[i] = upper_band.iloc[i - 1]

            if lower_basic.iloc[i] > lower_band.iloc[i - 1] or df["Close"].iloc[i - 1] < lower_band.iloc[i - 1]:
                lower_band.iloc[i] = lower_basic.iloc[i]
            else:
                lower_band.iloc[i] = lower_band.iloc[i - 1]

        supertrend = pd.Series(index=df.index, dtype=float)
        direction = pd.Series(index=df.index, dtype=int)

        for i in range(1, len(df)):
            if df["Close"].iloc[i] > upper_band.iloc[i - 1]:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
            elif df["Close"].iloc[i] < lower_band.iloc[i - 1]:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
            else:
                supertrend.iloc[i] = supertrend.iloc[i - 1]
                direction.iloc[i] = direction.iloc[i - 1]

        return supertrend, direction

    # ─────────────────────────────────────────
    # CANDLESTICK PATTERNS
    # ─────────────────────────────────────────

    @staticmethod
    def detect_candlestick_pattern(df: pd.DataFrame) -> str:
        """
        Deteksi pola candlestick dasar untuk konfirmasi sinyal.
        Menganalisis 3 candle terakhir.
        """
        if len(df) < 3:
            return "NONE"

        c = df["Close"]
        o = df["Open"]
        h = df["High"]
        l = df["Low"]

        # Candle terakhir
        body = abs(c.iloc[-1] - o.iloc[-1])
        upper_wick = h.iloc[-1] - max(c.iloc[-1], o.iloc[-1])
        lower_wick = min(c.iloc[-1], o.iloc[-1]) - l.iloc[-1]
        total_range = h.iloc[-1] - l.iloc[-1]

        if total_range == 0:
            return "NONE"

        body_ratio = body / total_range

        # Doji - ketidakpastian
        if body_ratio < 0.1:
            return "DOJI"

        # Hammer / Shooting Star
        if lower_wick > 2 * body and upper_wick < body and c.iloc[-1] > o.iloc[-1]:
            return "HAMMER_BULLISH"

        if upper_wick > 2 * body and lower_wick < body and c.iloc[-1] < o.iloc[-1]:
            return "SHOOTING_STAR_BEARISH"

        # Marubozu - momentum kuat
        if body_ratio > 0.8:
            if c.iloc[-1] > o.iloc[-1]:
                return "MARUBOZU_BULLISH"
            else:
                return "MARUBOZU_BEARISH"

        # Bullish Engulfing
        if (c.iloc[-2] < o.iloc[-2] and  # Candle sebelumnya merah
                c.iloc[-1] > o.iloc[-1] and  # Candle ini hijau
                o.iloc[-1] < c.iloc[-2] and  # Open lebih rendah
                c.iloc[-1] > o.iloc[-2]):    # Close lebih tinggi
            return "BULLISH_ENGULFING"

        # Bearish Engulfing
        if (c.iloc[-2] > o.iloc[-2] and
                c.iloc[-1] < o.iloc[-1] and
                o.iloc[-1] > c.iloc[-2] and
                c.iloc[-1] < o.iloc[-2]):
            return "BEARISH_ENGULFING"

        # Morning Star (3 candle)
        if len(df) >= 3:
            if (c.iloc[-3] < o.iloc[-3] and               # Candle 1: bearish
                    # Candle 2: kecil
                    abs(c.iloc[-2] - o.iloc[-2]) < body * 0.5 and
                    # Candle 3: bullish
                    c.iloc[-1] > o.iloc[-1] and
                    c.iloc[-1] > (o.iloc[-3] + c.iloc[-3]) / 2):  # Tutup > midpoint candle 1
                return "MORNING_STAR_BULLISH"

        return "NONE"
