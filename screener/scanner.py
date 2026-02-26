"""
Stock Scanner - Runner utama screener saham

Alur dua tahap:
  Tahap 1 — Pre-screen (DynamicPreScreener):
    Unduh data harian seluruh IDX_UNIVERSE (~400 saham) secara batch,
    kemudian filter berdasarkan kriteria likuiditas & momentum:
      • Harga penutupan >= min_price
      • Volume MA5 > min_volume_ma5
      • Nilai transaksi MA5 >= min_value_ma5
      • |Perubahan harga 1 hari| >= min_price_change_pct
      • Volume hari ini / Volume MA5 >= 1 + vol_surge_pct
    Hasil: 20–60 kandidat aktif.

  Tahap 2 — Full technical scan (StockScanner):
    Unduh data intraday 5-menit hanya untuk kandidat,
    hitung semua indikator, dan generate sinyal BUY/SELL
    lengkap dengan Entry, TP1/TP2/TP3, SL, dan scoring.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

from data.fetcher import StockDataFetcher
from data.stock_list import (
    IDX_UNIVERSE, SCREENER_WATCHLIST,
    COMPANY_NAMES, get_yahoo_symbol,
    get_effective_universe,
)
from data.dynamic_screener import DynamicPreScreener, ScreenerCriteria
from screener.signal_generator import SignalGenerator, ScalpSignal

logger = logging.getLogger(__name__)


class StockScanner:
    """
    Scanner dua tahap:
      1. DynamicPreScreener  → filter universe harian (cepat, batch)
      2. Analisis teknikal   → intraday 5-menit hanya pada kandidat
    """

    def __init__(
        self,
        max_workers: int = 5,
        criteria: Optional[ScreenerCriteria] = None,
    ):
        self.fetcher = StockDataFetcher()
        self.generator = SignalGenerator()
        self.max_workers = max_workers
        self.pre_screener = DynamicPreScreener(
            criteria=criteria,
            universe=get_effective_universe(),
        )
        self.last_scan_results: List[ScalpSignal] = []
        self.last_scan_time: Optional[str] = None
        self.last_prescreen_summary: Optional[Dict] = None

    def scan_single_stock(self, ticker_raw: str) -> Optional[ScalpSignal]:
        """
        Scan satu saham dan kembalikan sinyal terbaik (BUY/WASPADA).

        Strategi data (store-first):
          1. Coba baca dari Parquet store lokal (instant, no API call)
          2. Jika data lokal masih segar (< 15 menit), gunakan langsung
          3. Jika data lokal terlalu lama / tidak ada, fallback ke live API

        Args:
            ticker_raw: Kode saham tanpa suffix (contoh: BBCA)

        Returns:
            ScalpSignal jika ada sinyal, None jika tidak ada
        """
        ticker = get_yahoo_symbol(ticker_raw)
        company_name = COMPANY_NAMES.get(ticker_raw, ticker_raw)

        df_5m = None
        source = "live"

        # ── Coba baca dari store lokal ──────────────────────────
        try:
            from data.store import get_store
            store = get_store()
            df_store = store.load(ticker_raw, "5m", days=5)

            if df_store is not None and len(df_store) >= 50:
                last_ts = df_store.index.max()
                age_minutes = (
                    datetime.utcnow() - last_ts.to_pydatetime().replace(tzinfo=None)
                ).total_seconds() / 60

                if age_minutes <= 20:  # data segar ≤ 20 menit → pakai store
                    df_5m = df_store
                    source = f"store({age_minutes:.0f}m old)"
                else:
                    logger.debug(
                        f"{ticker_raw}: data store {age_minutes:.0f}m lalu, "
                        f"fallback ke live API"
                    )
        except Exception as se:
            logger.debug(f"{ticker_raw}: gagal baca store: {se}")

        # ── Fallback ke live API ────────────────────────────────
        if df_5m is None:
            df_5m = self.fetcher.get_intraday_data(
                ticker,
                period="5d",
                interval="5m"
            )
            source = "live"

        # ── Load 15m dari store untuk konfirmasi timeframe ───────
        df_15m = None
        try:
            from data.store import get_store as _get_store
            _store = _get_store()
            _df15 = _store.load(ticker_raw, "15m", days=5)
            if _df15 is not None and len(_df15) >= 20:
                df_15m = _df15
        except Exception as _e:
            logger.debug(f"{ticker_raw}: gagal baca store 15m: {_e}")

        if df_5m is None or len(df_5m) < 50:
            logger.info(
                f"[SKIP] {ticker_raw}: data 5m tidak cukup "
                f"({len(df_5m) if df_5m is not None else 0} candle, min 50) [{source}]"
            )
            return None

        logger.debug(f"{ticker_raw}: {len(df_5m)} candle [{source}]")

        try:
            # Generate sinyal BUY
            buy_signal = self.generator.generate_buy_signal(
                ticker, df_5m, company_name, df_15m=df_15m)

            # Generate sinyal WASPADA/SELL
            sell_signal = self.generator.generate_sell_signal(
                ticker, df_5m, company_name, df_15m=df_15m)

            # Pilih sinyal dengan skor lebih tinggi
            if buy_signal and sell_signal:
                result = buy_signal if buy_signal.signal_score >= sell_signal.signal_score else sell_signal
                logger.debug(
                    f"[{result.signal_type}] {ticker_raw}: skor={result.signal_score} "
                    f"vol={result.volume_ratio:.2f}x trend={result.trend}"
                )
                return result
            elif buy_signal:
                logger.debug(
                    f"[BUY] {ticker_raw}: skor={buy_signal.signal_score} "
                    f"vol={buy_signal.volume_ratio:.2f}x trend={buy_signal.trend}"
                )
                return buy_signal
            elif sell_signal:
                logger.debug(
                    f"[WASPADA] {ticker_raw}: skor={sell_signal.signal_score} "
                    f"vol={sell_signal.volume_ratio:.2f}x trend={sell_signal.trend}"
                )
                return sell_signal

            # Tidak ada sinyal — hitung indikator dasar untuk log diagnosis
            try:
                close = df_5m["Close"]
                rsi_val = float(self.generator.ind.rsi(close, 9).iloc[-1])
                _, _, hist = self.generator.ind.macd(close, 12, 26, 9)
                macd_hist_val = float(hist.iloc[-1])
                trend = self.generator._get_trend(df_5m)
                vol_ratio = float(
                    self.generator.ind.volume_ratio(df_5m, 20).iloc[-1])
                logger.info(
                    f"[NO SIGNAL] {ticker_raw}: RSI={rsi_val:.1f} "
                    f"MACD_hist={macd_hist_val:.4f} trend={trend} "
                    f"vol={vol_ratio:.2f}x — tidak memenuhi threshold"
                )
            except Exception:
                logger.info(
                    f"[NO SIGNAL] {ticker_raw}: tidak ada sinyal (skor < 45)")

            return None

        except Exception as e:
            logger.error(f"Error scan {ticker}: {e}")
            try:
                from logs.error_tracker import tracker
                tracker.track(ticker_raw, "scanner.scan_single", e)
            except Exception:
                pass
            return None

    def scan_all(
        self,
        watchlist: Optional[List[str]] = None,
        min_score: int = 55,
        min_volume_ratio: float = 0.0,
        signal_filter: Optional[str] = None,  # "BUY", "SELL", atau None
        skip_prescreen: bool = False,
    ) -> List[ScalpSignal]:
        """
        Scan saham secara dua tahap.

        Tahap 1 — Pre-screen (otomatis jika watchlist=None):
            Filter IDX_UNIVERSE berdasarkan kriteria likuiditas & momentum.
            Saham yang tidak memenuhi kriteria TIDAK di-scan teknikal
            sehingga waktu proses jauh lebih efisien.

        Tahap 2 — Analisis teknikal pada kandidat:
            Intraday 5-menit → RSI, MACD, BB, VWAP, ADX, ATR → sinyal.

        Args:
            watchlist       : Daftar ticker manual (opsional).
                              None  → jadikan IDX_UNIVERSE sebagai pool,
                                      lalu jalankan pre-screener otomatis.
            min_score       : Skor minimum sinyal yang dikembalikan (0–100).
            min_volume_ratio: Filter tambahan rasio volume intraday.
            signal_filter   : "BUY" / "SELL" / None.
            skip_prescreen  : True = lewati tahap 1, langsung scan semua
                              ticker dalam watchlist (berguna untuk debug).

        Returns:
            List[ScalpSignal] terurut dari skor tertinggi.
        """
        start_time = time.time()

        # ── Tahap 1: tentukan kandidat ───────────────────────
        if watchlist is not None:
            # Watchlist manual → skip pre-screener
            candidates = watchlist
            logger.info(
                f"Scan manual: {len(candidates)} saham (pre-screen dilewati)"
            )
        elif skip_prescreen:
            universe = get_effective_universe()
            candidates = universe
            logger.info(
                f"Scan tanpa pre-screen: {len(candidates)} saham (debug mode)"
            )
        else:
            # DEFAULT: pre-screen effective universe dulu
            universe = get_effective_universe()
            logger.info(
                f"Tahap 1 — Pre-screen {len(universe)} saham IDX + custom..."
            )
            self.pre_screener.universe = universe
            candidates = self.pre_screener.run(verbose=True)
            self.last_prescreen_summary = self.pre_screener.summary()

            if not candidates:
                logger.warning(
                    "Pre-screen tidak menghasilkan kandidat. "
                    "Pasar mungkin tutup atau data terbatas. "
                    "Fallback ke SCREENER_WATCHLIST."
                )
                candidates = SCREENER_WATCHLIST

            logger.info(
                f"Tahap 1 selesai: {len(candidates)} kandidat lolos pre-screen "
                f"(dari {len(universe)} saham)"
            )

        # ── Tahap 2: analisis teknikal paralel ───────────────
        logger.info(
            f"Tahap 2 — Analisis teknikal {len(candidates)} kandidat...")

        signals: List[ScalpSignal] = []
        no_signal_count = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ticker = {
                executor.submit(self.scan_single_stock, ticker): ticker
                for ticker in candidates
            }
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    signal = future.result(timeout=30)
                    if signal is not None:
                        signals.append(signal)
                    else:
                        no_signal_count += 1
                except Exception as e:
                    logger.error(f"Error future {ticker}: {e}")
                    no_signal_count += 1

        # ── Log semua sinyal mentah sebelum filter ────────────
        logger.info(
            f"Tahap 2 selesai: {len(signals)} sinyal raw dari {len(candidates)} kandidat "
            f"(no-signal/error: {no_signal_count})"
        )
        if signals:
            for sig in sorted(signals, key=lambda s: s.signal_score, reverse=True):
                logger.info(
                    f"  RAW {sig.signal_type:7s} {sig.ticker_clean:6s} | "
                    f"skor={sig.signal_score:3d} vol={sig.volume_ratio:.2f}x "
                    f"trend={sig.trend}"
                )

        # ── Filter & urutkan ─────────────────────────────────
        after_score = [s for s in signals if s.signal_score >= min_score]
        after_vol = [
            s for s in after_score if s.volume_ratio >= min_volume_ratio]
        filtered = [
            s for s in after_vol
            if signal_filter is None or s.signal_type == signal_filter
        ]
        filtered.sort(key=lambda x: x.signal_score, reverse=True)

        # Log saham yang gugur di tiap filter
        score_rejected = [s for s in signals if s.signal_score < min_score]
        vol_rejected = [
            s for s in after_score if s.volume_ratio < min_volume_ratio]
        if score_rejected:
            logger.info(
                f"  ❌ Gugur filter skor (<{min_score}): "
                + ", ".join(
                    f"{s.ticker_clean}({s.signal_score})"
                    for s in sorted(score_rejected, key=lambda s: s.signal_score, reverse=True)
                )
            )
        if vol_rejected:
            logger.info(
                f"  ❌ Gugur filter volume (<{min_volume_ratio:.1f}x): "
                + ", ".join(
                    f"{s.ticker_clean}({s.volume_ratio:.2f}x)"
                    for s in vol_rejected
                )
            )

        elapsed = time.time() - start_time
        logger.info(
            f"Scan selesai {elapsed:.1f}s | "
            f"Kandidat: {len(candidates)} | "
            f"Sinyal raw: {len(signals)} | "
            f"Lolos semua filter: {len(filtered)}"
        )

        self.last_scan_results = filtered
        from datetime import datetime
        self.last_scan_time = datetime.now().isoformat()

        # Simpan ke disk agar /buy dan /waspada bisa baca data
        # meskipun bot berjalan di proses terpisah atau server restart
        if filtered:
            try:
                from data.signal_cache import save_signals
                save_signals(filtered, self.last_scan_time)
            except Exception as _ce:
                logger.debug(f"Signal cache write skip: {_ce}")

        return filtered

    # ── /info deep analysis ──────────────────────────────────────────────────

    def analyze_stock_info(self, ticker_raw: str) -> dict:
        """
        Analisis mendalam satu saham untuk perintah /info.

        Menggabungkan data harian (tren jangka menengah) dan intraday 5m
        (momentum pendek) untuk memberi gambaran komprehensif:
          - Trend (bullish / bearish / sideways) + kekuatannya
          - Zona support & resistance lewat swing high/low + EMA
          - Potensi ke depan: probabilistik berdasarkan indikator
          - Risiko utama yang perlu diperhatikan
          - Skor confidence mengapa angkanya segitu

        Returns dict dengan key:
          ticker, company_name, last_price, change_pct,
          trend, trend_detail, ema_alignment,
          support, resistance, support2, resistance2,
          rsi, rsi_zone, macd_signal, bb_position,
          volume_ratio, adx, atr_pct,
          potential, potential_detail,
          risk, risk_detail,
          confidence, confidence_reasons,
          signals_found (ScalpSignal | None)
        """
        from data.stock_list import get_yahoo_symbol, COMPANY_NAMES

        company_name = COMPANY_NAMES.get(ticker_raw, ticker_raw)
        result = {
            "ticker": ticker_raw,
            "company_name": company_name,
            "last_price": 0.0,
            "change_pct": 0.0,
            "trend": "UNKNOWN",
            "trend_detail": "Data tidak tersedia",
            "ema_alignment": "N/A",
            "support": 0.0,
            "resistance": 0.0,
            "support2": 0.0,
            "resistance2": 0.0,
            "rsi": 50.0,
            "rsi_zone": "Netral",
            "macd_signal": "NETRAL",
            "bb_position": "MIDDLE",
            "volume_ratio": 1.0,
            "adx": 0.0,
            "atr_pct": 0.0,
            "potential": "NETRAL",
            "potential_detail": [],
            "risk": "SEDANG",
            "risk_detail": [],
            "confidence": 0,
            "confidence_reasons": [],
            "trend_15m": "N/A",
            "signal_obj": None,
        }

        try:
            # ── Load data 5m dari store ─────────────────────────
            df = None
            source = "none"
            try:
                from data.store import get_store
                store = get_store()
                df = store.load(ticker_raw, "5m", days=7)
                if df is not None and len(df) >= 50:
                    source = "store_5m"
            except Exception:
                pass

            if df is None or len(df) < 50:
                # fallback live API
                ticker_yf = get_yahoo_symbol(ticker_raw)
                df = self.fetcher.get_intraday_data(
                    ticker_yf, period="5d", interval="5m")
                source = "live_5m"

            # ── Load data harian untuk tren jangka menengah ─────
            df_1d = None
            try:
                from data.store import get_store
                df_1d = get_store().load(ticker_raw, "1d", days=90)
            except Exception:
                pass

            # ── Load data 15m untuk konfirmasi timeframe ────────
            df_15m = None
            try:
                from data.store import get_store as _gs15
                _df15 = _gs15().load(ticker_raw, "15m", days=5)
                if _df15 is not None and len(_df15) >= 20:
                    df_15m = _df15
            except Exception:
                pass

            if df is None or len(df) < 50:
                result["trend_detail"] = "Data tidak cukup untuk analisis (min 50 candle)"
                result["confidence_reasons"].append(
                    "❌ Data intraday tidak tersedia")
                return result

            # ── Hitung EMA ──────────────────────────────────────
            df = df.copy()
            df["ema9"] = df["Close"].ewm(span=9,  adjust=False).mean()
            df["ema20"] = df["Close"].ewm(span=20, adjust=False).mean()
            df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()

            last = df.iloc[-1]
            prev = df.iloc[-2]

            last_price = float(last["Close"])
            # harga awal sesi ~78 candle 5m = 390m
            open_price = float(df.iloc[-int(min(78, len(df)-1))]["Open"])
            change_pct = (
                last_price - float(df.iloc[-2]["Close"])) / float(df.iloc[-2]["Close"]) * 100
            vol_today = float(last["Volume"])
            vol_avg = float(df["Volume"].rolling(20).mean().iloc[-1])
            volume_ratio = vol_today / vol_avg if vol_avg > 0 else 1.0

            # ── EMA alignment ───────────────────────────────────
            e9 = float(last["ema9"])
            e20 = float(last["ema20"])
            e50 = float(last["ema50"])

            if e9 > e20 > e50:
                ema_align = "BULLISH_FULL"       # golden alignment
                trend = "BULLISH"
            elif e9 > e20 and e9 < e50:
                ema_align = "BULLISH_WEAK"       # EMA9 di atas EMA20 tapi EMA50 masih menekan
                trend = "UPTREND_WEAK"
            elif e9 < e20 < e50:
                ema_align = "BEARISH_FULL"       # death alignment
                trend = "BEARISH"
            elif e9 < e20 and e9 > e50:
                ema_align = "BEARISH_WEAK"
                trend = "DOWNTREND_WEAK"
            else:
                ema_align = "SIDEWAYS"
                trend = "SIDEWAYS"

            # EMA 20 cross dalam 5 candle terakhir?
            ema_cross_up = any(df["ema9"].iloc[i] > df["ema20"].iloc[i] and
                               df["ema9"].iloc[i-1] <= df["ema20"].iloc[i-1]
                               for i in range(-5, 0))
            ema_cross_down = any(df["ema9"].iloc[i] < df["ema20"].iloc[i] and
                                 df["ema9"].iloc[i-1] >= df["ema20"].iloc[i-1]
                                 for i in range(-5, 0))

            # ── RSI ─────────────────────────────────────────────
            delta = df["Close"].diff()
            gain = delta.clip(lower=0).rolling(9).mean()
            loss = (-delta.clip(upper=0)).rolling(9).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi = float((100 - 100 / (1 + rs)).iloc[-1])
            if rsi >= 70:
                rsi_zone = "Overbought — potensi koreksi"
            elif rsi <= 30:
                rsi_zone = "Oversold — potensi reversal naik"
            elif 50 <= rsi < 70:
                rsi_zone = "Bullish Zone (30–70)"
            elif 35 < rsi < 50:
                rsi_zone = "Relatif Lemah"
            else:
                rsi_zone = "Sangat Lemah / Potensi Bounce"

            # ── MACD ─────────────────────────────────────────────
            ema12 = df["Close"].ewm(span=12, adjust=False).mean()
            ema26 = df["Close"].ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal_l = macd_line.ewm(span=9, adjust=False).mean()
            macd_hist = macd_line - signal_l
            macd_sig = "BULLISH" if float(
                macd_line.iloc[-1]) > float(signal_l.iloc[-1]) else "BEARISH"
            macd_cross_up = float(macd_line.iloc[-1]) > float(signal_l.iloc[-1]) and float(
                macd_line.iloc[-2]) <= float(signal_l.iloc[-2])
            macd_cross_down = float(macd_line.iloc[-1]) < float(
                signal_l.iloc[-1]) and float(macd_line.iloc[-2]) >= float(signal_l.iloc[-2])

            # ── Bollinger Bands ──────────────────────────────────
            bb_mid = df["Close"].rolling(20).mean()
            bb_std = df["Close"].rolling(20).std()
            bb_up = bb_mid + 2 * bb_std
            bb_low = bb_mid - 2 * bb_std
            bb_pct = (float(last["Close"]) - float(bb_low.iloc[-1])) / \
                max(float(bb_up.iloc[-1]) - float(bb_low.iloc[-1]), 1)
            if bb_pct > 0.85:
                bb_pos = "UPPER (overbought)"
            elif bb_pct < 0.15:
                bb_pos = "LOWER (oversold)"
            else:
                bb_pos = "MIDDLE"

            # ── ATR ──────────────────────────────────────────────
            hi = df["High"]
            lo = df["Low"]
            cl = df["Close"]
            tr = pd.concat([hi - lo, (hi - cl.shift()).abs(),
                           (lo - cl.shift()).abs()], axis=1).max(axis=1)
            atr = float(tr.rolling(14).mean().iloc[-1])
            atr_pct = atr / last_price * 100

            # ── ADX ──────────────────────────────────────────────
            plus_dm = df["High"].diff().clip(lower=0)
            minus_dm = (-df["Low"].diff()).clip(lower=0)
            tr14 = tr.rolling(14).mean()
            pdm14 = plus_dm.rolling(14).mean()
            mdm14 = minus_dm.rolling(14).mean()
            pdi = 100 * pdm14 / tr14.replace(0, np.nan)
            mdi = 100 * mdm14 / tr14.replace(0, np.nan)
            dx = (abs(pdi - mdi) / (pdi + mdi) * 100).replace(np.nan, 0)
            adx = float(dx.rolling(14).mean().iloc[-1])

            # ── Support & Resistance dari swing high/low ─────────
            window = 10
            highs = df["High"].rolling(window, center=True).max()
            lows = df["Low"].rolling(window, center=True).min()
            is_sh = (df["High"] == highs) & (df["High"] > df["High"].shift(1)) & (
                df["High"] > df["High"].shift(-1))
            is_sl = (df["Low"] == lows) & (df["Low"] < df["Low"].shift(1)) & (
                df["Low"] < df["Low"].shift(-1))

            swing_highs = sorted(
                df["High"][is_sh].dropna().unique(), reverse=True)
            swing_lows = sorted(df["Low"][is_sl].dropna().unique())

            resistance = float(
                next((h for h in swing_highs if h > last_price * 1.002), last_price * 1.03))
            resistance2 = float(
                next((h for h in swing_highs if h > resistance), resistance * 1.02))
            support = float(
                next((l for l in swing_lows if l < last_price * 0.998), last_price * 0.97))
            support2 = float(
                next((l for l in swing_lows if l < support), support * 0.97))

            # Jika ada data harian, pakai high/low 30 hari sebagai R/S sekunder
            if df_1d is not None and len(df_1d) >= 20:
                d1_recent = df_1d.tail(30)
                daily_res = float(d1_recent["High"].max())
                daily_sup = float(d1_recent["Low"].min())
                resistance2 = max(resistance2, daily_res)
                support2 = min(support2,    daily_sup)

            # ── Confidence score ─────────────────────────────────
            conf_score = 50  # base
            conf_reasons = []

            # EMA alignment
            if ema_align == "BULLISH_FULL":
                conf_score += 20
                conf_reasons.append(
                    "✅ EMA9 > EMA20 > EMA50 (golden alignment)")
            elif ema_align == "BEARISH_FULL":
                conf_score -= 20
                conf_reasons.append(
                    "⚠️ EMA9 < EMA20 < EMA50 (death alignment)")
            elif ema_align == "BULLISH_WEAK":
                conf_score += 8
                conf_reasons.append(
                    "⚡ EMA9 > EMA20 tapi EMA50 masih di atas (tren lemah)")
            elif ema_align == "BEARISH_WEAK":
                conf_score -= 8
                conf_reasons.append(
                    "⚡ EMA9 < EMA20 tapi EMA50 masih mendukung")

            # EMA cross recent
            if ema_cross_up:
                conf_score += 12
                conf_reasons.append(
                    "✅ EMA9 baru saja cross UP EMA20 (5 candle terakhir)")
            if ema_cross_down:
                conf_score -= 12
                conf_reasons.append(
                    "⚠️ EMA9 baru saja cross DOWN EMA20 (5 candle terakhir)")

            # RSI
            if 40 <= rsi <= 60:
                conf_score += 5
                conf_reasons.append(
                    "✅ RSI di zona netral-kuat, ruang gerak tersedia")
            elif rsi > 75:
                conf_score -= 15
                conf_reasons.append(
                    f"⚠️ RSI={rsi:.0f} sudah overbought, risiko koreksi tinggi")
            elif rsi < 25:
                conf_score -= 10
                conf_reasons.append(
                    f"⚡ RSI={rsi:.0f} oversold ekstrem, potensi bounce tapi hati-hati")
            elif 60 < rsi < 75:
                conf_score += 10
                conf_reasons.append(
                    f"✅ RSI={rsi:.0f} bullish zona, masih ada ruang naik")

            # MACD
            if macd_sig == "BULLISH":
                conf_score += 10
                conf_reasons.append(
                    "✅ MACD di atas signal line (momentum positif)")
            else:
                conf_score -= 10
                conf_reasons.append(
                    "⚠️ MACD di bawah signal line (momentum negatif)")
            if macd_cross_up:
                conf_score += 8
                conf_reasons.append("✅ MACD fresh bullish crossover!")
            if macd_cross_down:
                conf_score -= 8
                conf_reasons.append("⚠️ MACD fresh bearish crossover")

            # ADX
            if adx >= 25:
                conf_score += 8
                conf_reasons.append(
                    f"✅ ADX={adx:.0f} — tren kuat, momentum valid")
            elif adx < 18:
                conf_score -= 8
                conf_reasons.append(
                    f"⚠️ ADX={adx:.0f} — pasar sideways, tren lemah")
            # 15m timeframe confirmation
            if df_15m is not None:
                try:
                    from screener.signal_generator import SignalGenerator as _SG
                    _gen = _SG()
                    trend_15m = _gen._get_trend(df_15m)
                    _ema12_15 = df_15m["Close"].ewm(
                        span=12, adjust=False).mean()
                    _ema26_15 = df_15m["Close"].ewm(
                        span=26, adjust=False).mean()
                    _macd15_bull = (
                        _ema12_15.iloc[-1] - _ema26_15.iloc[-1]) > 0
                    trend_15m_label = trend_15m.replace("_", " ").title()
                    if trend_15m in ("UPTREND", "UPTREND_WEAK") and trend in ("BULLISH", "UPTREND_WEAK"):
                        conf_score += 10
                        conf_reasons.append(
                            f"\u2705 Konfirmasi 15m: {trend_15m_label} \u2014 aligned (+10)")
                    elif trend_15m in ("DOWNTREND", "DOWNTREND_WEAK") and trend in ("BEARISH", "DOWNTREND_WEAK"):
                        conf_score += 10
                        conf_reasons.append(
                            f"\u2705 Konfirmasi 15m: {trend_15m_label} \u2014 aligned (+10)")
                    elif trend_15m in ("UPTREND", "UPTREND_WEAK") and trend in ("BEARISH", "DOWNTREND_WEAK"):
                        conf_score -= 8
                        conf_reasons.append(
                            f"\u26a0\ufe0f Kontratren 15m: {trend_15m_label} vs 5m bearish (-8)")
                    elif trend_15m in ("DOWNTREND", "DOWNTREND_WEAK") and trend in ("BULLISH", "UPTREND_WEAK"):
                        conf_score -= 8
                        conf_reasons.append(
                            f"\u26a0\ufe0f Kontratren 15m: {trend_15m_label} vs 5m bullish (-8)")
                    else:
                        conf_reasons.append(
                            f"\u2194\ufe0f Konfirmasi 15m: {trend_15m_label} (sideways/netral)")
                    result["trend_15m"] = trend_15m
                except Exception:
                    pass
            # Volume
            if volume_ratio >= 1.5:
                conf_score += 7
                conf_reasons.append(
                    f"✅ Volume {volume_ratio:.1f}x rata-rata (smart money masuk)")
            elif volume_ratio < 0.7:
                conf_score -= 5
                conf_reasons.append(
                    f"⚠️ Volume rendah ({volume_ratio:.1f}x), konfirmasi lemah")

            conf_score = max(10, min(95, conf_score))

            # ── Potential & Risk assessment ──────────────────────
            potential_detail = []
            risk_detail = []

            # Potential
            upside_r1 = (resistance - last_price) / last_price * 100
            upside_r2 = (resistance2 - last_price) / last_price * 100
            potential_detail.append(
                f"📈 Target R1: Rp {resistance:,.0f} (+{upside_r1:.1f}%)")
            potential_detail.append(
                f"📈 Target R2: Rp {resistance2:,.0f} (+{upside_r2:.1f}%)")

            if trend in ("BULLISH", "UPTREND_WEAK") and macd_sig == "BULLISH" and rsi < 70:
                potential = "BULLISH"
                potential_detail.insert(
                    0, "🟢 Kondisi teknikal mendukung kelanjutan naik")
            elif trend in ("BEARISH", "DOWNTREND_WEAK") and macd_sig == "BEARISH":
                potential = "BEARISH"
                potential_detail.insert(
                    0, "🔴 Kondisi teknikal menunjuk potensi lanjut turun")
            elif ema_cross_up or macd_cross_up:
                potential = "POTENSI REVERSAL NAIK"
                potential_detail.insert(
                    0, "⚡ Ada sinyal awal reversal — konfirmasi volume dibutuhkan")
            else:
                potential = "SIDEWAYS / WAIT"
                potential_detail.insert(
                    0, "↔️ Belum ada bias jelas — tunggu breakout atau konfirmasi")

            # Risk
            downside_s1 = (last_price - support) / last_price * 100
            risk_detail.append(
                f"📉 Support S1: Rp {support:,.0f} (-{downside_s1:.1f}%)")
            risk_detail.append(
                f"📉 Support S2: Rp {support2:,.0f} (-{(last_price-support2)/last_price*100:.1f}%)")

            if rsi > 70:
                risk_detail.append(
                    "⚠️ Overbought — risiko profit taking meningkat")
            if adx < 18:
                risk_detail.append(
                    "⚠️ Tren lemah — posisi scalping mudah kena noise")
            if bb_pct > 0.85:
                risk_detail.append(
                    "⚠️ Harga di Upper Bollinger Band — potensi mean-reversion")
            if volume_ratio < 1.0:
                risk_detail.append(
                    "⚠️ Volume di bawah rata-rata — likuiditas intraday berkurang")
            if atr_pct > 3.0:
                risk_detail.append(
                    f"⚠️ ATR tinggi {atr_pct:.1f}% — volatilitas besar, perhitungkan SL lebih lebar")

            if conf_score >= 70:
                risk = "RENDAH-SEDANG"
            elif conf_score >= 50:
                risk = "SEDANG"
            else:
                risk = "TINGGI"

            # ── trend_detail teks ────────────────────────────────
            ema_desc = {
                "BULLISH_FULL":  "EMA9 > EMA20 > EMA50 — uptrend solid",
                "BULLISH_WEAK":  "EMA9 > EMA20 tapi EMA50 masih di atas — momentum membangun",
                "BEARISH_FULL":  "EMA9 < EMA20 < EMA50 — downtrend aktif",
                "BEARISH_WEAK":  "EMA9 < EMA20 tapi masih di atas EMA50 — koreksi short-term",
                "SIDEWAYS":      "EMA9 ≈ EMA20 — konsolidasi / sideways",
            }.get(ema_align, ema_align)

            # ── Juga scan normal untuk ScalpSignal ───────────────
            try:
                sig_obj = self.scan_single_stock(ticker_raw)
            except Exception:
                sig_obj = None

            # ── Tulis hasil ─────────────────────────────────────
            result.update({
                "last_price":        last_price,
                "change_pct":        round(change_pct, 2),
                "trend":             trend,
                "trend_detail":      ema_desc,
                "ema_alignment":     ema_align,
                "ema9":              round(e9, 2),
                "ema20":             round(e20, 2),
                "ema50":             round(e50, 2),
                "ema_cross_up":      ema_cross_up,
                "ema_cross_down":    ema_cross_down,
                "support":           round(support, 2),
                "resistance":        round(resistance, 2),
                "support2":          round(support2, 2),
                "resistance2":       round(resistance2, 2),
                "rsi":               round(rsi, 1),
                "rsi_zone":          rsi_zone,
                "macd_signal":       macd_sig,
                "macd_cross_up":     macd_cross_up,
                "macd_cross_down":   macd_cross_down,
                "bb_position":       bb_pos,
                "volume_ratio":      round(volume_ratio, 2),
                "adx":               round(adx, 1),
                "atr_pct":           round(atr_pct, 2),
                "potential":         potential,
                "potential_detail":  potential_detail,
                "risk":              risk,
                "risk_detail":       risk_detail,
                "confidence":        conf_score,
                "confidence_reasons": conf_reasons,
                "signal_obj":        sig_obj,
                "data_source":       source,
            })

        except Exception as e:
            logger.error(
                f"analyze_stock_info({ticker_raw}): {e}", exc_info=True)
            result["trend_detail"] = f"Error analisis: {str(e)[:100]}"
            result["confidence_reasons"].append(f"❌ Error: {e}")

        return result

    def get_top_signals(self, n: int = 5) -> List[ScalpSignal]:
        """Ambil N sinyal teratas dari scan terakhir (cek disk jika memory kosong)."""
        results = self._get_results_with_cache()
        return results[:n]

    def _get_results_with_cache(self, signal_type: Optional[str] = None) -> List[ScalpSignal]:
        """
        Kembalikan sinyal dari memory.
        Jika memory kosong (belum scan sejak restart), coba load dari cache disk.
        """
        if not self.last_scan_results:
            try:
                from data.signal_cache import load_signals_today
                cached = load_signals_today()
                if cached:
                    logger.info(
                        f"[Scanner] Memory kosong, load {len(cached)} sinyal dari cache disk"
                    )
                    self.last_scan_results = cached
                    # Ambil scan_time dari cache
                    if not self.last_scan_time:
                        self.last_scan_time = cached[0].timestamp if cached else None
            except Exception as e:
                logger.debug(f"[Scanner] Gagal load cache: {e}")

        results = self.last_scan_results
        if signal_type:
            results = [s for s in results if s.signal_type == signal_type]
        return results

    def get_market_summary(self) -> Dict:
        """
        Ringkasan kondisi pasar berdasarkan scan terakhir.
        Jika memory kosong, otomatis load dari cache disk.
        """
        results = self._get_results_with_cache()
        if not results:
            return {"status": "Belum ada data scan"}

        total = len(results)
        buy_count = sum(1 for s in results if s.signal_type == "BUY")
        # WASPADA adalah pengganti SELL di BEI
        sell_count = sum(
            1 for s in results if s.signal_type in ("WASPADA", "SELL"))
        strong_count = sum(1 for s in results if s.strength == "STRONG")
        avg_score = sum(s.signal_score for s in results) / \
            total if total > 0 else 0
        avg_rsi = sum(s.rsi for s in results) / total if total > 0 else 50

        if buy_count > sell_count * 1.5:
            market_bias = "BULLISH"
        elif sell_count > buy_count * 1.5:
            market_bias = "BEARISH"
        else:
            market_bias = "MIXED/SIDEWAYS"

        return {
            "market_bias": market_bias,
            "total_signals": total,
            "buy_signals": buy_count,
            "sell_signals": sell_count,
            "strong_signals": strong_count,
            "avg_score": round(avg_score, 1),
            "avg_rsi": round(avg_rsi, 1),
            "scan_time": self.last_scan_time,
            "top_buys": [
                {"ticker": s.ticker_clean, "score": s.signal_score,
                    "entry": s.entry_price, "tp2": s.tp2}
                for s in results
                if s.signal_type == "BUY"
            ][:3],
            "top_sells": [
                {"ticker": s.ticker_clean, "score": s.signal_score,
                    "entry": s.entry_price}
                for s in results
                if s.signal_type in ("WASPADA", "SELL")
            ][:3],
        }

    async def scan_all_async(
        self,
        watchlist: Optional[List[str]] = None,
        min_score: int = 55,
        min_volume_ratio: float = 0.0,
        signal_filter: Optional[str] = None,
        skip_prescreen: bool = False,
    ) -> List[ScalpSignal]:
        """Versi async dari scan_all untuk digunakan di FastAPI."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.scan_all(
                watchlist, min_score, min_volume_ratio, signal_filter, skip_prescreen
            ),
        )
        return result

    def update_criteria(self, criteria: ScreenerCriteria) -> None:
        """Update kriteria pre-screener tanpa restart scanner."""
        self.pre_screener.criteria = criteria
        # Invalidasi cache agar filter baru langsung aktif
        self.pre_screener._daily_cache = None
        self.pre_screener._cache_time = None
        logger.info(f"Kriteria pre-screener diperbarui: {criteria}")
