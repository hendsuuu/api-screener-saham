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
    "WOMF", "BCAP", "LPPS", "MPMX", "SMMA",
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
    "DSSA", "HRTA", "LMSH", "NIKL", "PURE", "SQMI",
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
