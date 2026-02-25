# 📈 Saham Scalper Bot - IDX Screener + Telegram Notifier

Sistem screener saham Indonesia (IDX/BEI) berbasis FastAPI dengan strategi **scalping intraday** yang mengirim notifikasi sinyal ke bot Telegram.

---

## ✨ Fitur Utama

| Fitur            | Detail                                                             |
| ---------------- | ------------------------------------------------------------------ |
| 📊 Data Source   | Yahoo Finance (`yfinance`) — real-time intraday 5 menit            |
| 🎯 Strategi      | Scalping intraday target profit **2–3%**                           |
| 📐 Signal Detail | Entry Zone, TP1/TP2/TP3, Stop Loss, Risk:Reward                    |
| 🤖 Telegram Bot  | Notif otomatis ke grup/pribadi                                     |
| ⏱ Scheduler      | Auto-scan setiap 15 menit saat jam bursa                           |
| 🔬 Indikator     | RSI, MACD, Bollinger Bands, VWAP, ADX, ATR, Stochastic, SuperTrend |
| 🏭 Watchlist     | 35+ saham LQ45/IDX30 paling likuid                                 |
| ⚡ Performance   | Scan paralel (ThreadPoolExecutor)                                  |

---

## 📐 Detail Sinyal Scalping

Setiap sinyal berisi informasi lengkap:

```
🟢 SINYAL SCALP BUY
━━━━━━━━━━━━━━━━━━━━
🏷 BBCA | Bank Central Asia

📊 SKOR SINYAL: 78/100
💪 Kekuatan: STRONG

💰 HARGA ENTRY
🎯 Entry Point  : Rp 9.500
📍 Zone Entry   : Rp 9.481 - Rp 9.529

▲ TAKE PROFIT
✅ TP1 (+1.5%) : Rp 9.643
✅ TP2 (+2.5%) : Rp 9.738  ⭐ Target Utama
✅ TP3 (+3.5%) : Rp 9.833  🚀 Target Maksimal

🛑 STOP LOSS
❌ SL (-1.0%)  : Rp 9.405

⚖️ RISK : REWARD = 1 : 2.5
```

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
# Clone atau buat project
cd d:\api_saham

# Buat virtual environment
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 2. Konfigurasi .env

```bash
# Copy file contoh
copy .env.example .env
```

Edit `.env`:

```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHI...  # Dari @BotFather
TELEGRAM_CHAT_IDS=-100123456789,987654321    # ID grup/user
```

#### Cara Mendapatkan Chat ID:

1. Tambahkan `@userinfobot` ke Telegram
2. Untuk grup: Tambahkan bot ke grup, lalu kirim pesan, cek dengan `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Chat ID grup biasanya negatif: `-100xxxxxxxxxx`

### 3. Setup Telegram Bot

1. Buka Telegram, cari `@BotFather`
2. Kirim `/newbot`
3. Ikuti instruksi, copy TOKEN
4. Tambahkan bot ke grup Anda
5. Berikan izin **Send Messages** ke bot

### 4. Test

```bash
# Test komponen tanpa Telegram
python test_screener.py
```

### 5. Jalankan

```bash
# Mode API Server (dengan scheduler otomatis)
python main.py

# Mode Bot Polling (untuk development)
python main.py bot
```

---

## 📡 API Endpoints

Setelah server berjalan, buka: `http://localhost:8000/docs`

| Endpoint                         | Method | Deskripsi                |
| -------------------------------- | ------ | ------------------------ |
| `/`                              | GET    | Info API & status pasar  |
| `/market`                        | GET    | Status pasar BEI         |
| `/watchlist`                     | GET    | Daftar saham watchlist   |
| `/scan`                          | POST   | Jalankan scan screener   |
| `/signal/{ticker}`               | GET    | Sinyal untuk 1 saham     |
| `/signals/top`                   | GET    | Top N sinyal terakhir    |
| `/signals/summary`               | GET    | Ringkasan market         |
| `/telegram/test`                 | POST   | Test koneksi Telegram    |
| `/telegram/send-signal/{ticker}` | POST   | Kirim sinyal ke Telegram |
| `/scheduler/jobs`                | GET    | Info jadwal scan         |
| `/scheduler/trigger`             | POST   | Trigger scan manual      |

### Contoh Request

```bash
# Scan saham tertentu
curl http://localhost:8000/signal/BBCA

# Scan semua dengan filter BUY
curl -X POST http://localhost:8000/scan \
  -H "Content-Type: application/json" \
  -d '{"min_score": 60, "signal_filter": "BUY", "send_telegram": true}'
```

---

## 🤖 Telegram Bot Commands

| Command        | Fungsi                       |
| -------------- | ---------------------------- |
| `/start`       | Selamat datang               |
| `/scan`        | Scan semua saham (1-2 menit) |
| `/top`         | Top 5 sinyal terakhir        |
| `/signal BBCA` | Sinyal detail satu saham     |
| `/buy`         | Daftar sinyal BUY            |
| `/sell`        | Daftar sinyal SELL           |
| `/market`      | Status pasar + ringkasan     |
| `/help`        | Panduan lengkap              |

---

## ⏱ Jadwal Scan Otomatis

| Waktu WIB              | Aksi                 |
| ---------------------- | -------------------- |
| 09:00                  | Notif pasar BUKA     |
| 09:05                  | Scan pertama         |
| 09:20, 09:35, 09:50... | Scan setiap 15 menit |
| 11:20                  | Scan terakhir sesi 1 |
| 13:35, 13:50           | Scan sesi 2          |
| 14:45                  | Notif pre-close      |
| 15:05                  | Notif pasar TUTUP    |

---

## 🔬 Strategi & Indikator

### Signal Scoring (0-100 poin):

| Kriteria                      | Bobot   |
| ----------------------------- | ------- |
| Trend Alignment (EMA 9/20/50) | 25 poin |
| MACD Konfirmasi               | 20 poin |
| RSI Kondisi                   | 20 poin |
| Volume Ratio                  | 15 poin |
| ADX Trend Strength            | 10 poin |
| Candlestick Pattern           | 10 poin |

### Kekuatan Sinyal:

- **STRONG** (≥ 75): Sinyal sangat kuat
- **MODERATE** (55-74): Sinyal cukup kuat
- **WEAK** (45-54): Sinyal lemah, hati-hati

### Manajemen Posisi yang Disarankan:

1. **Entry** di zone entry yang ditentukan
2. Saat **TP1 (+1.5%)** tercapai → cut sebagian (30%), geser SL ke breakeven
3. Saat **TP2 (+2.5%)** tercapai → cut lagi (50%), biarkan sisanya
4. **TP3 (+3.5%)** → full exit atau trailing stop
5. **SL** adalah batas keras — DO NOT HOLD jika tertembus

---

## 📁 Struktur Project

```
api_saham/
├── main.py                     # FastAPI app + entry point
├── config.py                   # Konfigurasi dari .env
├── requirements.txt
├── .env.example                # Template konfigurasi
├── test_screener.py            # Script test
│
├── data/
│   ├── fetcher.py              # Yahoo Finance data fetcher
│   └── stock_list.py           # Daftar saham IDX (LQ45, IDX30)
│
├── screener/
│   ├── indicators.py           # RSI, MACD, BB, ATR, VWAP, ADX, dll
│   ├── signal_generator.py     # Kalkulasi Entry/TP/SL, scoring
│   └── scanner.py              # Runner scan paralel
│
├── telegram_bot/
│   ├── bot.py                  # Bot handler + notifier
│   ├── formatter.py            # Format pesan HTML Telegram
│   └── notifier_runner.py      # Helper async notifikasi
│
└── scheduler/
    └── job_scheduler.py        # APScheduler (cron jobs)
```

---

## ⚠️ Disclaimer

> Sistem ini adalah **alat bantu analisis teknikal** semata. Sinyal yang dihasilkan bukan merupakan rekomendasi investasi. Selalu lakukan riset mandiri (DYOR) sebelum mengambil keputusan trading. **Risiko trading ditanggung penuh oleh trader masing-masing.**

---

## 📌 Tips Scalping

- Gunakan saham dengan **volume tinggi** (BBCA, BBRI, BMRI, TLKM, ASII)
- Buka posisi hanya di **sesi aktif**: 09:15–11:00 dan 13:45–14:45
- Jangan buka posisi **5 menit pertama** (09:00–09:05) — terlalu volatile
- Perhatikan **VWAP**: beli di bawah VWAP (lebih aman), jual di atas VWAP
- Minimal **RR 1:2** — jangan ambil trade dengan risiko lebih besar dari reward
- **Volume ratio > 1.5x** = konfirmasi sinyal lebih kuat
