"""
manage.py — CLI untuk kontrol server IDX Scalper Bot dari terminal / VPS.

Cara pakai:
    python manage.py start                  # Jalankan API server (port 8000)
    python manage.py start --port 9000      # Custom port
    python manage.py stop                   # Hentikan server
    python manage.py status                 # Status server + statistik store
    python manage.py restart                # Restart server

    python manage.py scan                   # Paksa scan sekarang (via API)
    python manage.py prescreen              # Jalankan pre-screener (via API)

    python manage.py store stats            # Statistik data store
    python manage.py store list             # Daftar ticker tersimpan
    python manage.py store list --interval 5m
    python manage.py store trim --days 365  # Hapus data > N hari
    python manage.py store delete BBCA      # Hapus satu ticker
    python manage.py store delete BBCA --interval 5m

    python manage.py bot                    # Jalankan hanya bot polling (tanpa API)

Catatan:
    - Perintah 'start', 'stop', 'restart', 'status' menggunakan PID file (.pid).
    - 'scan' dan 'prescreen' membutuhkan server sudah berjalan.
    - Jalankan di direktori root project (sama dengan main.py).
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# ── Pastikan root project ada di sys.path ──────────────────────────────────────
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Konstanta ─────────────────────────────────────────────────────────────────
PID_FILE = ROOT / ".server.pid"
LOG_FILE = ROOT / "logs" / "app.log"


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _python() -> str:
    """Kembalikan path Python interpreter yang sedang dipakai."""
    return sys.executable


def _read_pid() -> int | None:
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except ValueError:
            pass
    return None


def _write_pid(pid: int):
    PID_FILE.write_text(str(pid))


def _clear_pid():
    if PID_FILE.exists():
        PID_FILE.unlink()


def _is_running(pid: int) -> bool:
    """Cek apakah proses dengan PID tersebut masih hidup."""
    try:
        if os.name == "nt":  # Windows
            import ctypes
            PROCESS_QUERY_INFORMATION = 0x0400
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_INFORMATION, False, pid)
            if handle == 0:
                return False
            import ctypes.wintypes
            exit_code = ctypes.wintypes.DWORD()
            ctypes.windll.kernel32.GetExitCodeProcess(
                handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return exit_code.value == 259  # STILL_ACTIVE
        else:
            os.kill(pid, 0)
            return True
    except (PermissionError, ProcessLookupError, OSError):
        return False


def _stop_pid(pid: int, timeout: int = 10) -> bool:
    """Kirim SIGTERM / kill ke proses, tunggu sampai mati."""
    try:
        if os.name == "nt":
            subprocess.call(
                ["taskkill", "/F", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.kill(pid, signal.SIGTERM)
            for _ in range(timeout * 2):
                time.sleep(0.5)
                if not _is_running(pid):
                    return True
            os.kill(pid, signal.SIGKILL)
        return True
    except Exception as e:
        print(f"  [!] Error stop PID {pid}: {e}")
        return False


def _api_call(path: str, method: str = "GET", payload: dict | None = None):
    """Helper sederhana untuk memanggil API lokal."""
    try:
        import requests
        from config import settings
        base = f"http://127.0.0.1:{settings.API_PORT}"
        headers = {"X-API-Key": settings.API_SECRET_KEY}
        url = f"{base}{path}"
        if method.upper() == "POST":
            r = requests.post(url, json=payload or {}, headers=headers, timeout=30)
        elif method.upper() == "GET":
            r = requests.get(url, headers=headers, timeout=30)
        else:
            r = requests.request(method, url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()
    except ImportError:
        print("  [!] Package 'requests' belum terinstall. Jalankan: pip install requests")
        return None
    except Exception as e:
        print(f"  [!] API call gagal ({path}): {e}")
        return None


def _print_store_stats(stats: dict):
    print()
    print("  ╔═══════════════════════════════════════╗")
    print("  ║        DATA STORE STATISTICS          ║")
    print("  ╠═══════════════════════════════════════╣")
    print(f"  ║  Path    : {stats.get('store_path','N/A')[:30]}")
    print(f"  ║  Tickers : {stats.get('total_tickers', 0):>6}")
    print(f"  ║  Baris   : {stats.get('total_rows', 0):>6,}")
    print(f"  ║  Disk    : {stats.get('disk_mb', 0):>6.1f} MB")
    print(f"  ║  Oldest  : {stats.get('oldest','N/A')}")
    print(f"  ║  Newest  : {stats.get('newest','N/A')}")
    print("  ╠═══════════════════════════════════════╣")
    for iv, info in stats.get("intervals", {}).items():
        print(
            f"  ║  [{iv:>3}]  {info['tickers']:>4} tickers "
            f"{info['rows']:>8,} rows  {info['mb']:>6.1f} MB"
        )
    print("  ╚═══════════════════════════════════════╝")


# ─────────────────────────────────────────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────────────────────────────────────────


def cmd_start(args):
    """Jalankan uvicorn server di background."""
    pid = _read_pid()
    if pid and _is_running(pid):
        print(f"  [!] Server sudah berjalan (PID {pid}). Gunakan 'manage.py restart' jika ingin restart.")
        return

    from config import settings
    port = args.port if hasattr(args, "port") and args.port else settings.API_PORT
    host = settings.API_HOST

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        _python(), "-m", "uvicorn",
        "main:app",
        "--host", host,
        "--port", str(port),
        "--log-level", "info",
    ]

    print(f"  [*] Menjalankan server pada {host}:{port} ...")
    with open(LOG_FILE, "a") as log:
        proc = subprocess.Popen(
            cmd, cwd=str(ROOT),
            stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
    _write_pid(proc.pid)
    time.sleep(2)
    if _is_running(proc.pid):
        print(f"  [✓] Server berjalan. PID={proc.pid}, port={port}")
        print(f"  [i] Log: {LOG_FILE}")
    else:
        print("  [!] Server gagal dijalankan. Cek log untuk detail.")
        _clear_pid()


def cmd_stop(args):
    """Hentikan server."""
    pid = _read_pid()
    if not pid:
        print("  [!] Tidak ada PID tersimpan. Server mungkin tidak sedang berjalan.")
        return
    if not _is_running(pid):
        print(f"  [!] Proses PID {pid} sudah tidak berjalan. Membersihkan PID file.")
        _clear_pid()
        return
    print(f"  [*] Menghentikan server PID {pid} ...")
    _stop_pid(pid)
    _clear_pid()
    print("  [✓] Server dihentikan.")


def cmd_restart(args):
    """Restart server."""
    cmd_stop(args)
    time.sleep(1)
    cmd_start(args)


def cmd_status(args):
    """Tampilkan status server dan statistik store."""
    pid = _read_pid()
    print()
    print("  ╔═══════════════════════════════════════╗")
    print("  ║         IDX SCALPER STATUS            ║")
    print("  ╠═══════════════════════════════════════╣")

    if pid and _is_running(pid):
        print(f"  ║  Server  : 🟢 RUNNING  (PID: {pid})")
    else:
        print("  ║  Server  : 🔴 STOPPED")
        if pid:
            print(f"  ║           PID {pid} tidak aktif — membersihkan PID file")
            _clear_pid()

    # Coba koneksi ke API
    data = _api_call("/market")
    if data:
        print(f"  ║  API     : ✓ Responsif")
        print(f"  ║  Pasar   : {data.get('status', 'N/A')}")
        print(f"  ║  Waktu   : {data.get('time_wib', data.get('waktu', 'N/A'))}")
    else:
        print("  ║  API     : ✗ Tidak dapat terhubung")

    print("  ╚═══════════════════════════════════════╝")

    # Tampilkan statistik store
    try:
        from data.store import get_store
        stats = get_store().stats()
        _print_store_stats(stats)
    except Exception as e:
        print(f"  [!] Gagal baca store stats: {e}")


def cmd_scan(args):
    """Paksa scan sekarang via API."""
    print("  [*] Memulai scan melalui API ...")
    result = _api_call("/scheduler/trigger", method="POST")
    if result:
        print(f"  [✓] Scan dimulai: {result}")
    else:
        print("  [!] Gagal trigger scan. Pastikan server berjalan.")


def cmd_prescreen(args):
    """Jalankan pre-screener via API."""
    print("  [*] Menjalankan pre-screener ...")
    result = _api_call("/prescreen/run", method="POST")
    if result:
        print(f"  [✓] Pre-screener selesai:")
        print(json.dumps(result, indent=4, ensure_ascii=False))
    else:
        print("  [!] Gagal. Pastikan server berjalan.")


def cmd_store(args):
    """Manajemen persistent data store."""
    from data.store import DataStore
    from config import settings

    store = DataStore(settings.DATA_STORE_PATH)

    subcmd = args.subcmd

    if subcmd == "stats":
        stats = store.stats()
        _print_store_stats(stats)

    elif subcmd == "list":
        interval = getattr(args, "interval", "5m") or "5m"
        tickers = store.list_tickers(interval)
        if not tickers:
            print(f"  [i] Tidak ada data untuk interval {interval}")
            return
        print(f"\n  [{interval}] Tickers tersimpan ({len(tickers)}):")
        # Tampilkan 10 per baris
        for i in range(0, len(tickers), 10):
            print("    " + "  ".join(tickers[i:i+10]))

    elif subcmd == "trim":
        keep_days = getattr(args, "days", None) or settings.DATA_STORE_MAX_DAYS
        print(f"  [*] Trim data lebih lama dari {keep_days} hari ...")
        total_removed = 0
        from data.store import DataStore
        for iv in store.SUPPORTED_INTERVALS:
            for ticker in store.list_tickers(iv):
                removed = store.trim(ticker, iv, keep_days=keep_days)
                total_removed += removed
        print(f"  [✓] Total {total_removed} baris dihapus.")

    elif subcmd == "delete":
        ticker = getattr(args, "ticker", None)
        if not ticker:
            print("  [!] Harap sertakan kode saham. Contoh: manage.py store delete BBCA")
            return
        iv = getattr(args, "interval", None)
        deleted = store.delete_ticker(ticker, interval=iv)
        if deleted:
            print(f"  [✓] Data {ticker} (interval={iv or 'semua'}) dihapus ({deleted} file).")
        else:
            print(f"  [i] Tidak ada data ditemukan untuk {ticker}.")

    else:
        print(f"  [!] Sub-perintah tidak dikenal: {subcmd}")
        print("  Pilihan: stats | list | trim | delete")


def cmd_bot(args):
    """Jalankan hanya bot polling (tanpa API server)."""
    print("  [*] Menjalankan bot dalam mode polling ...")
    try:
        from config import settings
        from telegram_bot.bot import TelegramBotHandler
        from screener.scanner import StockScanner
        handler = TelegramBotHandler(
            token=settings.TELEGRAM_BOT_TOKEN,
            chat_ids=settings.TELEGRAM_CHAT_IDS,
            scanner=StockScanner(),
        )
        print("  [✓] Bot aktif. Tekan Ctrl+C untuk berhenti.")
        handler.run_polling()
    except KeyboardInterrupt:
        print("\n  [i] Bot dihentikan.")
    except Exception as e:
        print(f"  [!] Error: {e}")


def cmd_logs(args):
    """Tampilkan N baris terakhir dari log file."""
    n = getattr(args, "lines", 50) or 50
    if not LOG_FILE.exists():
        print(f"  [!] File log tidak ditemukan: {LOG_FILE}")
        return
    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    tail = lines[-n:]
    print(f"\n  === {LOG_FILE.name} (terakhir {len(tail)} baris) ===")
    print("".join(tail), end="")


# ─────────────────────────────────────────────────────────────────────────────
# ARGUMENT PARSER
# ─────────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="IDX Scalper Bot — CLI Management Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # ── start ────────────────────────────────────────────────────────────────
    p_start = sub.add_parser("start", help="Jalankan API server")
    p_start.add_argument("--port", type=int, default=None,
                         help="Port server (default dari .env API_PORT)")
    p_start.set_defaults(func=cmd_start)

    # ── stop ─────────────────────────────────────────────────────────────────
    p_stop = sub.add_parser("stop", help="Hentikan API server")
    p_stop.set_defaults(func=cmd_stop)

    # ── restart ──────────────────────────────────────────────────────────────
    p_restart = sub.add_parser("restart", help="Restart API server")
    p_restart.add_argument("--port", type=int, default=None)
    p_restart.set_defaults(func=cmd_restart)

    # ── status ───────────────────────────────────────────────────────────────
    p_status = sub.add_parser("status", help="Status server dan store stats")
    p_status.set_defaults(func=cmd_status)

    # ── scan ─────────────────────────────────────────────────────────────────
    p_scan = sub.add_parser("scan", help="Paksa scan via API")
    p_scan.set_defaults(func=cmd_scan)

    # ── prescreen ────────────────────────────────────────────────────────────
    p_pre = sub.add_parser("prescreen", help="Jalankan pre-screener via API")
    p_pre.set_defaults(func=cmd_prescreen)

    # ── bot ──────────────────────────────────────────────────────────────────
    p_bot = sub.add_parser("bot", help="Jalankan bot polling saja (tanpa server)")
    p_bot.set_defaults(func=cmd_bot)

    # ── logs ─────────────────────────────────────────────────────────────────
    p_logs = sub.add_parser("logs", help="Tampilkan log terakhir")
    p_logs.add_argument("-n", "--lines", type=int, default=50,
                        help="Jumlah baris (default 50)")
    p_logs.set_defaults(func=cmd_logs)

    # ── store ─────────────────────────────────────────────────────────────────
    p_store = sub.add_parser("store", help="Manajemen data store")
    store_sub = p_store.add_subparsers(dest="subcmd", metavar="<subcmd>")
    store_sub.required = True

    # store stats
    p_store_stats = store_sub.add_parser("stats", help="Statistik store")
    p_store_stats.set_defaults(func=cmd_store)

    # store list
    p_store_list = store_sub.add_parser("list", help="Daftar ticker tersimpan")
    p_store_list.add_argument(
        "--interval", default="5m", choices=["5m", "15m", "1h", "1d"],
        help="Filter interval"
    )
    p_store_list.set_defaults(func=cmd_store)

    # store trim
    p_store_trim = store_sub.add_parser("trim", help="Hapus data lama dari store")
    p_store_trim.add_argument(
        "--days", type=int, default=None,
        help="Hapus data lebih lama dari N hari (default DATA_STORE_MAX_DAYS)"
    )
    p_store_trim.set_defaults(func=cmd_store)

    # store delete
    p_store_del = store_sub.add_parser("delete", help="Hapus data satu ticker")
    p_store_del.add_argument("ticker", help="Kode saham (contoh: BBCA)")
    p_store_del.add_argument(
        "--interval", default=None, choices=["5m", "15m", "1h", "1d"],
        help="Hapus hanya interval tertentu (default: semua)"
    )
    p_store_del.set_defaults(func=cmd_store)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
