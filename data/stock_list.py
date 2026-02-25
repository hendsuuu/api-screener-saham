"""
Daftar saham Indonesia - Universe lengkap IDX/BEI
Suffix .JK untuk Yahoo Finance

Pendekatan baru:
  - IDX_UNIVERSE: ~400 saham aktif di BEI dari semua sektor.
    Ini adalah POOL kandidat, bukan daftar final.
  - Watchlist final ditentukan secara DINAMIS oleh DynamicPreScreener
    berdasarkan kriteria likuiditas & momentum harian, sehingga
    SEMUA saham punya kesempatan masuk screening.
"""

# ─────────────────────────────────────────────────
# INDEKS REFERENSI (untuk konteks & fallback)
# ─────────────────────────────────────────────────

LQ45 = [
    "AALI", "ADRO", "AKRA", "AMRT", "ANTM", "ASII", "BBCA", "BBNI",
    "BBRI", "BBTN", "BMRI", "BRIS", "BRPT", "BUKA", "CPIN", "EMTK",
    "ESSA", "EXCL", "GOTO", "HMSP", "HRUM", "ICBP", "INCO", "INDF",
    "INKP", "INTP", "ITMG", "KLBF", "MAPI", "MBMA", "MDKA", "MEDC",
    "MIKA", "MNCN", "PGAS", "PTBA", "PTPP", "SMGR", "TBIG", "TKIM",
    "TLKM", "TOWR", "UNTR", "UNVR", "WIIM",
]

IDX30 = [
    "ASII", "BBCA", "BBNI", "BBRI", "BMRI", "BRIS", "BUKA", "CPIN",
    "EMTK", "GOTO", "HMSP", "ICBP", "INDF", "INKP", "KLBF", "MAPI",
    "MDKA", "MEDC", "PGAS", "PTBA", "SMGR", "TLKM", "TOWR", "UNTR",
    "UNVR", "ADRO", "ANTM", "INCO", "ITMG", "PTPP",
]

# ─────────────────────────────────────────────────
# IDX UNIVERSE — Pool kandidat seluruh sektor
# ~400 saham aktif di BEI. Difilter dinamis oleh
# DynamicPreScreener sebelum analisis teknikal.
# ─────────────────────────────────────────────────

# Perbankan & Keuangan
_BANK = [
    "BBCA", "BBRI", "BMRI", "BBNI", "BBTN", "BRIS", "BTPS", "BNGA",
    "BDMN", "BJBR", "BJTM", "MEGA", "NISP", "PNBN", "BNLI", "BVIC",
    "AGRO", "ARTO", "BABP", "BBYB", "BCIC", "BGTG", "BINA", "BMAS",
    "BPFI", "BSIM", "DNAR", "INPC", "MAYA", "MCOR", "NAGA", "NOBU",
    "PNBS", "SDRA", "ADMF", "BFIN", "BPII", "CFIN", "MFIN", "VRNA",
    "WOMF", "BCAP", "LPPS", "MPMX", "SMMA","SUPA"
]

# Energi, Batubara & Migas
_ENERGI = [
    "ADRO", "PTBA", "ITMG", "HRUM", "BYAN", "ARII", "BOSS", "BSSR",
    "DEWA", "GTBO", "HIRE", "KKGI", "MBAP", "MCOL", "MITI", "MYOH",
    "PKPK", "SMRU", "SMMT", "TOBA", "GEMS", "DOID", "INDY", "BUMI",
    "MEDC", "PGAS", "ENRG", "ESSA", "ELSA", "RUIS", "ARTI", "BIPI",
    "CNKO", "FIRE", "MGAS", "SURE",
]

# Logam, Mineral & Pertambangan
_TAMBANG = [
    "ANTM", "INCO", "MDKA", "MBMA", "PSAB", "SMCB", "BRMS", "CITA",
    "DKFT", "IFSH", "IPPE", "NUSA", "POLU", "TINS", "ZINC", "CKRA",
    "DSSA", "HRTA", "LMSH", "NIKL", "PURE", "SQMI","PTRO"
]

# Telekomunikasi & Teknologi
_TELKO_TECH = [
    "TLKM", "EXCL", "ISAT", "TBIG", "TOWR", "EMTK", "GOTO", "BUKA",
    "DCII", "EDGE", "FREN", "HATM", "JGLE", "KIOS", "MCAS", "MORA",
    "MTEL", "SUPR", "SWAT", "WIFI", "YELO", "AMMN", "AXIO",
]

# Konsumer — Makanan, Minuman & Rokok
_CONSUMER_FNB = [
    "UNVR", "HMSP", "ICBP", "INDF", "CPIN", "KLBF", "WIIM", "AMRT",
    "AISA", "ALTO", "CAMP", "FAST", "FOOD", "GOOD", "HOKI", "ICBP",
    "INDF", "LAYS", "MAMIN", "MLBI", "MYOR", "PANI", "PCAR", "PSDN",
    "ROTI", "SKBM", "SKLT", "STTP", "TBLA", "ULTJ", "UNVR", "WSKT",
    "BTEK", "KEJU", "PMMP", "CLEO", "ADES", "AICE", "DLTA", "PTSP",
]

# Ritel & Distribusi
_RITEL = [
    "MAPI", "AMRT", "RALS", "CSAP", "HERO", "MIDI", "RANC", "TRIO",
    "ACES", "CENT", "CMRY", "ERAA", "FISH", "GLOB", "KICI", "LPPF",
    "MATAHARI", "MPPA", "SONA", "TELE",
]

# Properti & Real Estate
_PROPERTI = [
    "BSDE", "CTRA", "PWON", "SMRA", "LPKR", "DILD", "KIJA", "JRPT",
    "MDLN", "MTLA", "PLIN", "POOL", "PPRO", "RBMS", "RDTX", "RODA",
    "SCBD", "SMDM", "URBN", "ASRI", "BYMS", "COWL", "CSIS", "GAMA",
    "GGRP", "GPRA", "GWSA", "INPP", "ISSP", "LAND", "LCGP", "LPCK",
    "MKPI", "MORE", "MTSM", "NIRO", "NRCA", "OMRE", "PJAA", "PNSE",
    "PUDP", "PWON", "RBMS",
]

# Infrastruktur, Konstruksi & Semen
_INFRASTRUKTUR = [
    "PTPP", "WIKA", "WSKT", "WTON", "ADHI", "JSMR", "SMGR", "INTP",
    "SEMEN", "NRCA", "DGIK", "IDPR", "MIKA", "SSIA", "TOLL", "TRST",
    "WSBP", "ACST", "BTON", "CMNP", "CSMI", "DGIK", "JAKARTA",
]

# Otomotif & Alat Berat
_OTOMOTIF = [
    "ASII", "UNTR", "ASTRA", "AUTO", "HEXA", "IMAS", "INDS", "NIPS",
    "PRAS", "SMSM", "TURI", "DRMA", "GJTL", "HDTX",
]

# Kesehatan & Farmasi
_KESEHATAN = [
    "KLBF", "MIKA", "KAEF", "SIDO", "DVLA", "PYFA", "SILO", "BMHS",
    "CARE", "HEAL", "IRRA", "MERK", "PEHA", "PRDA", "SAME", "SOHO",
    "TSPC", "OMED",
]

# Pulp, Kertas & Kimia
_INDUSTRI = [
    "INKP", "TKIM", "BRPT", "TPIA", "BTRN", "SMCB", "AKRA", "DPNS",
    "EKAD", "INCI", "MDKI", "MOLI", "PICO", "SRSN", "UNIC", "AGII",
    "DUTI", "ETWA", "IPOL", "LABA", "LTLS", "MLIA", "SIAP", "SOBI",
]

# Pertanian & Agribisnis
_AGRI = [
    "AALI", "LSIP", "SIMP", "TBLA", "BWPT", "DSNG", "GOLL", "JAWA",
    "PALM", "PLTM", "SGRO", "SSMS", "TAPG",
]

# Media, Hotel & Pariwisata
_MEDIA_HOTEL = [
    "MNCN", "SCMA", "MASA", "BNBR", "BAYU", "HOME", "HOTL", "INPP",
    "JSPT", "KOIN", "MAMI", "PANR", "PDES", "PLIN", "PNSE", "PTSP",
    "SHID", "SONA", "ICON", "TMPI",
]

# Logistik & Transportasi
_LOGISTIK = [
    "JSMR", "BIRD", "CARS", "GIAA", "IATA", "SAFE", "SATK", "SMDR",
    "TMAS", "WINS", "ASSA", "BLTA", "CMPP", "DEAL", "MIRA", "NELY",
    "PEGE", "PORT", "SHIP", "TAXI",
]

# ─────────────────────────────────────────────────
# Gabungkan semua sektor → IDX_UNIVERSE (deduplikasi)
# ─────────────────────────────────────────────────
_ALL_SECTORS = (
    _BANK + _ENERGI + _TAMBANG + _TELKO_TECH +
    _CONSUMER_FNB + _RITEL + _PROPERTI + _INFRASTRUKTUR +
    _OTOMOTIF + _KESEHATAN + _INDUSTRI + _AGRI +
    _MEDIA_HOTEL + _LOGISTIK +
    LQ45 + IDX30  # pastikan semua indeks masuk
)

IDX_UNIVERSE: list = sorted(list(dict.fromkeys(_ALL_SECTORS)))
"""
Pool kandidat ~400 saham IDX.
Digunakan sebagai INPUT oleh DynamicPreScreener.
Screener akan memfilter ini berdasarkan:
  - Harga >= min_price (default 100)
  - Volume MA5 > min_volume_ma5 (default 10.000.000)
  - Value MA5 >= min_value_ma5 (default 10.000.000.000)
  - |Price change| >= min_price_change (default 2%)
  - Volume hari ini vs MA5 >= 1 + vol_change_threshold (default 1.3)
"""

# Backward-compat alias
SCREENER_WATCHLIST = list(set(LQ45 + IDX30))
# Tidak digunakan lagi sebagai default scan —
# scanner.py sekarang memanggil DynamicPreScreener.
# Tetap ada agar kode lama tidak rusak.
SCALPING_WATCHLIST = SCREENER_WATCHLIST


# ─────────────────────────────────────────────────
# MAPPING NAMA PERUSAHAAN (shared, bisa diimport)
# ─────────────────────────────────────────────────
COMPANY_NAMES: dict = {
    # Perbankan
    "BBCA": "Bank Central Asia", "BBRI": "Bank Rakyat Indonesia",
    "BMRI": "Bank Mandiri", "BBNI": "Bank Negara Indonesia",
    "BBTN": "Bank Tabungan Negara", "BRIS": "Bank Syariah Indonesia",
    "BTPS": "Bank BTPN Syariah", "BNGA": "Bank CIMB Niaga",
    "BDMN": "Bank Danamon", "BJBR": "Bank BJB",
    "BJTM": "Bank Jatim", "MEGA": "Bank Mega",
    "NISP": "Bank OCBC NISP", "PNBN": "Bank Panin",
    "ARTO": "Bank Jago", "AGRO": "Bank Raya Indonesia",
    # Energi
    "ADRO": "Adaro Energy", "PTBA": "Bukit Asam",
    "ITMG": "Indo Tambangraya Megah", "HRUM": "Harum Energy",
    "BYAN": "Bayan Resources", "MEDC": "Medco Energi",
    "ESSA": "ESSA Industries", "PGAS": "Perusahaan Gas Negara",
    "ELSA": "Elnusa", "INDY": "Indika Energy",
    "DOID": "Delta Dunia Makmur", "BUMI": "Bumi Resources",
    # Tambang
    "ANTM": "Aneka Tambang", "INCO": "Vale Indonesia",
    "MDKA": "Merdeka Copper Gold", "MBMA": "Merdeka Battery Materials",
    "TINS": "Timah",
    # Telko & Teknologi
    "TLKM": "Telkom Indonesia", "EXCL": "XL Axiata",
    "ISAT": "Indosat Ooredoo", "TBIG": "Tower Bersama",
    "TOWR": "Sarana Menara Nusantara", "EMTK": "Elang Mahkota Teknologi",
    "GOTO": "GoTo Gojek Tokopedia", "BUKA": "Bukalapak",
    "DCII": "DCI Indonesia", "MTEL": "Dayamitra Telekomunikasi",
    # Consumer
    "UNVR": "Unilever Indonesia", "HMSP": "HM Sampoerna",
    "ICBP": "Indofood CBP", "INDF": "Indofood Sukses Makmur",
    "CPIN": "Charoen Pokphand Indonesia", "KLBF": "Kalbe Farma",
    "WIIM": "Wismilak Inti Makmur", "AMRT": "Sumber Alfaria Trijaya",
    "MYOR": "Mayora Indah", "ROTI": "Nippon Indosari Corpindo",
    "ULTJ": "Ultra Jaya Milk", "MLBI": "Multi Bintang Indonesia",
    "DLTA": "Delta Djakarta", "ADES": "Akasha Wira International",
    # Ritel
    "MAPI": "Mitra Adiperkasa", "RALS": "Ramayana Lestari",
    "ACES": "Ace Hardware Indonesia", "ERAA": "Erajaya Swasembada",
    "LPPF": "Matahari Department Store",
    # Properti
    "BSDE": "BSD City", "CTRA": "Ciputra Development",
    "PWON": "Pakuwon Jati", "SMRA": "Summarecon Agung",
    "LPKR": "Lippo Karawaci", "DILD": "Intiland Development",
    "KIJA": "Kawasan Industri Jababeka", "ASRI": "Alam Sutera Realty",
    "JRPT": "Jaya Real Property", "MKPI": "Metropolitan Kentjana",
    # Infrastruktur & Semen
    "PTPP": "PP (Persero)", "WIKA": "Wijaya Karya",
    "WSKT": "Waskita Karya", "WTON": "Wijaya Karya Beton",
    "ADHI": "Adhi Karya", "JSMR": "Jasa Marga",
    "SMGR": "Semen Indonesia", "INTP": "Indocement",
    # Otomotif & Alat Berat
    "ASII": "Astra International", "UNTR": "United Tractors",
    "AUTO": "Astra Otoparts", "HEXA": "Hexindo Adiperkasa",
    "IMAS": "Indomobil Sukses International",
    # Kesehatan
    "MIKA": "Mitra Keluarga Karyasehat", "KAEF": "Kimia Farma",
    "SIDO": "Industri Jamu Sido Muncul", "DVLA": "Darya-Varia Laboratoria",
    "SILO": "Siloam International Hospitals", "TSPC": "Tempo Scan Pacific",
    "HEAL": "Medikaloka Hermina",
    # Pulp & Kimia
    "INKP": "Indah Kiat Pulp & Paper", "TKIM": "Tjiwi Kimia",
    "BRPT": "Barito Pacific", "TPIA": "Chandra Asri Pacific",
    "AKRA": "AKR Corporindo",
    # Pertanian
    "AALI": "Astra Agro Lestari", "LSIP": "PP London Sumatra",
    "SIMP": "Salim Ivomas Pratama", "TBLA": "Tunas Baru Lampung",
    # Media
    "MNCN": "Media Nusantara Citra", "SCMA": "Surya Citra Media",
}


def get_yahoo_symbol(ticker: str) -> str:
    """Konversi ticker BEI ke format Yahoo Finance (tambah .JK)."""
    if not ticker.endswith(".JK"):
        return f"{ticker}.JK"
    return ticker


def get_all_yahoo_symbols(tickers: list) -> list:
    """Konversi list ticker ke format Yahoo Finance."""
    return [get_yahoo_symbol(t) for t in tickers]


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM STOCK LIST — penambahan saham oleh admin via Telegram
# ─────────────────────────────────────────────────────────────────────────────

import json
import logging
from datetime import datetime
from pathlib import Path

_logger = logging.getLogger(__name__)
_CUSTOM_STOCKS_PATH = Path(__file__).parent / "custom_stocks.json"


def _load_custom_json() -> dict:
    """Baca file custom_stocks.json; kembalikan dict kosong jika error."""
    try:
        if _CUSTOM_STOCKS_PATH.exists():
            with open(_CUSTOM_STOCKS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        _logger.warning(f"Gagal baca custom_stocks.json: {e}")
    return {"stocks": []}


def _save_custom_json(data: dict) -> bool:
    """Tulis dict ke custom_stocks.json. Return True jika sukses."""
    try:
        with open(_CUSTOM_STOCKS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        _logger.error(f"Gagal simpan custom_stocks.json: {e}")
        return False


def load_custom_stocks() -> list:
    """
    Kembalikan list dict custom stock yang sudah ditambahkan.
    Setiap item: {"ticker": str, "name": str, "added_by": str, "added_at": str}
    """
    return _load_custom_json().get("stocks", [])


def add_custom_stock(ticker: str, name: str = "", added_by: str = "") -> tuple:
    """
    Tambahkan saham ke custom list.

    Args:
        ticker   : Kode saham BEI (tanpa .JK), huruf kapital.
        name     : Nama perusahaan (opsional).
        added_by : ID user Telegram yang menambahkan.

    Returns:
        (True, "pesan") jika berhasil ditambahkan.
        (False, "pesan") jika sudah ada atau error.
    """
    ticker = ticker.upper().strip().replace(".JK", "")
    if not ticker:
        return False, "Kode saham tidak valid."

    data = _load_custom_json()
    existing = [s["ticker"] for s in data.get("stocks", [])]

    if ticker in IDX_UNIVERSE:
        return False, f"<b>{ticker}</b> sudah ada di IDX Universe (built-in)."

    if ticker in existing:
        return False, f"<b>{ticker}</b> sudah ada di custom list."

    entry = {
        "ticker": ticker,
        "name": name.strip() if name else "",
        "added_by": str(added_by),
        "added_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    data.setdefault("stocks", []).append(entry)

    if _save_custom_json(data):
        # Update alias di COMPANY_NAMES jika ada nama
        if name:
            COMPANY_NAMES[ticker] = name.strip()
        return True, f"✅ <b>{ticker}</b> berhasil ditambahkan ke custom list."
    return False, "❌ Gagal menyimpan ke file."


def remove_custom_stock(ticker: str) -> tuple:
    """
    Hapus saham dari custom list.

    Returns:
        (True, "pesan") jika berhasil dihapus.
        (False, "pesan") jika tidak ditemukan.
    """
    ticker = ticker.upper().strip().replace(".JK", "")
    data = _load_custom_json()
    stocks = data.get("stocks", [])
    new_stocks = [s for s in stocks if s["ticker"] != ticker]

    if len(new_stocks) == len(stocks):
        return False, f"<b>{ticker}</b> tidak ditemukan di custom list."

    data["stocks"] = new_stocks
    if _save_custom_json(data):
        COMPANY_NAMES.pop(ticker, None)
        return True, f"✅ <b>{ticker}</b> berhasil dihapus dari custom list."
    return False, "❌ Gagal menyimpan ke file."


def get_effective_universe() -> list:
    """
    Kembalikan IDX_UNIVERSE + custom stocks (deduplikasi, terurut).
    Ini adalah pool lengkap yang digunakan oleh scanner dan pre-screener.
    """
    custom_tickers = [s["ticker"] for s in load_custom_stocks()]
    combined = list(dict.fromkeys(IDX_UNIVERSE + custom_tickers))
    return combined


def get_sector_map() -> dict:
    """
    Kembalikan mapping {sector_name: [tickers]} untuk tampilan /stocklist.
    """
    return {
        "🏦 Perbankan & Keuangan": _BANK,
        "⚡ Energi & Batubara": _ENERGI,
        "⛏ Tambang & Mineral": _TAMBANG,
        "📡 Telko & Teknologi": _TELKO_TECH,
        "🛒 Consumer & F&B": _CONSUMER_FNB,
        "🏪 Ritel": _RITEL,
        "🏠 Properti": _PROPERTI,
        "🏗 Infrastruktur & Semen": _INFRASTRUKTUR,
        "🚗 Otomotif": _OTOMOTIF,
        "💊 Kesehatan & Farmasi": _KESEHATAN,
        "🏭 Industri & Kimia": _INDUSTRI,
        "🌾 Agribisnis": _AGRI,
        "🎬 Media & Hotel": _MEDIA_HOTEL,
        "🚢 Logistik & Trans.": _LOGISTIK,
    }
