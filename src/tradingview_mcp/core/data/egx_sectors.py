"""EGX (Egyptian Exchange) sector classification for stock symbols.

Symbols validated against the live TradingView egypt-market listing on
2026-08-26; 12 delisted/suspended symbols were pruned. New listings are
NOT auto-assigned to sectors (sector membership needs manual research) —
the full live universe lives in coinlist/egx.txt.
"""
from __future__ import annotations
from typing import Any, Dict, List, Set

# Sector metadata: market cap weight (%), value traded (LE), volume, market cap (LE)
EGX_SECTOR_META: Dict[str, Dict[str, Any]] = {
    "banks": {
        "market_cap_weight": 24.25,
        "market_cap_le": 764_739_680_138,
        "value_le": 535_771_978,
        "value_pct": 9.30,
        "volume": 7_178_860,
        "volume_pct": 0.35,
    },
    "basic_resources": {
        "market_cap_weight": 15.96,
        "market_cap_le": 503_377_840_279,
        "value_le": 943_626_902,
        "value_pct": 16.38,
        "volume": 34_419_148,
        "volume_pct": 1.70,
    },
    "healthcare_and_pharma": {
        "market_cap_weight": 3.02,
        "market_cap_le": 95_339_365_687,
        "value_le": 362_201_314,
        "value_pct": 6.29,
        "volume": 168_389_924,
        "volume_pct": 8.29,
    },
    "industrial_goods_and_services": {
        "market_cap_weight": 6.58,
        "market_cap_le": 207_482_953_267,
        "value_le": 94_232_268,
        "value_pct": 1.64,
        "volume": 35_123_104,
        "volume_pct": 1.73,
    },
    "real_estate": {
        "market_cap_weight": 11.89,
        "market_cap_le": 374_996_430_009,
        "value_le": 1_328_214_860,
        "value_pct": 23.06,
        "volume": 1_069_999_779,
        "volume_pct": 52.70,
    },
    "travel_and_leisure": {
        "market_cap_weight": 0.85,
        "market_cap_le": 26_710_170_478,
        "value_le": 45_559_591,
        "value_pct": 0.79,
        "volume": 5_080_616,
        "volume_pct": 0.25,
    },
    "utilities": {
        "market_cap_weight": 0.75,
        "market_cap_le": 23_686_451_422,
        "value_le": 8_432_609,
        "value_pct": 0.15,
        "volume": 446_683,
        "volume_pct": 0.02,
    },
    "it_media_and_communication": {
        "market_cap_weight": 9.36,
        "market_cap_le": 295_321_450_209,
        "value_le": 397_424_046,
        "value_pct": 6.90,
        "volume": 87_306_677,
        "volume_pct": 4.30,
    },
    "food_beverages_and_tobacco": {
        "market_cap_weight": 8.15,
        "market_cap_le": 256_955_059_857,
        "value_le": 307_973_960,
        "value_pct": 5.35,
        "volume": 72_721_257,
        "volume_pct": 3.58,
    },
    "energy_and_support_services": {
        "market_cap_weight": 0.68,
        "market_cap_le": 21_314_790_445,
        "value_le": 110_033_851,
        "value_pct": 1.91,
        "volume": 12_513_370,
        "volume_pct": 0.62,
    },
    "trade_and_distributors": {
        "market_cap_weight": 1.10,
        "market_cap_le": 34_759_558_266,
        "value_le": 103_562_606,
        "value_pct": 1.80,
        "volume": 12_208_009,
        "volume_pct": 0.60,
    },
    "shipping_and_transportation": {
        "market_cap_weight": 3.22,
        "market_cap_le": 101_692_038_998,
        "value_le": 73_947_527,
        "value_pct": 1.28,
        "volume": 3_412_518,
        "volume_pct": 0.17,
    },
    "education_services": {
        "market_cap_weight": 1.48,
        "market_cap_le": 46_606_969_683,
        "value_le": 13_224_589,
        "value_pct": 0.23,
        "volume": 9_489_540,
        "volume_pct": 0.47,
    },
    "non_bank_financial_services": {
        "market_cap_weight": 6.91,
        "market_cap_le": 217_831_009_414,
        "value_le": 828_813_172,
        "value_pct": 14.39,
        "volume": 267_507_864,
        "volume_pct": 13.18,
    },
    "contracting_and_construction": {
        "market_cap_weight": 2.13,
        "market_cap_le": 67_067_682_370,
        "value_le": 242_741_327,
        "value_pct": 4.21,
        "volume": 181_352_942,
        "volume_pct": 8.93,
    },
    "textiles_and_durables": {
        "market_cap_weight": 1.10,
        "market_cap_le": 34_831_779_103,
        "value_le": 81_577_559,
        "value_pct": 1.42,
        "volume": 29_970_788,
        "volume_pct": 1.48,
    },
    "building_materials": {
        "market_cap_weight": 2.39,
        "market_cap_le": 75_364_203_134,
        "value_le": 273_177_371,
        "value_pct": 4.74,
        "volume": 12_115_171,
        "volume_pct": 0.60,
    },
    "paper_and_packaging": {
        "market_cap_weight": 0.18,
        "market_cap_le": 5_803_552_401,
        "value_le": 9_590_748,
        "value_pct": 0.17,
        "volume": 21_227_330,
        "volume_pct": 1.04,
    },
}

# Sector mapping: sector name -> set of ticker symbols (without EGX: prefix)
EGX_SECTORS: Dict[str, Set[str]] = {

    "banks": {
        "CANA",  # Suez Canal Bank
        "EXPA",  # Export Development Bank
        "CIEB",  # Credit Agricole Egypt
        "SAUD",  # Al Baraka Bank
        "UBEE",  # The United Bank
        "EGBE",  # Egyptian Gulf Bank
        "HDBK",  # Housing & Development Bank
        "FAIT",  # Faisal Islamic Bank
        "FAITA", # Faisal Islamic Bank (USD)
        "QNBE",  # QNB Alahli
        "COMI",  # CIB
        "ADIB",  # ADIB Egypt
    },

    "basic_resources": {
        "ATQA",  # Misr National Steel - Ataqa
        "MICH",  # Misr Chemical Industries
        "KZPC",  # Kafr El Zayat Pesticides
        "ASCM",  # ASEC Company For Mining - ASCOM
        "SKPC",  # Sidi Kerir Petrochemicals - SIDPEC
        "ISMQ",  # Iron And Steel for Mines and Quarries
        "EGCH",  # Egyptian Chemical Industries (Kima)
        "EFIC",  # Egyptian Financial & Industrial
        "IRON",  # Egyptian Iron & Steel
        "ALUM",  # Arab Aluminum
        "MFPC",  # Misr Fertilizers Production Company - Mopco
        "EGAL",  # Egypt Aluminum
        "ABUK",  # Abou Kir Fertilizers
    },

    "healthcare_and_pharma": {
        "MIPH",  # Minapharm Pharmaceuticals
        "RMDA",  # Rameda
        "BIOC",  # Glaxo Smith Kline	
        "AXPH",  # Alexandria Pharmaceuticals
        "OCPH",  # October Pharma
        "APPC",  # Arab Pharmaceuticals
        "SIPC",  # Sabaa International Company
        "MCRO",  # Macro Group Pharmaceuticals
        "ISPH",  # Ibnsina Pharma
        "SPMD",  # Speed Medical
        "CPCI",  # Cairo Pharmaceuticals
        "PRMH",  # Premium HealthCare Group
        "MPCI",  # Memphis Pharmaceuticals
        "NIPH",  # El-Nile Pharmaceuticals
        "NINH",  # Nozha International Hospital
        "AMES",  # Alexandria New Medical Center
        "CLHO",  # Cleopatra Hospital Company
        "PHAR",  # EIPICO
    },

    "industrial_goods_and_services": {
        "ENGC",  # El Arabia Engineering Industries
        "SWDY",  # Elsewedy Electric
        "GDWA",  # Gadwa For Industrial Development
        "DTPP",  # Delta Printing & Packaging
        "ELEC",  # Electro Cable Egypt
        "GBCO",  # GB Corp
    },

    "real_estate": {
        "RREI",  # Arab Real Estate Investment CO.-ALICO
        "MAAL",  # Egyptian Gulf Marseilia
        "ELSH",  # El Shams Housing
        "AREH",  # Egyptian Real Estate Group
        "ORHD",  # Orascom Development Egypt
        "GIHD",  # Gharbia Islamic Housing Development
        "MASR",  # Madinet Masr
        "OCDI",  # SODIC
        "EMFD",  # Emaar Misr
        "TMGH",  # Talaat Moustafa Group
        "PHDC",  # Palm Hills
        "HELI",  # Heliopolis Housing
        "ZMID",  # Zahraa Maadi
        "ADRI",  # Arab Developers Holding
        "IDRE",  # Ismailia Development
        "AMER",  # Amer Group
        "OBRI",  # El Obour Real Estate
        "PRDC",  # Pioneers Properties
        "UEGC",  # ElSaeed Contracting
        "ELKA",  # El Kahera Housing
    },

    "travel_and_leisure": {
        "MHOT",  # Misr Hotels
        "MMAT",  # Marsa Marsa Alam For Tourism Development
        "SDTI",  # Sharm Dreams Co. for Tourism Investment
        "ROTO",  # Rowad Tourism (Al Rowad)
        "ELWA",  # El Wadi For International and Investment Development
        "PHTV",  # Pyramisa Hotels
        "EGTS",  # Egyptian for Tourism Resorts
        "TRTO",  # TransOceans Tours
        "RTVC",  # Remco for Touristic Villages Construction
    },

    "utilities": {
        "EGAS", # Natural Gas & Mining Project (Egypt Gas)
        "TAQA", # Taqa Arabia
    },

    "it_media_and_communication": {
        "DGTZ",  # Digitize for Investment And Technology
        "MPRC",  # Egyptian Media Production City
        "EGSA",  # Egyptian Satellites (NileSat) (USD)
        "EFIH",  # E-finance
        "RACC",  # Raya Customer Experience
        "OIH",   # Orascom Investment Holding
        "FWRY",  # Fawry
        "ETEL",  # Telecom Egypt
    },

    "food_beverages_and_tobacco": {
        "ELNA",  # El Nasr For Manufacturing Agricultural Crops
        "KRDI",  # Al Khair River For Development Agricultural Investment & Environmental Services
        "GSSC",  # General Silos & Storage
        "CEFM",  # Middle Egypt Flour Mills
        "SUGR",  # Delta Sugar
        "ADPC",  # The Arab Dairy Products Co. Arab Dairy - Panda
        "LUTS",  # Lotus For Agricultural Investments And Development
        "GGRN",  # Gogreen for Agricultural Investment
        "INFI",  # Ismailia National Food Industries
        "ISMA",  # Ismailia Misr Poultry
        "MPCO",  # Mansourah Poultry
        "POUL",  # Cairo Poultry
        "EPCO",  # Egypt for Poultry
        "EAST",  # Eastern Company
        "ZEOT",  # Extracted Oils
        "MILS",  # North Cairo Mills
        "AFMC",  # Alexandria Flour Mills
        "UEFM",  # Upper Egypt Flour Mills
        "WCDF",  # Middle & West Delta Flour Mills
        "SCFM",  # South Cairo & Giza Mills & Bakeries
        "COSG",  # Cairo Oils & Soap
        "MOSC",  # Misr Oils & Soap
        "AJWA",  # AJWA for Food Industries company Egypt
        "SNFC",  # Sharkia National Food
        "DOMT",  # Arabian Food Industries DOMTY
        "NEDA",  # Northern Upper Egypt Development & Agricultural Production
        "JUFO",  # Juhayna Food Industries
        "EFID",  # Edita Food Industries S.A.E
        "OLFI",  # Obour Land For Food Industries
        "EDFM",  # East Delta Flour Mills
    },

    "energy_and_support_services": {
        "MOIL",  # Maridive & Oil Services
        "AMOC",  # Alexandria Mineral Oils Company
    },

    "trade_and_distributors": {
        "IFAP",  # International Agricultural Products
        "SMFR",  # Samad Misr - EGYFERT
        "ICFC",  # International Company For Fertilizers & Chemicals
        "MFSC",  # Misr Duty Free Shops
        "GMCI",  # GMC Group
        "MTIE",  # MM Group For Industry And International Trade
        "GOUR",  # Gourmet Egypt.Com Foods
    },

    "shipping_and_transportation": {
        "ETRS",  # Egyptian Transport (EGYTRANS)
        "ALCN",  # Alexandria Containers and Goods
        "CSAG",  # Canal Shipping Agencies
    },

    "education_services": {
        "MOED",  # The Egyptian Modern Education Systems
        "SCTS",  # Suez Canal Company For Technology Settling
        "TALM",  # Taaleem Management Services
        "CAED",  # Cairo Educational Services
        "CIRA",  # Cairo For Investment And Real Estate Developments (CIRA Edu)
    },

    "non_bank_financial_services": {
        "ACTF",  # Act Financial
        "AIH",   # Arabia Investments Holding
        "NAHO",  # Naeem Holding
        "RAYA",  # Raya Holding For Financial Investments
        "CICH",  # CI Capital Holding
        "BTFH",  # Beltone Holding
        "KWIN",  # El Kahera El Watania Investment
        "AMIA",  # Arab Moltaka Investments
        "OBRI",  # O B Financial Holding
        "AFDI",  # El Ahli Investment and Development
        "VALU",  # U Consumer Finance (ValU)
        "AIDC",  # Arabia for Investment and Development
        "ICLE",  # IncoLEASE
        "PRMH",  # Prime Holding
        "ASPI",  # Aspire Capital
        "MOIN",  # Mohandes Insurance
        "HRHO",  # EFG Holding
        "SEIG",  # Saudi Egyptian Investment & Finance
        "ODIN",  # ODIN Investments
        "ATLC",  # A.T.LEASE
        "BINV",  # B Investments Holding
        "GRCA",  # Grand Investment Capital
        "CCAP",  # QALA (Citadel Capital)
        "CNFN",  # Contact Financial Holding
        "VLMR",   # Valmore Holding (USD)
        "VLMRA",  # Valmore Holding (EGP)
    },

    "contracting_and_construction": {
        "WKOL",  # Wadi Kom Ombo Land Reclamation
        "AALR",  # General Company For Land Reclamation
        "GGCC",  # Giza General Contracting
        "IEEC",  # Industrial & Engineering Projects
        "NCCW",  # Nasr Company for Civil Works
        "ORAS",  # Orascom Construction PLC
        "GPIM",  # GPI For Urban Growth
        "COPR",  # Copper For Commercial Investment & Real Estate Development
        "EALR",  # El Arabia for Land Reclamation
        "CRST",  # Creast Mark For Contracting
    },

    "textiles_and_durables": {
        "DSCW",  # Dice Sport & Casual Wear
        "APSW",  # Arab Polvara Spinning & Weaving
        "GTWL",  # Golden Textiles & Clothes Wool
        "KABO",  # El Nasr Clothes & Textiles
        "ORWE",  # Oriental Weavers
        "CFGH",  # Concrete Fashion Group
        "SPIN",  # Alexandria Spinning & Weaving (Spinalex)
        "ACGC",  # Arab Cotton Ginning
        "GTEX",  # GTEX For Commercial And Industrial
    },

    "building_materials": {
        "CERA",  # Ceramic & Porcelain
        "RREI",  # Ceramica Remas (verify source naming if needed)
        "MBSC",  # Misr Beni Suef Cement
        "ARCC",  # Arabian Cement Company
        "SVCE",  # South Valley Cement
        "PRCL",  # El Ezz Porcelain (Gemma)
        "LCSW",  # Lecico Egypt
        "SCEM",  # Sinai Cement
        "MCQE",  # Misr Cement (Qena)
        "RUBX",  # Rubex International
    },

    "paper_and_packaging": {
        "RAKT",  # Rakta Paper Manufacturing
        "UNIP",  # Universal For Paper and Packaging Materials (Unipack)
        "EPPK",  # El Ahram Co. For Printing And Packing
    },
}

# Symbols denominated in USD (all others are EGP)
EGX_USD_SYMBOLS: Set[str] = {
    "FAITA",  # Faisal Islamic Bank (USD)
    "VLMR",   # Valmore Holding (USD)
    "EGSA",   # Egyptian Satellites - NileSat
    "SAIB",   # Societe Arabe Internationale de Banque
    "MOIL",   # Maridive & Oil Services
    "NAHO",   # Naeem Holding
    "EGBE",   # Egyptian Gulf Bank
    "TRTO",   # TransOceans Tours
    "NDRL",   # National Drilling Company 
    "GPPL",   # Golden Pyramids Plaza
}


def get_currency(symbol: str) -> str:
    """Return 'USD' or 'EGP' for an EGX symbol."""
    clean = symbol.upper().replace("EGX:", "")
    return "USD" if clean in EGX_USD_SYMBOLS else "EGP"


# Reverse lookup: symbol -> sector
_SYMBOL_TO_SECTOR: Dict[str, str] = {}
for _sector, _symbols in EGX_SECTORS.items():
    for _sym in _symbols:
        if _sym not in _SYMBOL_TO_SECTOR:
            _SYMBOL_TO_SECTOR[_sym] = _sector


def get_sector(symbol: str) -> str:
    """Return the sector for an EGX symbol, or 'other' if not classified."""
    clean = symbol.upper().replace("EGX:", "")
    return _SYMBOL_TO_SECTOR.get(clean, "other")


def get_symbols_by_sector(sector: str) -> List[str]:
    """Return list of EGX symbols for a given sector."""
    key = sector.lower().replace(" ", "_")
    symbols = EGX_SECTORS.get(key, set())
    return [f"EGX:{s}" for s in sorted(symbols)]


def get_all_sectors() -> List[str]:
    """Return list of all available EGX sectors."""
    return sorted(EGX_SECTORS.keys())


def get_sector_meta(sector: str) -> Dict[str, Any]:
    """Return metadata (market cap weight, value, volume) for a sector."""
    key = sector.lower().replace(" ", "_")
    return EGX_SECTOR_META.get(key, {})


def get_sectors_by_weight(descending: bool = True) -> List[Dict[str, Any]]:
    """Return all sectors sorted by market cap weight."""
    result = []
    for key, meta in EGX_SECTOR_META.items():
        result.append({"sector": key, **meta})
    result.sort(key=lambda x: x["market_cap_weight"], reverse=descending)
    return result


# Display-friendly sector names
SECTOR_DISPLAY_NAMES: Dict[str, str] = {
    "banks": "Banks",
    "basic_resources": "Basic Resources",
    "healthcare_and_pharma": "Health Care & Pharmaceuticals",
    "industrial_goods_and_services": "Industrial Goods, Services & Automobiles",
    "real_estate": "Real Estate",
    "travel_and_leisure": "Travel & Leisure",
    "utilities": "Utilities",
    "it_media_and_communication": "IT, Media & Communication Services",
    "food_beverages_and_tobacco": "Food, Beverages & Tobacco",
    "energy_and_support_services": "Energy & Support Services",
    "trade_and_distributors": "Trade & Distributors",
    "shipping_and_transportation": "Shipping & Transportation Services",
    "education_services": "Education Services",
    "non_bank_financial_services": "Non-Bank Financial Services",
    "contracting_and_construction": "Contracting & Construction Engineering",
    "textiles_and_durables": "Textile & Durables",
    "building_materials": "Building Materials",
    "paper_and_packaging": "Paper & Packaging",
}
