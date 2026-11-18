from market_skew.sectors import classify


def test_industry_beats_nasdaqs_loose_sector_field():
    assert classify("ZIM", "Consumer Discretionary", "Marine Transportation") == "Industrials"
    assert classify("XOM", "Energy", "Integrated oil Companies") == "Energy"
    assert classify("DOW", "Industrials", "Major Chemicals") == "Materials"
    assert classify("NEM", "Basic Materials", "Precious Metals") == "Materials"
    assert classify("KMI", "Utilities", "Oil/Gas Transmission") == "Energy"


def test_gics_moves_are_pinned():
    assert classify("META", "Technology", "Computer Software: Programming Data Processing") == "Comm Svcs"
    assert classify("V", "Consumer Discretionary", "Business Services") == "Financials"
    assert classify("A", "Industrials", "Biotechnology: Laboratory Analytical Instruments") == "Health Care"


def test_reits_banks_and_unknowns():
    assert classify("O", "Real Estate", "Real Estate Investment Trusts") == "Real Estate"
    assert classify("JPM", "Finance", "Major Banks") == "Financials"
    assert classify("NEWCO", "", "") == "Unclassified"
