#  IDX Scalper Bot  Screener + Telegram Notifier

Sistem screener saham Indonesia (IDX/BEI) berbasis **FastAPI** dengan strategi **scalping intraday** yang mengirim notifikasi sinyal ke Telegram. Didukung persistent OHLCV database dan CLI management tool untuk VPS.

---

##  Fitur Utama

| Fitur                  | Detail                                                               |
|------------------------|----------------------------------------------------------------------|
|  Data Source         | Yahoo Finance (`yfinance`)  real-time intraday 5 menit             |
|  Strategi            | Scalping intraday target profit **23%**                            |
|  Sinyal BUY          | Entry Zone, TP1/TP2/TP3, Stop Loss, Risk:Reward                     |
|  Sinyal WASPADA      | Peringatan kondisi bearish (BEI tidak ada short-selling)            |
|  Telegram Bot        | Notifikasi otomatis ke grup/channel + command interaktif            |
|  Auto Scan            | Setiap 15 menit saat jam bursa BEI                                  |
|  Indikator           | RSI, MACD, Bollinger Bands, VWAP, ADX, ATR, Stochastic, SuperTrend |
|  Dynamic Pre-Screen  | Filter ~342 saham IDX berdasarkan volume & momentum                 |
|  Persistent Store    | Data OHLCV tersimpan Parquet, tumbuh akumulatif tiap scan           |
|  Signal Cache        | Sinyal tersimpan JSON per hari  /buy & /waspada tetap aktif setelah restart |
|  CLI Management      | `manage.py` untuk kontrol VPS: start/stop/status/scan/store         |
|  Admin Commands      | Command pribadi via Telegram untuk pemilik bot                      |

---

##  Contoh Sinyal BUY

```
 SINYAL SCALP BUY

 BBCA | Bank Central Asia

 SKOR SINYAL: 78/100 |  STRONG

 HARGA ENTRY
 Entry Point  : Rp 9.500
 Zone Entry   : Rp 9.481 - Rp 9.529

 TAKE PROFIT
 TP1 (+1.5%) : Rp 9.643
 TP2 (+2.5%) : Rp 9.738   Target Utama
 TP3 (+3.5%) : Rp 9.833   Target Maksimal

 STOP LOSS  : Rp 9.405 (-1.0%)
 RISK : REWARD = 1 : 2.5
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

# Admin bot (untuk perintah /admin)
ADMIN_CHAT_IDS=123456789         # Cari ID Anda di @userinfobot

API_SECRET_KEY=ganti-dengan-key-anda
MIN_SIGNAL_SCORE=60
DATA_STORE_PATH=data/store
```

### 3. Jalankan

```bash
# API Server + Scheduler + Auto Notif
python main.py

# Atau via CLI (direkomendasikan untuk VPS):
python manage.py start
```

---

##  CLI (`manage.py`)

```bash
# Server
python manage.py start [--port 8000]
python manage.py stop
python manage.py restart
python manage.py status          # Status + store stats
python manage.py logs [-n 50]    # Log terakhir

# Scan
python manage.py scan            # Paksa scan via API
python manage.py prescreen       # Jalankan pre-screener

# Data Store
python manage.py store stats
python manage.py store list [--interval 5m]
python manage.py store trim [--days 365]
python manage.py store delete BBCA [--interval 5m]

# Bot saja (tanpa API server)
python manage.py bot
```

---

##  API Endpoints

Buka `http://localhost:8000/docs` setelah server berjalan.

| Endpoint               | Method | Deskripsi                  |
|------------------------|--------|----------------------------|
| `/`                    | GET    | Info + status pasar        |
| `/market`              | GET    | Status bursa BEI           |
| `/scan`                | POST   | Jalankan scan              |
| `/signal/{ticker}`     | GET    | Sinyal 1 saham             |
| `/signals/top`         | GET    | Top N sinyal               |
| `/signals/summary`     | GET    | Ringkasan market           |
| `/scheduler/trigger`   | POST   | Trigger scan manual        |
| `/prescreen/run`       | POST   | Jalankan pre-screener      |
| `/prescreen/criteria`  | PATCH  | Hot-reload kriteria filter |

---

##  Perintah Telegram

### Publik

| Command          | Fungsi                                                        |
|------------------|---------------------------------------------------------------|
| `/start`         | Sambutan                                                     |
| `/scan`          | Scan ~342 saham IDX, kirim sinyal terbaik                    |
| `/top`           | Top 5 sinyal (dari cache jika server baru restart)           |
| `/signal BBCA`   | Analisis satu saham                                          |
| `/buy`           | Daftar sinyal BUY hari ini                                   |
| `/waspada`       | Daftar saham kondisi bearish hari ini                        |
| `/market`        | Status pasar + ringkasan scan                                |

> Ketik kode saham langsung (contoh: `BBCA`)  bot langsung analisis!

### Admin (`ADMIN_CHAT_IDS`)

| Command             | Fungsi                                   |
|---------------------|------------------------------------------|
| `/admin status`     | Status server + store + scan terakhir    |
| `/admin scan`       | Paksa scan, hasilnya dikirim ke Anda     |
| `/admin store`      | Statistik data store                     |
| `/admin logs [30]`  | N baris terakhir app.log                 |
| `/admin prescreen`  | Jalankan pre-screener                    |

---

##  Data Architecture

### OHLCV Store (Parquet)

```
data/store/
 5m/   BBCA.parquet  BBRI.parquet  ...     auto-append tiap scan
 1d/   BBCA.parquet  BBRI.parquet  ...     data harian
 signals_2025-02-25.json    sinyal hari ini (expire esok)
 signals_2025-02-24.json    riwayat 7 hari
```

**Logika akumulatif:**
```
Data lama : [1, 2, 3, 4, 5]
Data baru  :       [3, 4, 5, 6, 7]
Hasil disk : [1, 2, 3, 4, 5, 6, 7]    tidak ada yang dihapus
```

### Signal Cache (JSON)

- Setiap scan menyimpan sinyal ke `signals_YYYY-MM-DD.json`
- `/buy` dan `/waspada` tetap tampil meski server restart
- Expire otomatis tengah malam WIB
- Riwayat 7 hari terakhir disimpan

---

##  Jadwal Scan Otomatis

| Waktu (WIB)  | Aksi                            |
|--------------|---------------------------------|
| 09:00        | Notif pasar BUKA                |
| 09:0511:20  | Scan tiap 15 menit (Sesi 1)     |
| 13:3514:50  | Scan tiap 15 menit (Sesi 2)     |
| 14:45        | Notif pre-close                 |
| 15:05        | Notif pasar TUTUP               |

---

##  Scoring Sinyal (0100 poin)

| Kriteria                      | Bobot  |
|-------------------------------|--------|
| Trend Alignment (EMA 9/20/50) | 25 pts |
| MACD Konfirmasi               | 20 pts |
| RSI Kondisi                   | 20 pts |
| Volume Ratio                  | 15 pts |
| ADX Trend Strength            | 10 pts |
| Candlestick Pattern           | 10 pts |

**Kekuatan:** STRONG (75) | MODERATE (5574) | WEAK (4554)

**Jenis sinyal:**
-  **BUY**  kondisi bullish, dilengkapi Entry/TP/SL/RR
-  **WASPADA**  kondisi bearish, **BUKAN short signal** (BEI larang short selling)

---

##  Struktur Project

```
api_saham/
 main.py                  # FastAPI app
 manage.py                # CLI VPS management
 config.py                # Settings dari .env
 requirements.txt
 .env
 data/
    fetcher.py           # Yahoo Finance + auto-save store
    stock_list.py        # IDX Universe (~342 saham)
    dynamic_screener.py  # Pre-screener batch
    store.py             # Parquet OHLCV database
    signal_cache.py      # Signal JSON cache (per hari)
    store/               # Data files (auto-created)
 screener/
    indicators.py
    signal_generator.py
    scanner.py           # Dua-tahap scan + cache-aware
 telegram_bot/
    bot.py               # Handler + admin commands
    formatter.py
    notifier_runner.py
 scheduler/
    job_scheduler.py     # APScheduler BEI
 logs/
     app.log
```

---

##  Disclaimer

Sistem ini adalah **alat bantu analisis teknikal** semata, bukan rekomendasi investasi. Selalu lakukan riset mandiri (DYOR). **Risiko trading ditanggung penuh oleh trader.**
