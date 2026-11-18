"""The 11 GICS sectors, their SPDR ETFs, and Nasdaq's listing labels mapped onto them.

Nasdaq's own sector field is loose (it files Agilent under Industrials and shipping lines under Consumer
Discretionary), so the finer industry label decides first, the sector field second, and a short list of big
names that GICS moved (Alphabet, Meta, Visa...) is pinned by hand.
"""
SECTOR_ETFS = {
    "Info Tech": "XLK", "Materials": "XLB", "Energy": "XLE", "Industrials": "XLI", "Health Care": "XLV",
    "Financials": "XLF", "Staples": "XLP", "Cons Disc": "XLY", "Comm Svcs": "XLC", "Utilities": "XLU",
    "Real Estate": "XLRE",
}
INDEXES = {"SPY": "S&P 500", "QQQ": "Nasdaq 100", "IWM": "Russell 2000", "RSP": "S&P equal weight"}
VOL_INDEX = "^VIX"
UNCLASSIFIED = "Unclassified"

PINNED = {
    **dict.fromkeys(["GOOGL", "GOOG", "META", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS", "CHTR", "EA", "TTWO", "RBLX",
                     "SPOT", "PINS", "SNAP", "TTD", "WBD", "PARA", "LYV", "MTCH", "ROKU", "OMC", "IPG", "FOXA", "FOX",
                     "NWSA", "NWS", "TKO", "Z", "ZG", "TRIP", "RDDT", "SIRI"], "Comm Svcs"),
    **dict.fromkeys(["AMZN", "TSLA", "BKNG", "ABNB", "EBAY", "ETSY", "CHWY", "DASH", "UBER", "LYFT", "CVNA", "W"], "Cons Disc"),
    **dict.fromkeys(["V", "MA", "PYPL", "FI", "FIS", "GPN", "AXP", "COF", "SOFI", "AFRM", "HOOD", "COIN", "XYZ", "TOST"], "Financials"),
    **dict.fromkeys(["WMT", "COST", "KR", "TGT", "DG", "DLTR", "BJ"], "Staples"),
    **dict.fromkeys(["A", "TMO", "DHR", "WAT", "MTD", "IQV", "ILMN", "BRKR"], "Health Care"),
    **dict.fromkeys(["MMM", "HON", "GE", "ITW", "EMR"], "Industrials"),
}
MATERIALS = {"Major Chemicals", "Agricultural Chemicals", "Specialty Chemicals", "Aluminum", "Steel/Iron Ore",
             "Precious Metals", "Metal Mining", "Other Metals and Minerals", "Mining & Quarrying of Nonmetallic Minerals (No Fuels)",
             "Building Materials", "Containers/Packaging", "Plastic Products", "Paper", "Forest Products", "Paints/Coatings"}
COMM = {"Advertising", "Broadcasting", "Movies/Entertainment", "Publishing", "Newspapers/Magazines", "Books",
        "Cable & Other Pay Television Services"}
TECH = {"Semiconductors", "Telecommunications Equipment", "Computer Communications Equipment", "Electronic Components",
        "Electronics Distribution", "Computer peripheral equipment", "Computer Manufacturing", "EDP Services",
        "Computer Software: Prepackaged Software", "Computer Software: Programming Data Processing",
        "Radio And Television Broadcasting And Communications Equipment", "Retail: Computer Software & Peripheral Equipment"}
STAPLES = {"Package Goods/Cosmetics", "Tobacco", "Food Distributors", "Farming/Seeds/Milling", "Beverages (Production/Distribution)",
           "Food Chains", "Meat/Poultry/Fish", "Packaged Foods", "Retail-Drug Stores and Proprietary Stores", "Specialty Foods"}
CONS_DISC = {"Auto Manufacturing", "Auto Parts:O.E.M.", "Homebuilding", "Home Furnishings", "Garments and Clothing",
             "Apparel", "Other Specialty Stores", "Consumer Electronics/Appliances", "Restaurants", "Hotels/Resorts",
             "Clothing/Shoe/Accessory Stores", "Department/Specialty Retail Stores", "Recreational Games/Products/Toys",
             "Services-Misc. Amusement & Recreation", "Retail-Auto Dealers and Gas Stations", "RETAIL: Building Materials",
             "Shoe Manufacturing", "Auto & Home Supply Stores", "Automotive Aftermarket", "Catalog/Specialty Distribution",
             "Other Consumer Services", "Consumer Specialties", "Consumer Electronics/Video Chains", "Textiles", "Durable Goods",
             "Motor Vehicles"}
ENERGY = {"Oil & Gas Production", "Oil/Gas Transmission", "Integrated oil Companies", "Oil Refining/Marketing",
          "Oilfield Services/Equipment", "Oil and Gas Field Machinery", "Coal Mining"}
UTILITIES = {"Electric Utilities: Central", "Natural Gas Distribution", "Water Supply", "Power Generation"}
HEALTH = {"Biotechnology: Laboratory Analytical Instruments"}
BY_SECTOR = {"Technology": "Info Tech", "Health Care": "Health Care", "Finance": "Financials", "Real Estate": "Real Estate",
             "Utilities": "Utilities", "Energy": "Energy", "Basic Materials": "Materials", "Consumer Staples": "Staples",
             "Telecommunications": "Comm Svcs", "Industrials": "Industrials", "Consumer Discretionary": "Industrials",
             "Miscellaneous": "Industrials"}


def classify(symbol: str, sector: str | None, industry: str | None) -> str:
    sector, industry = (sector or "").strip(), (industry or "").strip()
    if symbol in PINNED:
        return PINNED[symbol]
    if sector == "Health Care" or industry in HEALTH:
        return "Health Care"
    if sector == "Real Estate" and industry != "Homebuilding":
        return "Real Estate"
    if sector == "Finance":
        return "Real Estate" if industry == "Real Estate" else "Financials"
    for group, name in ((ENERGY, "Energy"), (UTILITIES, "Utilities"), (MATERIALS, "Materials"), (COMM, "Comm Svcs"),
                        (TECH, "Info Tech"), (STAPLES, "Staples"), (CONS_DISC, "Cons Disc")):
        if industry in group:
            if name == "Utilities" and sector == "Technology":
                break
            return name
    return BY_SECTOR.get(sector, UNCLASSIFIED)
