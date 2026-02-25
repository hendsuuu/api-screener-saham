#  IDX Scalper Bot  Screener + Telegram Notifier

Sistem screener saham Indonesia (IDX/BEI) berbasis **FastAPI** dengan strategi **scalping intraday**. Dilengkapi persistent OHLCV database (Parquet), crawling historis, structured error logging, dan CLI management tool untuk VPS.

---

##  Fitur Utama

| Fitur | Detail |
|---|---|
|  Data Store | OHLCV tersimpan Parquet per-ticker  baca lokal tanpa live API |
|  Data Crawler | Crawl historis 5 tahun + intraday 60 hari, update 15 menit |
|  Data Source | Yahoo Finance (`yfinance 1.2.0`) dengan Chrome impersonation |
|  Strategi | Scalping intraday target profit **23%** |
|  Sinyal BUY | Entry Zone, TP1/TP2/TP3, Stop Loss, Risk:Reward |
|  Sinyal WASPADA | Peringatan kondisi bearish (BEI tidak ada short-selling) |
|  Telegram Bot | Notifikasi + command interaktif + admin commands |
|  Auto Fetch+Scan | Setiap 15 menit: update store  scan dari store (cepat) |
|  Indikator | RSI, MACD, Bollinger Bands, VWAP, ADX, ATR, Stochastic, SuperTrend |
|  Dynamic Pre-Screen | Filter ~342 saham IDX berdasarkan volume & momentum |
|  Signal Cache | Sinyal tersimpan JSON per hari  /buy & /waspada aktif setelah restart |
|  CLI Management | `manage.py` untuk kontrol VPS: start/stop/status/get-data/scan/store |
|  Admin Commands | Command pribadi via Telegram untuk pemilik bot |
|  Error Logging | Structured JSON log per request gagal + API `/errors/recent` |

---

##  Alur Data (Data-First Flow)

```

  [SEKALI / JARANG]                                               
  python manage.py get-data                                       
     Crawl ~342 saham: 5 tahun harian + 60 hari intraday 5m     
     Simpan ke data/store/{interval}/{TICKER}.parquet            

         

  [OTOMATIS, setiap 15 menit saat jam bursa]                     
  1. crawler.update_latest()  ambil candle terbaru  upsert     
  2. scanner.scan_all()       baca dari Parquet (cepat!)        
  3. TelegramNotifier         kirim sinyal terbaik ke grup       

         

  [ON-DEMAND]  /scan, /signal BBCA, POST /scan                   
     Baca dari store lokal (20 menit fresh)                    
     Fallback ke live API jika data terlalu lama                 

```

---

##  Quick Start

### 1. Install

```bash
cd d:\api_saham
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac
pip install -r requirements.txt
```

### 2. Konfigurasi `.env`

```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdef...
TELEGRAM_CHAT_IDS=-100123456789

# Admin bot
ADMIN_CHAT_IDS=123456789         # Cari ID Anda di @userinfobot

API_SECRET_KEY=ganti-dengan-key-anda
MIN_SIGNAL_SCORE=60

# Data Store & Crawler
DATA_STORE_PATH=data/store
CRAWL_HISTORICAL_PERIOD=5y       # Periode historis harian
CRAWL_INTRADAY_PERIOD=60d        # Periode intraday 5m (max 60d untuk yfinance)
CRAWL_WORKERS=4                  # Thread paralel crawling
CRAWL_BATCH_SIZE=20              # Saham per batch download
CRAWL_DELAY_SECONDS=0.5          # Jeda antar batch (rate-limit guard)
```

### 3. Crawl Data Historis (WAJIB sebelum pertama kali scan)

```bash
# Full crawl: 5 tahun harian + 60 hari intraday (~342 saham IDX, ~20-40 menit)
python manage.py get-data

# Atau bertahap
python manage.py get-data --interval 1d          # hanya harian dulu
python manage.py get-data --interval 5m          # lanjut intraday

# Test dengan beberapa saham dulu
python manage.py get-data --tickers BBCA,BBRI,TLKM,ASII,BMRI
```

### 4. Jalankan Server

```bash
# API Server + Scheduler (fetch data + scan + Telegram otomatis)
python manage.py start
# Atau langsung:
python main.py
```

---

##  CLI (`manage.py`)

```bash
#  Server 
python manage.py start [--port 8000]
python manage.py stop
python manage.py restart
python manage.py status          # Status + store stats
python manage.py logs [-n 50]    # Log terakhir

#  Data Crawling 
python manage.py get-data                            # Full crawl (5y harian + 60d intraday)
python manage.py get-data --period 2y                # Pilih periode harian
python manage.py get-data --interval 1d              # Hanya data harian
python manage.py get-data --interval 5m              # Hanya intraday 5m
python manage.py get-data --tickers BBCA,BBRI,TLKM   # Saham tertentu
python manage.py get-data --workers 8                # Lebih banyak thread
python manage.py get-data --update                   # Incremental (candle terbaru saja)

#  Scan Manual (butuh server berjalan) 
python manage.py scan
python manage.py prescreen

#  Data Store 
python manage.py store stats
python manage.py store list [--interval 5m]
python manage.py store trim [--days 365]
python manage.py store delete BBCA [--interval 5m]

#  Bot Saja 
python manage.py bot
```

---

##  API Endpoints

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

##  Perintah Telegram

### Publik

| Command | Fungsi |
|---|---|
| `/start` | Sambutan |
| `/scan` | Scan IDX, kirim sinyal terbaik |
| `/top` | Top 5 sinyal (dari cache jika server baru restart) |
| `/signal BBCA` | Analisis satu saham |
| `/buy` | Daftar sinyal BUY hari ini |
| `/waspada` | Daftar saham kondisi bearish hari ini |
| `/market` | Status pasar + ringkasan scan |

> Ketik kode saham langsung (contoh: `BBCA`)  bot langsung analisis!

### Admin (`ADMIN_CHAT_IDS`)

| Command | Fungsi |
|---|---|
| `/admin status` | Status server + store + scan terakhir |
| `/admin scan` | Paksa scan, hasilnya dikirim ke Anda |
| `/admin store` | Statistik data store |
| `/admin logs [30]` | N baris terakhir app.log |
| `/admin prescreen` | Jalankan pre-screener |

---

##  Arsitektur Data

### OHLCV Store (Parquet)

```
data/store/
 5m/
    BBCA.parquet        # ~18.000 baris 5 menit (60 hari)
    BBRI.parquet
    ...                 # ~342 saham IDX
 1d/
    BBCA.parquet        # ~1.250 baris harian (5 tahun)
    ...
 signals_2026-02-25.json  # Cache sinyal hari ini
 signals_2026-02-24.json  # Riwayat 7 hari
```

**Logika akumulatif (upsert):**
```
Data lama : [1, 2, 3, 4, 5]
Data baru  :       [3, 4, 5, 6, 7]
Hasil disk : [1, 2, 3, 4, 5, 6, 7]   tidak ada yang dihapus, duplikat di-overwrite
```

### Estimasi Kapasitas

| Data | Ukuran per Saham | Total 342 Saham |
|---|---|---|
| 5m  60 hari | ~100 KB | ~34 MB |
| 5m  730 hari | ~1.2 MB | ~420 MB |
| 1d  5 tahun | ~15 KB | ~5 MB |

### Error Logging (Structured)

```
logs/
 errors.jsonl    # Append-only JSON lines, rotate 10 MB, retain 7 hari
 app.log         # Log aplikasi standar
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

##  Jadwal Scheduler

| Waktu (WIB) | Aksi |
|---|---|
| 09:00 | Notif pasar BUKA |
| 09:0511:20 | **Fetch data** + Scan tiap 15 menit (Sesi 1) |
| 13:3514:50 | **Fetch data** + Scan tiap 15 menit (Sesi 2) |
| 14:45 | Notif pre-close |
| 15:05 | Notif pasar TUTUP |

> Setiap job 15 menit: pertama update Parquet store (candle terbaru), baru scan dari data lokal. Scan **tidak membuat API call live** selama data store masih  20 menit.

---

##  Scoring Sinyal (0100 poin)

| Kriteria | Bobot |
|---|---|
| Trend Alignment (EMA 9/20/50) | 25 pts |
| MACD Konfirmasi | 20 pts |
| RSI Kondisi | 20 pts |
| Volume Ratio | 15 pts |
| ADX Trend Strength | 10 pts |
| Candlestick Pattern | 10 pts |

**Kekuatan:** STRONG (75) | MODERATE (5574) | WEAK (4554)

**Jenis sinyal:**
-  **BUY**  kondisi bullish, dilengkapi Entry/TP/SL/RR
-  **WASPADA**  kondisi bearish, **BUKAN short signal** (BEI larang short selling)

---

##  Struktur Project

```
api_saham/
 main.py                   # FastAPI app + semua endpoints
 manage.py                 # CLI management (start/stop/get-data/...)
 config.py                 # Settings dari .env (incl. CRAWL_* vars)
 requirements.txt
 .env

 data/
    fetcher.py            # Yahoo Finance + auto-save store + OHLCV normalize
    crawler.py            #  Bulk crawl historis + incremental update
    store.py              # Parquet OHLCV database (upsert/load/stats/trim)
    signal_cache.py       # Signal JSON cache per hari
    stock_list.py         # IDX Universe (~342 saham)
    dynamic_screener.py   # Pre-screener batch harian
    store/                # Data Parquet (auto-created)

 screener/
    scanner.py            # Scan store-first  fallback live API
    indicators.py
    signal_generator.py

 telegram_bot/
    bot.py
    formatter.py
    notifier_runner.py

 scheduler/
    job_scheduler.py      # Fetch data + scan setiap 15 menit

 logs/
     __init__.py
     error_tracker.py      #  Structured error logging (JSON ring buffer)
     errors.jsonl          # File error log (auto-created)
     app.log               # Log aplikasi
```

---

##  Dependency Utama

| Package | Versi | Fungsi |
|---|---|---|
| `yfinance` | 1.2.0 | Data saham Yahoo Finance (wajib 1.x untuk auth baru) |
| `curl_cffi` | 0.7 | Chrome impersonation untuk bypass rate-limit YF |
| `fastapi` | 0.115.5 | REST API |
| `python-telegram-bot` | 21.7 | Telegram Bot |
| `APScheduler` | 3.10.4 | Scheduler jam bursa |
| `pyarrow` | 14.0.0 | Engine Parquet (persistent OHLCV store) |
| `loguru` | 0.7.3 | Structured logging |
| `tqdm` | 4.66.0 | Progress bar crawling |
| `pandas` | 2.2.3 | Data manipulation |

>  **yfinance 0.2.x tidak kompatibel** dengan alur baru. Pastikan menggunakan versi 1.2.0.
> Yahoo Finance 2024+ menggunakan autentikasi baru yang membutuhkan `curl_cffi`.

---

##  Config Variables (`.env`)

```env
# Telegram
TELEGRAM_BOT_TOKEN=           # Token dari @BotFather
TELEGRAM_CHAT_IDS=            # ID grup/channel tujuan notif
ADMIN_CHAT_IDS=               # ID pribadi untuk admin commands

# API
API_PORT=8000
API_SECRET_KEY=changeme-secret-key
DEBUG=false

# Screener
MIN_SIGNAL_SCORE=60
MAX_SCAN_WORKERS=8
MIN_VOLUME_RATIO=1.2

# Pre-screener
PRESCREEN_MIN_PRICE=100
PRESCREEN_MIN_VOLUME_MA5=10000000
PRESCREEN_MIN_VALUE_MA5=10000000000
PRESCREEN_MIN_PRICE_CHANGE_PCT=2.0
PRESCREEN_MIN_VOL_SURGE_PCT=30.0

# Data Store
DATA_STORE_PATH=data/store
DATA_STORE_MAX_DAYS=365

# Crawler (historis & incremental)
CRAWL_HISTORICAL_PERIOD=5y    # Periode data harian (1y / 2y / 5y)
CRAWL_INTRADAY_PERIOD=60d     # Periode intraday 5m (max 60d)
CRAWL_WORKERS=4               # Thread paralel
CRAWL_BATCH_SIZE=20           # Saham per batch yf.download
CRAWL_DELAY_SECONDS=0.5       # Jeda antar batch (detik)
```

---

##  Disclaimer

Sistem ini adalah **alat bantu analisis teknikal** semata, bukan rekomendasi investasi. Selalu lakukan riset mandiri (DYOR). **Risiko trading ditanggung penuh oleh trader.**
