import pandas as pd

from market_skew.picks import holdings_check


def _scored():
    base = dict(bucket="Contrarian Bid", close=150.0, dvol_21=5e8, source="mid", atm=0.20, ret_1m=-0.04, ret_1d=0.0,
                market_cap=200e9, name="Co")
    return pd.DataFrame([
        dict(base, symbol="CALM", sector="Staples"),
        dict(base, symbol="SCARED", sector="Utilities", bucket="Fear"),
    ])


def test_holdings_get_warning_lights_and_missing_names_are_listed():
    rows = holdings_check(_scored(), {"SCARED", "CALM", "GONE"})
    assert rows[0]["symbol"] == "SCARED" and rows[0]["label"] == "Don't add now"
    assert rows[-1]["symbol"] == "GONE" and rows[-1]["light"] == "none"
