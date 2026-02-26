"""
Main FastAPI Application - API Screener Saham Indonesia
Endpoint untuk sinyal scalping, status pasar, dan trigger manual scan
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from config import settings
from data.fetcher import StockDataFetcher
from data.stock_list import IDX_UNIVERSE, get_yahoo_symbol, get_effective_universe
from data.dynamic_screener import ScreenerCriteria
from screener.scanner import StockScanner
from screener.signal_generator import ScalpSignal
from scheduler.job_scheduler import ScanScheduler
from telegram_bot.bot import TelegramNotifier, TelegramBotHandler
from telegram_bot.formatter import TelegramFormatter

# Setup logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ─── Global instances ────────────────────────
fetcher = StockDataFetcher()
scanner = StockScanner(
    max_workers=settings.MAX_SCAN_WORKERS,
    criteria=settings.build_screener_criteria(),
)
notifier = TelegramNotifier(
    settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_IDS)
formatter = TelegramFormatter()
scheduler: Optional[ScanScheduler] = None
bot_handler: Optional[TelegramBotHandler] = None

# ─── Single-instance lock (PID file) ─────────
_SCHEDULER_LOCK = Path(".scheduler.lock")


def _acquire_scheduler_lock() -> bool:
    """
    Coba kuasai single-instance lock untuk scheduler + bot.
    Menggunakan PID file — jika proses lama masih hidup, return False.
    Return True jika berhasil (proses ini boleh start scheduler/bot).
    """
    try:
        if _SCHEDULER_LOCK.exists():
            try:
                old_pid = int(_SCHEDULER_LOCK.read_text().strip())
                if os.name == "nt":
                    import ctypes
                    import ctypes.wintypes
                    h = ctypes.windll.kernel32.OpenProcess(0x0400, False, old_pid)
                    if h:
                        code = ctypes.wintypes.DWORD()
                        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
                        ctypes.windll.kernel32.CloseHandle(h)
                        if code.value == 259:  # STILL_ACTIVE
                            return False
                else:
                    os.kill(old_pid, 0)  # raises OSError kalau proses mati
                    return False
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                pass  # proses lama sudah mati — ambil alih lock
        _SCHEDULER_LOCK.write_text(str(os.getpid()))
        return True
    except Exception:
        return True  # fail-open: lebih baik start daripada tidak sama sekali


def _release_scheduler_lock():
    try:
        _SCHEDULER_LOCK.unlink(missing_ok=True)
    except Exception:
        pass


# ─── Lifespan (startup/shutdown) ─────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup dan shutdown hooks."""
    global scheduler, bot_handler

    logger.info("=== SAHAM SCALPER API STARTING ===")

    # Validasi config
    try:
        settings.validate()
    except ValueError as e:
        logger.warning(f"Config warning: {e}")

    # ── Single-instance guard ──────────────────────────────────────────────
    # Uvicorn tidak men-set APP_WORKER_ID secara otomatis, sehingga env var
    # tersebut tidak bisa diandalkan untuk membedakan worker.
    # Solusi: PID file lock — hanya proses pertama yang berhasil menulis PID
    # yang boleh menjalankan scheduler dan bot polling.
    is_main_worker = _acquire_scheduler_lock()

    if not is_main_worker:
        logger.info(
            f"ℹ️ PID {os.getpid()}: proses lain sudah menjalankan scheduler/bot. "
            "Worker ini hanya melayani HTTP request."
        )

    # ── Test koneksi Telegram (hanya di main worker) ───────────────────────
    if is_main_worker and settings.TELEGRAM_BOT_TOKEN:
        connected = await notifier.test_connection()
        if connected:
            logger.info("✅ Telegram bot terhubung")
        else:
            logger.warning("⚠️ Telegram bot tidak terhubung")

    # ── Scheduler (hanya di main worker) ──────────────────────────────────
    if is_main_worker:
        scheduler = ScanScheduler(
            scanner=scanner,
            fetcher=fetcher,
            telegram_token=settings.TELEGRAM_BOT_TOKEN,
            chat_ids=settings.TELEGRAM_CHAT_IDS,
            scan_interval_minutes=settings.SCAN_INTERVAL_MINUTES,
        )
        scheduler.start()
        logger.info("✅ Scheduler dimulai")
    else:
        logger.info("ℹ️ Scheduler dilewati (bukan main worker)")

    # ── Telegram bot handler / polling (hanya di main worker) ─────────────
    if is_main_worker and settings.TELEGRAM_BOT_TOKEN:
        bot_handler = TelegramBotHandler(
            token=settings.TELEGRAM_BOT_TOKEN,
            chat_ids=settings.TELEGRAM_CHAT_IDS,
            scanner=scanner,
        )
        try:
            await bot_handler.start_async()
            logger.info("✅ Telegram bot handler dimulai")
        except Exception as e:
            logger.warning(f"⚠️ Telegram bot handler gagal dimulai: {e}")
            bot_handler = None
    elif not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("⚠️ TELEGRAM_BOT_TOKEN tidak diset, bot handler dilewati")
    else:
        logger.info("ℹ️ Bot polling dilewati (bukan main worker)")

    logger.info(
        f"✅ API berjalan di http://{settings.API_HOST}:{settings.API_PORT}")
    logger.info("=== SIAP MELAYANI PERMINTAAN ===")

    yield  # === Aplikasi berjalan ===

    # Shutdown
    logger.info("=== SAHAM SCALPER API SHUTTING DOWN ===")
    if bot_handler:
        await bot_handler.stop_async()
    if scheduler:
        scheduler.stop()
    _release_scheduler_lock()
    logger.info("Shutdown selesai")


# ─── FastAPI App ─────────────────────────────
app = FastAPI(
    title="Saham Scalper API",
    description="""
## 📈 API Screener Saham Indonesia + Telegram Notifier

Sistem screener saham IDX/BEI dengan strategi **scalping intraday** yang mencari peluang profit **2-3%**.

### Fitur:
- Pre-screen dinamis ~400 saham IDX berdasarkan kriteria volume/momentum
- Sinyal BUY/SELL dengan Entry, TP1/TP2/TP3, SL
- Analisis multi-indikator (RSI, MACD, Bollinger, VWAP, ADX, SuperTrend)
- Notifikasi otomatis ke Telegram (grup/pribadi)
- Scheduler berbasis jam bursa BEI

### Data Source:
- Yahoo Finance (`yfinance`) - data intraday 5 menit
- Saham Indonesia suffix `.JK`
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Auth (simple bearer token) ──────────────
security = HTTPBearer(auto_error=False)


def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if settings.API_SECRET_KEY == "changeme-secret-key":
        return True  # Skip auth jika masih key default
    if not credentials or credentials.credentials != settings.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="API key tidak valid")
    return True


# ════════════════════════════════════════════════
# PYDANTIC MODELS (Response Schema)
# ════════════════════════════════════════════════

class SignalResponse(BaseModel):
    ticker: str
    ticker_clean: str
    company_name: str
    signal_type: str
    strength: str
    signal_score: int
    entry_price: float
    entry_zone_low: float
    entry_zone_high: float
    tp1: float
    tp2: float
    tp3: float
    sl: float
    rr_ratio: float
    target_pct: float
    sl_pct: float
    rsi: float
    macd_signal: str
    volume_ratio: float
    trend: str
    bb_position: str
    atr: float
    atr_pct: float
    current_price: float
    open_price: float
    high_day: float
    low_day: float
    change_pct: float
    volume: int
    candle_pattern: str
    vwap: float
    price_vs_vwap: str
    support: float
    resistance: float
    reasons: List[str]
    timestamp: str


class ScanRequest(BaseModel):
    tickers: Optional[List[str]] = None
    min_score: int = 50
    min_volume_ratio: float = 0.0   # 0.0 = tidak ada filter volume (hanya skor)
    signal_filter: Optional[str] = None  # "BUY", "SELL", None
    send_telegram: bool = False
    skip_prescreen: bool = False  # True = scan seluruh IDX_UNIVERSE langsung


class UpdateCriteriaRequest(BaseModel):
    """Hot-reload kriteria pre-screener tanpa restart server."""
    min_price: Optional[float] = None
    min_volume_ma5: Optional[float] = None
    min_value_ma5: Optional[float] = None
    min_price_change_pct: Optional[float] = None
    min_vol_surge_pct: Optional[float] = None
    max_price: Optional[float] = None


class MarketStatusResponse(BaseModel):
    status: str
    session: str
    is_open: bool
    time_wib: str
    date: str


def signal_to_response(s: ScalpSignal) -> SignalResponse:
    return SignalResponse(
        ticker=s.ticker,
        ticker_clean=s.ticker_clean,
        company_name=s.company_name,
        signal_type=s.signal_type,
        strength=s.strength,
        signal_score=s.signal_score,
        entry_price=s.entry_price,
        entry_zone_low=s.entry_zone_low,
        entry_zone_high=s.entry_zone_high,
        tp1=s.tp1, tp2=s.tp2, tp3=s.tp3, sl=s.sl,
        rr_ratio=s.rr_ratio,
        target_pct=s.target_pct,
        sl_pct=s.sl_pct,
        rsi=s.rsi,
        macd_signal=s.macd_signal,
        volume_ratio=s.volume_ratio,
        trend=s.trend,
        bb_position=s.bb_position,
        atr=s.atr,
        atr_pct=s.atr_pct,
        current_price=s.current_price,
        open_price=s.open_price,
        high_day=s.high_day,
        low_day=s.low_day,
        change_pct=s.change_pct,
        volume=s.volume,
        candle_pattern=s.candle_pattern,
        vwap=s.vwap,
        price_vs_vwap=s.price_vs_vwap,
        support=s.support,
        resistance=s.resistance,
        reasons=s.reasons,
        timestamp=s.timestamp,
    )


# ════════════════════════════════════════════════
# ENDPOINTS
# ════════════════════════════════════════════════

@app.get("/", tags=["Info"])
async def root():
    """Info API dan status."""
    market = fetcher.get_market_status()
    return {
        "name": "Saham Scalper API",
        "version": "1.0.0",
        "description": "IDX Stock Screener dengan sinyal scalping intraday",
        "market": market,
        "docs": "/docs",
        "endpoints": {
            "scan_all": "POST /scan",
            "scan_stock": "GET /signal/{ticker}",
            "top_signals": "GET /signals/top",
            "market_status": "GET /market",
            "watchlist": "GET /watchlist",
            "prescreen_run": "POST /prescreen/run",
            "prescreen_results": "GET /prescreen/results",
            "prescreen_criteria": "PATCH /prescreen/criteria",
            "scheduler_jobs": "GET /scheduler/jobs",
            "manual_trigger": "POST /scheduler/trigger",
            "data_fetch": "POST /data/fetch",
            "data_update": "POST /data/update",
            "data_status": "GET /data/status",
            "errors_recent": "GET /errors/recent",
            "errors_stats": "GET /errors/stats",
        },
        "universe_size": len(get_effective_universe()),
        "prescreen_criteria": {
            "min_price": scanner.pre_screener.criteria.min_price,
            "min_volume_ma5": scanner.pre_screener.criteria.min_volume_ma5,
            "min_value_ma5": scanner.pre_screener.criteria.min_value_ma5,
            "min_price_change_pct": scanner.pre_screener.criteria.min_price_change_pct,
            "min_vol_surge_pct": scanner.pre_screener.criteria.min_vol_surge_pct,
        }
    }


@app.get("/market", response_model=MarketStatusResponse, tags=["Market"])
async def get_market_status():
    """Status pasar BEI saat ini."""
    return fetcher.get_market_status()


@app.get("/watchlist", tags=["Market"])
async def get_watchlist():
    """Universe IDX yang akan di-pre-screen."""
    c = scanner.pre_screener.criteria
    return {
        "total_universe": len(get_effective_universe()),
        "tickers": get_effective_universe(),
        "prescreen_criteria": {
            "min_price": c.min_price,
            "min_volume_ma5": c.min_volume_ma5,
            "min_value_ma5": c.min_value_ma5,
            "min_price_change_pct": c.min_price_change_pct,
            "min_vol_surge_pct": c.min_vol_surge_pct,
            "max_price": c.max_price,
        },
        "description": "Pre-screen dinamis seluruh saham IDX berdasarkan kriteria volume/momentum"
    }


@app.post("/scan", response_model=List[SignalResponse], tags=["Screener"])
async def run_scan(
    req: ScanRequest,
    background_tasks: BackgroundTasks,
    _: bool = Depends(verify_api_key)
):
    """
    Jalankan scan screener.

    - **tickers**: (opsional) Kode saham custom, default: seluruh watchlist
    - **min_score**: Skor minimum 0-100 (default: 55)
    - **signal_filter**: Filter "BUY"/"SELL"/null
    - **send_telegram**: Kirim hasil ke Telegram
    """
    try:
        signals = await scanner.scan_all_async(
            watchlist=req.tickers,
            min_score=req.min_score,
            min_volume_ratio=req.min_volume_ratio,
            signal_filter=req.signal_filter,
            skip_prescreen=req.skip_prescreen,
        )

        if req.send_telegram and signals:
            market = fetcher.get_market_status()
            background_tasks.add_task(
                _send_telegram_background,
                signals,
                market
            )

        return [signal_to_response(s) for s in signals]

    except Exception as e:
        logger.error(f"Error scan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _send_telegram_background(signals, market):
    """Background task untuk kirim Telegram."""
    try:
        await notifier.send_summary(signals, market)
        await asyncio.sleep(2)
        await notifier.send_signals_batch(signals, max_signals=settings.MAX_SIGNALS_PER_SCAN)
    except Exception as e:
        logger.error(f"Error send telegram background: {e}")


@app.get("/signal/{ticker}", response_model=Optional[SignalResponse], tags=["Screener"])
async def get_signal_for_ticker(
    ticker: str,
    _: bool = Depends(verify_api_key)
):
    """
    Dapatkan sinyal untuk satu saham.

    - **ticker**: Kode saham (contoh: BBCA, BBRI, TLKM)
    """
    ticker_clean = ticker.upper().strip().replace(".JK", "")
    signal = scanner.scan_single_stock(ticker_clean)

    if signal is None:
        return None

    return signal_to_response(signal)


@app.get("/signals/top", response_model=List[SignalResponse], tags=["Screener"])
async def get_top_signals(
    n: int = Query(default=5, ge=1, le=20,
                   description="Jumlah sinyal teratas"),
    signal_type: Optional[str] = Query(
        default=None, description="Filter: BUY atau SELL"),
):
    """
    Tampilkan N sinyal teratas dari scan terakhir.
    Gunakan /scan dahulu untuk memperbarui data.
    """
    signals = scanner.last_scan_results

    if signal_type:
        signals = [s for s in signals if s.signal_type == signal_type.upper()]

    top = signals[:n]
    return [signal_to_response(s) for s in top]


@app.get("/signals/summary", tags=["Screener"])
async def get_market_summary():
    """Ringkasan kondisi pasar dari scan terakhir."""
    market = fetcher.get_market_status()
    summary = scanner.get_market_summary()
    return {
        "market_status": market,
        "scan_summary": summary
    }


@app.post("/telegram/test", tags=["Telegram"])
async def test_telegram(_: bool = Depends(verify_api_key)):
    """Test koneksi dan kirim pesan test ke Telegram."""
    connected = await notifier.test_connection()
    if not connected:
        raise HTTPException(status_code=503, detail="Bot tidak terhubung")

    await notifier.send_message(
        "✅ <b>Test Notifikasi Berhasil!</b>\n"
        "Bot Saham Scalper terhubung dan siap mengirim sinyal."
    )
    return {"status": "success", "message": "Pesan test terkirim"}


@app.post("/telegram/send-signal/{ticker}", tags=["Telegram"])
async def send_signal_to_telegram(
    ticker: str,
    _: bool = Depends(verify_api_key)
):
    """Kirim sinyal saham tertentu ke Telegram secara manual."""
    ticker_clean = ticker.upper().strip().replace(".JK", "")
    signal = scanner.scan_single_stock(ticker_clean)

    if signal is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tidak ada sinyal untuk {ticker_clean}"
        )

    success = await notifier.send_signal(signal)
    return {
        "status": "sent" if success else "failed",
        "ticker": ticker_clean,
        "signal_type": signal.signal_type,
        "score": signal.signal_score
    }


@app.get("/scheduler/jobs", tags=["Scheduler"])
async def get_scheduler_jobs(_: bool = Depends(verify_api_key)):
    """Informasi semua job scheduler yang aktif."""
    if scheduler is None:
        return {"status": "scheduler belum diinisialisasi", "jobs": []}
    return {
        "total_jobs": len(scheduler.scheduler.get_jobs()),
        "jobs": scheduler.get_jobs_info()
    }


@app.post("/scheduler/trigger", tags=["Scheduler"])
async def trigger_manual_scan(
    background_tasks: BackgroundTasks,
    _: bool = Depends(verify_api_key)
):
    """
    Trigger scan manual di luar jadwal.
    Hasilnya dikirim ke Telegram.
    """
    background_tasks.add_task(_manual_trigger_scan)
    return {"status": "scanning", "message": "Scan manual dimulai, hasil dikirim ke Telegram"}


async def _manual_trigger_scan():
    """Background task scan manual."""
    try:
        signals = await scanner.scan_all_async(min_score=settings.MIN_SIGNAL_SCORE)
        market = fetcher.get_market_status()
        await notifier.send_summary(signals, market)
        if signals:
            await asyncio.sleep(2)
            await notifier.send_signals_batch(signals, max_signals=settings.MAX_SIGNALS_PER_SCAN)
    except Exception as e:
        logger.error(f"Error manual trigger: {e}", exc_info=True)


# ════════════════════════════════════════════════
# PRE-SCREEN ENDPOINTS
# ════════════════════════════════════════════════

@app.post("/prescreen/run", tags=["Pre-Screen"])
async def run_prescreen(
    verbose: bool = False,
    _: bool = Depends(verify_api_key)
):
    """
    Jalankan pre-screener terhadap seluruh IDX_UNIVERSE.

    Mengembalikan daftar kandidat yang lolos kriteria + ringkasan top movers.
    """
    try:
        loop = asyncio.get_event_loop()
        candidates = await loop.run_in_executor(
            None, lambda: scanner.pre_screener.run(verbose=verbose)
        )
        summary = scanner.last_prescreen_summary or scanner.pre_screener.summary()
        return {
            "total_universe": len(IDX_UNIVERSE),
            "total_candidates": len(candidates),
            "candidates": candidates,
            "summary": summary,
            "criteria": {
                "min_price": scanner.pre_screener.criteria.min_price,
                "min_volume_ma5": scanner.pre_screener.criteria.min_volume_ma5,
                "min_value_ma5": scanner.pre_screener.criteria.min_value_ma5,
                "min_price_change_pct": scanner.pre_screener.criteria.min_price_change_pct,
                "min_vol_surge_pct": scanner.pre_screener.criteria.min_vol_surge_pct,
                "max_price": scanner.pre_screener.criteria.max_price,
            }
        }
    except Exception as e:
        logger.error(f"Error prescreen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/prescreen/results", tags=["Pre-Screen"])
async def get_prescreen_results(_: bool = Depends(verify_api_key)):
    """
    Hasil pre-screen terakhir (detail semua saham: lolos & ditolak).

    Cache berlaku 5 menit. Jalankan POST /prescreen/run untuk memperbarui.
    """
    raw = scanner.pre_screener.last_results
    if not raw:
        return {
            "message": "Belum ada hasil pre-screen. Jalankan POST /prescreen/run terlebih dahulu.",
            "passed": [],
            "failed": []
        }
    passed = [r.__dict__ for r in raw if r.passed]
    failed = [r.__dict__ for r in raw if not r.passed]
    return {
        "total": len(raw),
        "passed": len(passed),
        "failed": len(failed),
        "passed_list": passed,
        "failed_list": failed,
    }


@app.patch("/prescreen/criteria", tags=["Pre-Screen"])
async def update_prescreen_criteria(
    req: UpdateCriteriaRequest,
    _: bool = Depends(verify_api_key)
):
    """
    Hot-reload kriteria pre-screener tanpa restart server.

    Hanya field yang dikirim yang akan diperbarui.
    Cache otomatis dihapus setelah update.
    """
    current = scanner.pre_screener.criteria
    new_criteria = ScreenerCriteria(
        min_price=req.min_price if req.min_price is not None else current.min_price,
        min_volume_ma5=req.min_volume_ma5 if req.min_volume_ma5 is not None else current.min_volume_ma5,
        min_value_ma5=req.min_value_ma5 if req.min_value_ma5 is not None else current.min_value_ma5,
        min_price_change_pct=req.min_price_change_pct if req.min_price_change_pct is not None else current.min_price_change_pct,
        min_vol_surge_pct=req.min_vol_surge_pct if req.min_vol_surge_pct is not None else current.min_vol_surge_pct,
        max_price=req.max_price if req.max_price is not None else current.max_price,
    )
    scanner.update_criteria(new_criteria)
    logger.info(f"Pre-screen criteria updated: {new_criteria}")
    return {
        "status": "updated",
        "message": "Kriteria diperbarui. Cache dihapus, pre-screen berikutnya menggunakan kriteria baru.",
        "new_criteria": {
            "min_price": new_criteria.min_price,
            "min_volume_ma5": new_criteria.min_volume_ma5,
            "min_value_ma5": new_criteria.min_value_ma5,
            "min_price_change_pct": new_criteria.min_price_change_pct,
            "min_vol_surge_pct": new_criteria.min_vol_surge_pct,
            "max_price": new_criteria.max_price,
        }
    }


# ════════════════════════════════════════════════
# DATA CRAWL ENDPOINTS
# ════════════════════════════════════════════════

class FetchRequest(BaseModel):
    tickers: Optional[List[str]] = None       # None = seluruh IDX_UNIVERSE
    period: Optional[str] = None              # "5y", "2y", dll. (harian)
    intraday_period: Optional[str] = None     # "60d", "30d" (5m/15m)
    interval: str = "all"                     # "1d", "5m", "15m", "all"
    workers: Optional[int] = None


@app.post("/data/fetch", tags=["Data"])
async def trigger_data_fetch(
    req: FetchRequest,
    background_tasks: BackgroundTasks,
    _: bool = Depends(verify_api_key),
):
    """
    Trigger crawl historis OHLCV di background.

    - interval="1d"  → hanya data harian (cepat, ~5–15 menit)
    - interval="5m"  → hanya intraday 5m (lebih lama)
    - interval="all" → keduanya (default)

    Gunakan **GET /data/status** untuk memantau progress.
    """
    from data.crawler import get_crawl_status, _status as crawl_status_obj

    current = get_crawl_status()
    if current["state"] == "running":
        return {
            "status": "already_running",
            "message": "Crawl sedang berlangsung. Pantau progress via GET /data/status",
            "progress": current,
        }

    tickers = req.tickers or get_effective_universe()

    background_tasks.add_task(
        _background_crawl,
        tickers=tickers,
        period=req.period or settings.CRAWL_HISTORICAL_PERIOD,
        intraday_period=req.intraday_period or settings.CRAWL_INTRADAY_PERIOD,
        interval=req.interval,
        workers=req.workers or settings.CRAWL_WORKERS,
    )

    return {
        "status": "started",
        "message": f"Crawl dimulai untuk {len(tickers)} saham (interval={req.interval})",
        "tickers": len(tickers),
        "interval": req.interval,
    }


async def _background_crawl(
    tickers: List[str],
    period: str,
    intraday_period: str,
    interval: str,
    workers: int,
):
    """Background task untuk crawl historis."""
    from data.crawler import DataCrawler, get_store
    from data.store import get_store as gs

    crawler = DataCrawler(
        store=gs(),
        workers=workers,
        batch_size=settings.CRAWL_BATCH_SIZE,
        delay_seconds=settings.CRAWL_DELAY_SECONDS,
    )

    loop = asyncio.get_event_loop()

    try:
        if interval in ("1d", "all"):
            await loop.run_in_executor(
                None,
                lambda: crawler.crawl_historical(
                    tickers, period=period, interval="1d")
            )

        if interval in ("5m", "all"):
            await loop.run_in_executor(
                None,
                lambda: crawler.crawl_intraday(
                    tickers, period=intraday_period, interval="5m")
            )

        if interval in ("15m", "all"):
            await loop.run_in_executor(
                None,
                lambda: crawler.crawl_intraday(
                    tickers, period=intraday_period, interval="15m")
            )
    except Exception as e:
        logger.error(f"Background crawl error: {e}", exc_info=True)


@app.post("/data/update", tags=["Data"])
async def trigger_incremental_update(
    background_tasks: BackgroundTasks,
    tickers: Optional[List[str]] = None,
    _: bool = Depends(verify_api_key),
):
    """
    Trigger incremental update (ambil candle terbaru saja).
    Cocok dipanggil manual untuk memperbarui store sebelum scan.
    """
    ticker_list = tickers or get_effective_universe()
    background_tasks.add_task(_background_update, ticker_list)
    return {
        "status": "started",
        "message": f"Incremental update dimulai untuk {len(ticker_list)} saham",
        "tickers": len(ticker_list),
    }


async def _background_update(tickers: List[str]):
    from data.crawler import get_crawler
    loop = asyncio.get_event_loop()
    try:
        crawler = get_crawler()
        result = await loop.run_in_executor(
            None,
            lambda: crawler.update_latest(tickers, interval="5m")
        )
        logger.info(
            f"[API] Incremental update selesai: "
            f"{result.get('updated', 0)} diperbarui, "
            f"+{result.get('new_rows', 0)} baris"
        )
    except Exception as e:
        logger.error(f"Background update error: {e}", exc_info=True)


@app.get("/data/status", tags=["Data"])
async def get_data_status(_: bool = Depends(verify_api_key)):
    """
    Status crawl data saat ini (progress, error summary, store stats).
    """
    from data.crawler import get_crawl_status
    from data.store import get_store

    crawl = get_crawl_status()
    try:
        store_stats = get_store().stats()
    except Exception:
        store_stats = {}

    return {
        "crawl": crawl,
        "store": store_stats,
    }


# ════════════════════════════════════════════════
# ERROR TRACKING ENDPOINTS
# ════════════════════════════════════════════════

@app.get("/errors/recent", tags=["Errors"])
async def get_recent_errors(
    n: int = Query(default=50, ge=1, le=500,
                   description="Jumlah error terbaru"),
    _: bool = Depends(verify_api_key),
):
    """
    Tampilkan N error request terbaru (yfinance timeout, empty data, dll.).
    Berguna untuk diagnosa saham mana yang sering gagal di-fetch.
    """
    from logs.error_tracker import tracker
    return {
        "total_in_buffer": len(tracker.get_recent(500)),
        "errors": tracker.get_recent(n),
    }


@app.get("/errors/stats", tags=["Errors"])
async def get_error_stats(_: bool = Depends(verify_api_key)):
    """
    Statistik error: breakdown per ticker, per operasi, per tipe error, per jam.
    """
    from logs.error_tracker import tracker
    return tracker.get_stats()


@app.delete("/errors/clear", tags=["Errors"])
async def clear_errors(_: bool = Depends(verify_api_key)):
    """Hapus buffer error in-memory (file JSONL tidak terpengaruh)."""
    from logs.error_tracker import tracker
    n = tracker.clear()
    return {"status": "cleared", "removed": n}


# ════════════════════════════════════════════════
# PROXY / NETWORK STATUS
# ════════════════════════════════════════════════


@app.get("/proxy/status", tags=["Network"])
async def proxy_status(_: bool = Depends(verify_api_key)):
    """
    Status proxy manager dan adaptive rate limiter.

    Mengembalikan:
    - mode proxy (off / single / rotate)
    - jumlah proxy aktif / blacklisted
    - delay rate limiter saat ini
    - recent error rate
    """
    result: dict = {}
    try:
        from network.proxy_manager import get_proxy_manager
        result["proxy"] = get_proxy_manager().status()
    except Exception as e:
        result["proxy"] = {"error": str(e)}
    try:
        from network.rate_limiter import get_rate_limiter
        result["rate_limiter"] = get_rate_limiter().status()
    except Exception as e:
        result["rate_limiter"] = {"error": str(e)}
    return result


# ════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    # Mode: api (default) atau bot (standalone polling tanpa API server)
    mode = sys.argv[1] if len(sys.argv) > 1 else "api"

    if mode == "bot":
        # Jalankan Telegram bot dalam mode polling standalone (tanpa API server)
        logger.info("Menjalankan dalam mode BOT POLLING standalone...")
        bot = TelegramBotHandler(
            token=settings.TELEGRAM_BOT_TOKEN,
            chat_ids=settings.TELEGRAM_CHAT_IDS,
            scanner=scanner
        )
        bot.run_polling()
    else:
        # ── Production / Development API server ──
        # Bot handler + scheduler otomatis dimulai via lifespan (startup hook),
        # dijaga oleh PID file lock agar hanya 1 proses yang menjalankannya.
        #
        # CATATAN PENTING: Bot polling (getUpdates) tidak kompatibel dengan
        # multi-process. Uvicorn tidak men-set worker ID secara otomatis,
        # sehingga UVICORN_WORKERS selalu dipaksa ke 1 di sini.
        # Jika butuh multi-worker di production, gunakan webhook (bukan polling).
        workers = 1  # paksa single process — polling tidak kompatibel multi-worker
        if settings.UVICORN_WORKERS > 1:
            logger.warning(
                f"⚠️ UVICORN_WORKERS={settings.UVICORN_WORKERS} diabaikan. "
                "Bot polling (getUpdates) hanya bisa berjalan di 1 proses. "
                "Gunakan webhook untuk deployment multi-worker."
            )

        logger.info(
            f"Menjalankan API server: "
            f"http://{settings.API_HOST}:{settings.API_PORT} "
            f"| workers={workers} | debug={settings.DEBUG}"
        )
        uvicorn.run(
            "main:app",
            host=settings.API_HOST,
            port=settings.API_PORT,
            workers=1 if settings.DEBUG else workers,  # reload tidak kompatibel dgn workers>1
            reload=settings.DEBUG,
            log_level="debug" if settings.DEBUG else "info",
            access_log=settings.DEBUG,  # matikan access log di production untuk performa
        )
