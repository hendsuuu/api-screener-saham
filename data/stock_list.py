"""
Daftar saham Indonesia - LQ45, IDX30, Saham Unggulan
Suffix .JK untuk Yahoo Finance
"""

# LQ45 - 45 saham likuid terbesar di BEI
LQ45 = [
    "AALI", "ADRO", "AKRA", "AMRT", "ANTM", "ASII", "BBCA", "BBNI",
    "BBRI", "BBTN", "BMRI", "BRIS", "BRPT", "BUKA", "CPIN", "EMTK",
    "ESSA", "EXCL", "GOTO", "HMSP", "HRUM", "ICBP", "INCO", "INDF",
    "INKP", "INTP", "ITMG", "KLBF", "MAPI", "MBMA", "MDKA", "MEDC",
    "MIKA", "MNCN", "PGAS", "PTBA", "PTPP", "SMGR", "TBIG", "TKIM",
    "TLKM", "TOWR", "UNTR", "UNVR", "WIIM"
]

# IDX30 - 30 saham terpilih
IDX30 = [
    "ASII", "BBCA", "BBNI", "BBRI", "BMRI", "BRIS", "BUKA", "CPIN",
    "EMTK", "GOTO", "HMSP", "ICBP", "INDF", "INKP", "KLBF", "MAPI",
    "MDKA", "MEDC", "PGAS", "PTBA", "SMGR", "TLKM", "TOWR", "UNTR",
    "UNVR", "ADRO", "ANTM", "INCO", "ITMG", "PTPP"
]

# Saham Perbankan Big4
PERBANKAN = ["BBCA", "BBRI", "BMRI", "BBNI", "BBTN", "BRIS", "MEGA", "NISP"]

# Saham Energi & Tambang
ENERGI = ["ADRO", "ANTM", "PTBA", "ITMG", "INCO",
          "MDKA", "MEDC", "PGAS", "HRUM", "BYAN"]

# Saham Teknologi & Digital
TEKNOLOGI = ["GOTO", "BUKA", "EMTK", "TLKM", "EXCL", "ISAT", "TBIG", "TOWR"]

# Saham Consumer
CONSUMER = ["UNVR", "HMSP", "ICBP", "INDF",
            "KLBF", "MAPI", "CPIN", "WIIM", "AMRT"]

# Saham Infrastruktur
INFRASTRUKTUR = ["PTPP", "WIKA", "WSKT", "WTON", "ADHI", "JSMR", "TLKM"]

# Saham Properti
PROPERTI = ["BSDE", "CTRA", "PWON", "SMRA", "LPKR", "DILD", "KIJA"]

# Gabungan screener utama (hindari duplikasi)
SCREENER_WATCHLIST = list(set(LQ45 + IDX30))

# Saham pilihan untuk scalping (likuid tinggi, spread kecil)
SCALPING_WATCHLIST = [
    "BBCA", "BBRI", "BMRI", "BBNI", "TLKM", "ASII", "UNTR",
    "ADRO", "ANTM", "PTBA", "ITMG", "INCO", "MDKA",
    "GOTO", "BUKA", "EMTK",
    "ICBP", "INDF", "KLBF", "UNVR",
    "SMGR", "INTP", "PGAS",
    "INKP", "TKIM", "BRPT",
    "BRIS", "BBTN", "MAPI", "CPIN",
    "HRUM", "BYAN", "MEDC", "ESSA"
]


def get_yahoo_symbol(ticker: str) -> str:
    """Konversi ticker BEI ke format Yahoo Finance (tambah .JK)"""
    if not ticker.endswith(".JK"):
        return f"{ticker}.JK"
    return ticker


def get_all_yahoo_symbols(tickers: list) -> list:
    """Konversi list ticker ke format Yahoo Finance"""
    return [get_yahoo_symbol(t) for t in tickers]
