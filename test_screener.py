"""
Quick Test Script - Test komponen tanpa Telegram token
Jalankan: python test_screener.py
"""

import asyncio
import sys
import os

# Tambahkan root ke path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_data_fetcher():
    """Test ambil data dari Yahoo Finance."""
    print("\n" + "="*50)
    print("TEST 1: Data Fetcher (Yahoo Finance)")
    print("="*50)

    from data.fetcher import StockDataFetcher
    fetcher = StockDataFetcher()

    # Test status pasar
    market = fetcher.get_market_status()
    print(f"Status Pasar : {market['status']}")
    print(f"Waktu WIB    : {market['time_wib']}")
    print(f"Tanggal      : {market['date']}")
    print(f"Pasar Buka?  : {market['is_open']}")

    # Test ambil data 1 saham
    print("\nMengambil data BBCA.JK (5 menit, 5 hari)...")
    df = fetcher.get_intraday_data("BBCA.JK", period="5d", interval="5m")
    if df is not None and not df.empty:
        print(f"✅ Data berhasil: {len(df)} candle")
        print(f"   Harga terakhir : Rp {df['Close'].iloc[-1]:,.0f}")
        print(f"   Timestamp      : {df.index[-1]}")
    else:
        print("❌ Gagal ambil data (mungkin pasar tutup/libur)")

    return df


def test_indicators(df):
    """Test kalkulasi indikator teknikal."""
    print("\n" + "="*50)
    print("TEST 2: Technical Indicators")
    print("="*50)

    if df is None or df.empty:
        print("⚠️  Skip - tidak ada data")
        return

    from screener.indicators import TechnicalIndicators
    ind = TechnicalIndicators()

    close = df["Close"]

    # RSI
    rsi = ind.rsi(close, 9)
    print(f"RSI(9)        : {rsi.iloc[-1]:.2f}")

    # MACD
    macd_line, signal_line, hist = ind.macd(close)
    print(f"MACD Histogram: {hist.iloc[-1]:.4f}")
    print(
        f"MACD Signal   : {'BULLISH ↑' if hist.iloc[-1] > 0 else 'BEARISH ↓'}")

    # Bollinger Bands
    upper, mid, lower = ind.bollinger_bands(close)
    current = close.iloc[-1]
    bb_pct = (current - lower.iloc[-1]) / \
        (upper.iloc[-1] - lower.iloc[-1]) * 100
    print(f"Bollinger %   : {bb_pct:.1f}% (0%=lower, 100%=upper)")

    # ATR
    atr = ind.atr(df)
    print(f"ATR(14)       : Rp {atr.iloc[-1]:,.0f}")

    # VWAP
    vwap = ind.vwap(df)
    print(f"VWAP          : Rp {vwap.iloc[-1]:,.0f}")
    print(
        f"vs VWAP       : {'ABOVE ✅' if current > vwap.iloc[-1] else 'BELOW'}")

    # Volume Ratio
    vol_ratio = ind.volume_ratio(df)
    print(f"Volume Ratio  : {vol_ratio.iloc[-1]:.2f}x avg")

    # Candlestick Pattern
    pattern = ind.detect_candlestick_pattern(df)
    print(f"Candle Pattern: {pattern}")

    print("✅ Semua indikator berjalan normal")


def test_signal_generator(df):
    """Test generate sinyal BUY/SELL."""
    print("\n" + "="*50)
    print("TEST 3: Signal Generator (Entry/TP/SL)")
    print("="*50)

    if df is None or df.empty or len(df) < 50:
        print("⚠️  Skip - data tidak cukup")
        return None

    from screener.signal_generator import SignalGenerator
    gen = SignalGenerator()

    # Test BUY signal
    buy = gen.generate_buy_signal("BBCA.JK", df, "Bank Central Asia")
    if buy:
        print(f"✅ Sinyal BUY ditemukan!")
        print(f"   Ticker  : {buy.ticker_clean}")
        print(f"   Skor    : {buy.signal_score}/100 ({buy.strength})")
        print(f"   Entry   : Rp {buy.entry_price:,.0f}")
        print(f"   TP1     : Rp {buy.tp1:,.0f} (+1.5%)")
        print(f"   TP2     : Rp {buy.tp2:,.0f} (+2.5%) ⭐")
        print(f"   TP3     : Rp {buy.tp3:,.0f} (+3.5%)")
        print(f"   SL      : Rp {buy.sl:,.0f} (-{buy.sl_pct:.1f}%)")
        print(f"   R:R     : 1:{buy.rr_ratio:.1f}")
        return buy
    else:
        print("ℹ️  Tidak ada sinyal BUY untuk BBCA saat ini")

    # Test SELL signal
    sell = gen.generate_sell_signal("BBCA.JK", df, "Bank Central Asia")
    if sell:
        print(f"✅ Sinyal SELL ditemukan!")
        print(f"   Entry   : Rp {sell.entry_price:,.0f}")
        print(f"   TP2     : Rp {sell.tp2:,.0f} (-2.5%)")
        print(f"   SL      : Rp {sell.sl:,.0f} (+{sell.sl_pct:.1f}%)")
        return sell

    print("ℹ️  Tidak ada sinyal kuat saat ini (normal jika sideways)")
    return None


def test_formatter(signal):
    """Test format pesan Telegram."""
    print("\n" + "="*50)
    print("TEST 4: Telegram Message Formatter")
    print("="*50)

    if signal is None:
        print("⚠️  Skip - tidak ada sinyal")
        return

    from telegram_bot.formatter import TelegramFormatter
    fmt = TelegramFormatter()

    msg = fmt.format_signal(signal)
    print("Format pesan berhasil! Preview (100 char pertama):")
    print("-" * 50)
    # Strip HTML tags untuk preview
    import re
    clean = re.sub(r'<[^>]+>', '', msg)
    print(clean[:500])
    print("...")
    print(f"\nTotal panjang pesan: {len(msg)} karakter")
    print("✅ Formatter berjalan normal")


async def test_scanner_async():
    """Test scanner untuk beberapa saham."""
    print("\n" + "="*50)
    print("TEST 5: Quick Scanner (3 saham)")
    print("="*50)

    from screener.scanner import StockScanner
    scanner = StockScanner(max_workers=3)

    test_tickers = ["BBCA", "BBRI", "TLKM"]
    print(f"Scanning: {', '.join(test_tickers)}")

    signals = await scanner.scan_all_async(
        watchlist=test_tickers,
        min_score=40,  # Turunkan threshold untuk testing
    )

    if signals:
        print(f"\n✅ {len(signals)} sinyal ditemukan:")
        for s in signals:
            print(
                f"   {s.ticker_clean} | {s.signal_type} | Skor: {s.signal_score}/100 | Entry: Rp {s.entry_price:,.0f}")
    else:
        print("ℹ️  Tidak ada sinyal ditemukan (normal jika pasar sideways/tutup)")

    return signals


def main():
    print("╔══════════════════════════════════════╗")
    print("║  SAHAM SCALPER BOT - TEST SUITE     ║")
    print("╚══════════════════════════════════════╝")

    # Test berurutan
    df = test_data_fetcher()
    test_indicators(df)
    signal = test_signal_generator(df)
    test_formatter(signal)

    # Test async scanner
    signals = asyncio.run(test_scanner_async())

    print("\n" + "="*50)
    print("SEMUA TEST SELESAI")
    print("="*50)
    print("\nLangkah selanjutnya:")
    print("1. Copy .env.example → .env")
    print("2. Isi TELEGRAM_BOT_TOKEN dari @BotFather")
    print("3. Isi TELEGRAM_CHAT_IDS (ID grup/user)")
    print("4. Jalankan: python main.py")
    print("   Atau bot mode: python main.py bot")


if __name__ == "__main__":
    main()
