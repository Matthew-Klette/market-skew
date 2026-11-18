import pandas as pd

from market_skew.picks import choose, holdings_check, split


def _scored():
    base = dict(bucket="Contrarian Bid", close=150.0, dvol_21=5e8, source="mid", atm=0.20, ret_1m=-0.04, ret_1d=0.0,
                market_cap=200e9, name="Co")
    return pd.DataFrame([
        dict(base, symbol="CALM", sector="Staples"),
        dict(base, symbol="CALM2", sector="Staples", atm=0.22),                 # same sector, less calm: dropped
        dict(base, symbol="POP", sector="Health Care", bucket="Chase", ret_1m=0.05),
        dict(base, symbol="WILD", sector="Info Tech", atm=0.70),                # too volatile
        dict(base, symbol="TINY", sector="Energy", market_cap=2e9),             # too small
        dict(base, symbol="SCARED", sector="Utilities", bucket="Fear"),         # traders bracing
        dict(base, symbol="INSURED", sector="Financials", bucket="Hedged Rally"),
        dict(base, symbol="SLIDE", sector="Industrials", ret_1m=-0.25),         # falling hard
    ])


def test_only_big_calm_untroubled_names_one_per_sector():
    picks = choose(_scored(), {"Staples": 3.0})
    assert [p.symbol for p in picks] == ["CALM", "POP"]
    assert picks[0].timing == "add" and picks[1].timing == "wait"
    assert picks[0].score == 100 - 20 + 5


def test_calmer_name_outranks_a_dip_in_a_jumpier_one():
    rows = _scored()
    rows.loc[rows["symbol"] == "POP", "atm"] = 0.12
    assert choose(rows, {})[0].symbol == "POP"


def test_holdings_get_warning_lights_and_missing_names_are_listed():
    rows = holdings_check(_scored(), {"SCARED", "CALM", "GONE"})
    assert rows[0]["symbol"] == "SCARED" and rows[0]["label"] == "Don't add now"
    assert rows[-1]["symbol"] == "GONE" and rows[-1]["light"] == "none"


def test_split_sends_most_money_to_the_index_fund():
    picks = [{"symbol": "CALM", "timing": "add"}, {"symbol": "POP", "timing": "wait"}]
    s = split(1000, picks)
    assert s["core"] == 800 and s["each"] == 200 and s["symbols"] == ["CALM"]
    assert split(1000, [])["core"] == 1000
    six = [{"symbol": f"S{i}", "timing": "add"} for i in range(6)]
    assert split(1000, six)["each"] == 100 and len(split(1000, six)["symbols"]) == 2
