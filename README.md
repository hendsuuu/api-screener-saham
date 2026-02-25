# 📈 IDX Scalper Bot — Screener + Telegram Notifier

Sistem screener saham Indonesia (IDX/BEI) berbasis **FastAPI** dengan strategi **scalping intraday**.
Dilengkapi persistent OHLCV database (Parquet), crawling historis, structured error logging, dan CLI management tool siap deploy di VPS.

---

## ✨ Fitur Utama

| Fitur | Detail |
|---|---|
| 🗄️ Data Store | OHLCV tersimpan Parquet per-ticker — baca lokal tanpa live API |
| 🕷️ Data Crawler | Crawl historis 5 tahun + intraday 60 hari, update otomatis jam 04:00 |
| 🌐 Data Source | Yahoo Finance (`yfinance 1.2.0`) dengan Chrome impersonation |
| 🎯 Strategi | Scalping intraday, target profit **2–3%** per trade |
| 🟢 Sinyal BUY | Entry Zone, TP1/TP2/TP3, Stop Loss, Risk:Reward |
| 🔴 Sinyal WASPADA | Peringatan kondisi bearish (BEI tidak ada short-selling) |
| 🤖 Telegram Bot | Notifikasi otomatis + command interaktif + admin commands |
| ⏱️ Auto Scheduler | 04:00 update data — 06:00 kirim max **10 BUY + 10 WASPADA** |
| 📊 Indikator | EMA 9/20/50, RSI, MACD, Bollinger Bands, VWAP, ADX, ATR, SuperTrend |
| 🔍 Pre-Screener | Filter ~342 saham IDX berdasarkan volume, nilai & momentum harga |
| 🧠 /info Ticker | Analisis mendalam: trend, S/R zones, potensi, risiko, confidence score |
| 💾 Signal Cache | Sinyal tersimpan JSON per hari — `/buy` & `/waspada` aktif setelah restart |
| 🖥️ CLI Management | `manage.py` untuk kontrol VPS: start/stop/status/get-data/scan/store |
| 🔐 Admin Commands | Command pribadi via Telegram khusus pemilik bot |
| 📋 Error Logging | Structured JSON log per request gagal + API `/errors/recent` |

---

## 🔄 Alur Data (Data-First Flow)

```
┌──────────────────────────────────────────────────────────────────┐
│  [SEKALI / JARANG]                                               │
│  python manage.py get-data                                       │
│    -> Crawl ~342 saham: 5 tahun harian + 60 hari intraday 5m     │
│    -> Simpan ke data/store/{interval}/{TICKER}.parquet           │
└──────────────────────────────────────────────────────────────────┘
         ↓
┌──────────────────────────────────────────────────────────────────┐
│  [04:00 WIB, Senin–Jumat]  ← otomatis via scheduler              │
│    -> crawler.update_latest() semua interval (5m, 15m, 1h, 1d)   │
│    -> Upsert candle terbaru ke Parquet store                     │
└──────────────────────────────────────────────────────────────────┘
         ↓
┌──────────────────────────────────────────────────────────────────┐
│  [06:00 WIB, Senin–Jumat]  ← otomatis via scheduler              │
│    -> scanner.scan_all()  — baca dari Parquet (cepat, no API)    │
│    -> Kirim max 10 BUY + max 10 WASPADA ke Telegram              │
│       (confidence >= 60, harga Rp 100–10.000, liquid)            │
└──────────────────────────────────────────────────────────────────┘
         ↓
┌──────────────────────────────────────────────────────────────────┐
│  [ON-DEMAND]  /scan, /signal BBCA, /info BBCA, POST /scan        │
│    -> Baca dari store lokal (<= 20 menit fresh)                  │
│    -> Fallback ke live API jika data terlalu lama                │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Install

```bash
cd d:\api_saham
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
```

### 2. Konfigurasi `.env`

```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdef...
TELEGRAM_CHAT_IDS=-100123456789
ADMIN_CHAT_IDS=123456789          # Cari ID Anda di @userinfobot

API_SECRET_KEY=ganti-dengan-key-anda
MIN_SIGNAL_SCORE=60

DATA_STORE_PATH=data/store
CRAWL_HISTORICAL_PERIOD=5y        # Periode historis harian
CRAWL_INTRADAY_PERIOD=60d         # Periode intraday 5m (max 60d)
CRAWL_WORKERS=4
CRAWL_BATCH_SIZE=20
CRAWL_DELAY_SECONDS=0.5
```

### 3. Crawl Data Historis ⚠️ WAJIB sebelum pertama kali scan

```bash
# Full crawl: 5 tahun harian + 60 hari intraday (~342 saham, ~20–40 menit)
python manage.py get-data

# Bertahap
python manage.py get-data --interval 1d          # harian dulu
python manage.py get-data --interval 5m          # lanjut intraday

# Quick test dengan beberapa saham
python manage.py get-data --tickers BBCA,BBRI,TLKM,ASII,BMRI
```

### 4. Jalankan Server

```bash
python manage.py start   # API + Scheduler (fetch + scan + Telegram otomatis)
# atau langsung:
python main.py
```

---

## 🖥️ CLI (`manage.py`)

```bash
# ── Server ───────────────────────────────────────────────
python manage.py start [--port 8000]
python manage.py stop
python manage.py restart
python manage.py status          # Status + store stats
python manage.py logs [-n 50]    # Log terakhir

# ── Data Crawling ────────────────────────────────────
python manage.py get-data                            # Full crawl (5y harian + 60d intraday)
python manage.py get-data --period 2y                # Pilih periode harian
python manage.py get-data --interval 1d              # Hanya data harian
python manage.py get-data --interval 5m              # Hanya intraday 5m
python manage.py get-data --tickers BBCA,BBRI,TLKM   # Saham tertentu
python manage.py get-data --workers 8                # Lebih banyak thread
python manage.py get-data --update                   # Incremental (candle terbaru saja)

# ── Scan Manual (butuh server berjalan) ─────────────────
python manage.py scan
python manage.py prescreen

# ── Data Store ───────────────────────────────────────────
python manage.py store stats
python manage.py store list [--interval 5m]
python manage.py store trim [--days 365]
python manage.py store delete BBCA [--interval 5m]

# ── Bot Saja ─────────────────────────────────────────────
python manage.py bot
```

---

## 🌐 API Endpoints

Buka `http://localhost:8000/docs` setelah server berjalan.

### Screener

| Endpoint | Method | Deskripsi |
|---|---|---|
| `/scan` | POST | Jalankan scan screener |
| `/signal/{ticker}` | GET | Sinyal 1 saham |
| `/signals/top` | GET | Top N sinyal terbaru |
| `/signals/summary` | GET | Ringkasan market |
| `/scheduler/trigger` | POST | Trigger scan manual |
| `/prescreen/run` | POST | Jalankan pre-screener |
| `/prescreen/criteria` | PATCH | Hot-reload kriteria filter |

### Data Store & Crawling

| Endpoint | Method | Deskripsi |
|---|---|---|
| `/data/fetch` | POST | Trigger crawl historis (background) |
| `/data/update` | POST | Trigger incremental update (background) |
| `/data/status` | GET | Progress crawl + statistik store |

### Error Logging

| Endpoint | Method | Deskripsi |
|---|---|---|
| `/errors/recent` | GET | N error request terbaru |
| `/errors/stats` | GET | Breakdown error per ticker/operasi/jam |
| `/errors/clear` | DELETE | Reset buffer error in-memory |

---

## 💬 Perintah Telegram

### Publik

| Command | Fungsi |
|---|---|
| `/start` | Sambutan + ringkasan fitur |
| `/scan` | Scan IDX sekarang, kirim sinyal terbaik |
| `/top` | Top 5 sinyal (dari cache jika server baru restart) |
| `/signal BBCA` | Analisis teknikal + sinyal satu saham |
| `/info BBCA` | 🧠 Analisis mendalam: trend, S/R zones, potensi, risiko, confidence |
| `/buy` | Daftar sinyal BUY hari ini (max 10) |
| `/waspada` | Daftar saham kondisi bearish hari ini (max 10) |
| `/market` | Status pasar + ringkasan scan terakhir |

> 💡 Ketik kode saham langsung (contoh: `BBCA`) → bot otomatis analisis dengan `/signal`!

### Admin (`ADMIN_CHAT_IDS`)

| Command | Fungsi |
|---|---|
| `/admin status` | Status server + store + scan terakhir |
| `/admin scan` | Paksa scan, hasil dikirim langsung ke Anda |
| `/admin store` | Statistik data store |
| `/admin logs [30]` | N baris terakhir app.log |
| `/admin prescreen` | Jalankan pre-screener manual |

---

## 🏗️ Arsitektur Data

### OHLCV Store (Parquet)

```
data/store/
├── 5m/
│   ├── BBCA.parquet        # ~18.000 baris (60 hari × intraday 5m)
│   ├── BBRI.parquet
│   └── ...                 # ~342 saham IDX
├── 15m/
├── 1h/
├── 1d/
│   ├── BBCA.parquet        # ~1.250 baris harian (5 tahun)
│   └── ...
├── signals_2026-02-25.json  # Cache sinyal hari ini
└── signals_2026-02-24.json  # Riwayat 7 hari
```

**Logika akumulatif (upsert):**
```
Data lama  :  [1, 2, 3, 4, 5]
Data baru  :        [3, 4, 5, 6, 7]
Hasil disk :  [1, 2, 3, 4, 5, 6, 7]   — tidak ada yang dihapus, duplikat di-overwrite
```

### Estimasi Kapasitas

| Data | Ukuran per Saham | Total ~342 Saham |
|---|---|---|
| 5m · 60 hari | ~100 KB | ~34 MB |
| 5m · 730 hari | ~1.2 MB | ~420 MB |
| 1d · 5 tahun | ~15 KB | ~5 MB |

### Error Logging (Structured)

```
logs/
├── errors.jsonl    # Append-only JSON lines, rotate 10 MB, retain 7 hari
└── app.log         # Log aplikasi standar
```

Format tiap entry:
```json
{
  "time": "2026-02-25T09:23:47.123",
  "ticker": "BBCA",
  "operation": "yfinance.5m",
  "error_type": "TimeoutError",
  "message": "...",
  "retry": 2
}
```

---

## ⏰ Jadwal Scheduler

| Waktu (WIB) | Aksi |
|---|---|
| 04:00 | 🔄 **Update data store** — ambil candle terbaru semua interval (5m, 15m, 1h, 1d) |
| 06:00 | 📨 **Kirim sinyal pagi** — max 10 BUY + max 10 WASPADA (confidence >= 60) |
| 09:00 | 🔔 Notifikasi pasar **BUKA** |
| 15:45 | ⚠️ Notifikasi pre-close (15 menit sebelum tutup) |
| 16:00 | 🔕 Notifikasi pasar **TUTUP** |

> - Data di-fetch **sekali sehari jam 04:00** — tidak ada polusi API tiap 15 menit
> - Sinyal dikirim jam **06:00** sehingga trader punya waktu riset penuh sebelum pasar buka (09:00)

---

## 📊 Scoring Sinyal (0–100 poin)

| Kriteria | Bobot |
|---|---|
| Trend Alignment (EMA 9/20/50) | 25 pts |
| MACD Konfirmasi | 20 pts |
| RSI Kondisi | 20 pts |
| Volume Ratio | 15 pts |
| ADX Trend Strength | 10 pts |
| Candlestick Pattern | 10 pts |

**Kekuatan sinyal:** 🟢 STRONG (>= 75) · 🟡 MODERATE (55–74) · 🔴 WEAK (45–54)

**Jenis sinyal:**
- 🟢 **BUY** — kondisi bullish, dilengkapi Entry / TP1 / TP2 / TP3 / SL / Risk:Reward
- 🔴 **WASPADA** — kondisi bearish, **BUKAN short signal** (BEI melarang short selling)

---

## 📁 Struktur Project

```
api_saham/
├── main.py                    # FastAPI app + semua endpoints
├── manage.py                  # CLI management (start/stop/get-data/...)
├── config.py                  # Settings dari .env
├── requirements.txt
├── .env
│
├── data/
│   ├── fetcher.py             # Yahoo Finance + auto-save store + OHLCV normalize
│   ├── crawler.py             # Bulk crawl historis + incremental update
│   ├── store.py               # Parquet OHLCV database (upsert/load/stats/trim)
│   ├── signal_cache.py        # Signal JSON cache per hari
│   ├── stock_list.py          # IDX Universe (~342 saham)
│   ├── dynamic_screener.py    # Pre-screener batch harian
│   └── store/                 # Data Parquet (auto-created)
│
├── screener/
│   ├── scanner.py             # Scan store-first → fallback live API + /info analysis
│   ├── indicators.py          # EMA, RSI, MACD, BB, ATR, ADX, dll
│   └── signal_generator.py    # Kalkulasi sinyal BUY/WASPADA + scoring
│
├── telegram_bot/
│   ├── bot.py                 # Handler semua command Telegram
│   ├── formatter.py           # Format pesan HTML untuk Telegram
│   └── notifier_runner.py     # Pengiriman notifikasi async
│
├── scheduler/
│   └── job_scheduler.py       # 04:00 fetch + 06:00 scan + notif market
│
└── logs/
    ├── error_tracker.py       # Structured error logging (JSON ring buffer)
    ├── errors.jsonl           # File error log (auto-created)
    └── app.log                # Log aplikasi
```

---

## 📦 Dependency Utama

| Package | Versi | Fungsi |
|---|---|---|
| `yfinance` | 1.2.0 | Data saham Yahoo Finance (wajib versi 1.x) |
| `curl_cffi` | >= 0.7 | Chrome impersonation untuk bypass rate-limit YF |
| `fastapi` | 0.115.5 | REST API framework |
| `python-telegram-bot` | 21.7 | Telegram Bot SDK |
| `APScheduler` | 3.10.4 | Scheduler jam bursa (CronTrigger) |
| `pyarrow` | >= 14.0.0 | Engine Parquet — persistent OHLCV store |
| `pandas` | 2.2.3 | Data manipulation & analisis |
| `loguru` | 0.7.3 | Structured logging |
| `tqdm` | 4.66.0 | Progress bar saat crawling |

> ⚠️ **`yfinance` versi 0.2.x tidak kompatibel.** Gunakan versi **1.2.0**.
> Yahoo Finance 2024+ menggunakan autentikasi baru yang membutuhkan `curl_cffi`.

---

## ⚙️ Config Variables (`.env`)

```env
# ── Telegram ─────────────────────────────────────────
TELEGRAM_BOT_TOKEN=           # Token dari @BotFather
TELEGRAM_CHAT_IDS=            # ID grup/channel tujuan notif
ADMIN_CHAT_IDS=               # ID pribadi untuk admin commands

# ── API ─────────────────────────────────────────────
API_PORT=8000
API_SECRET_KEY=changeme-secret-key
DEBUG=false

# ── Screener ──────────────────────────────────────
MIN_SIGNAL_SCORE=60
MAX_SCAN_WORKERS=8
MIN_VOLUME_RATIO=1.2

# ── Limit Sinyal Harian ───────────────────────────
MAX_BUY_SIGNALS=10            # Maksimal sinyal BUY per hari (dikirim jam 06:00)
MAX_WASPADA_SIGNALS=10        # Maksimal sinyal WASPADA per hari

# ── Pre-Screener (profit-first, IDX sweet-spot) ───────────
PRESCREEN_MIN_PRICE=100           # Rp 100 minimum
PRESCREEN_MAX_PRICE=10000         # Rp 10.000 maksimum
PRESCREEN_MIN_VOLUME_MA5=3000000  # 3 juta lembar/hari (liquid)
PRESCREEN_MIN_VALUE_MA5=5000000000  # Rp 5 miliar/hari
PRESCREEN_MIN_PRICE_CHANGE_PCT=0.5  # 0.5% — tangkap pre-breakout
PRESCREEN_MIN_VOL_SURGE_PCT=15.0    # Volume surge 15% — smart money signal

# ── Data Store ──────────────────────────────────────
DATA_STORE_PATH=data/store
DATA_STORE_MAX_DAYS=365

# ── Crawler (historis & incremental) ────────────────
CRAWL_HISTORICAL_PERIOD=5y    # Periode data harian (1y / 2y / 5y)
CRAWL_INTRADAY_PERIOD=60d     # Periode intraday 5m (max 60d)
CRAWL_WORKERS=4               # Thread paralel
CRAWL_BATCH_SIZE=20           # Saham per batch yf.download
CRAWL_DELAY_SECONDS=0.5       # Jeda antar batch (detik)
```

---

## ⚠️ Disclaimer

Sistem ini adalah **alat bantu analisis teknikal** semata, bukan rekomendasi investasi.
Selalu lakukan riset mandiri (DYOR). **Risiko trading ditanggung penuh oleh trader.**
