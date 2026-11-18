import math

import pandas as pd
import pytest

from market_skew import costs
from market_skew.swing import choose, net_return, record, settle

TODAY = "2026-11-18"
CALM = {"SPY": {"ret_1m": 0.01}, "VIX": {"ret_1d": 0.0}}
STORM = {"SPY": {"ret_1m": -0.06}, "VIX": {"ret_1d": 0.07}}


def _scored():
    base = dict(bucket="Contrarian Bid", close=50.0, dvol_21=2e8, source="mid", atm=0.40, ret_1m=-0.08, ret_1d=0.01,
                asym=30, name="Co")
    return pd.DataFrame([
        dict(base, symbol="A", sector="Tech", asym=40),
        dict(base, symbol="A2", sector="Tech", asym=35),                  # same sector, lower: dropped
        dict(base, symbol="B", sector="Energy", ret_1d=-0.01, asym=20),
        dict(base, symbol="CHEAP", sector="Health", close=4.0),
        dict(base, symbol="THIN", sector="Utilities", dvol_21=4e7),
        dict(base, symbol="QUOTE", sector="Staples", source="last"),
        dict(base, symbol="WILD", sector="Financials", atm=1.2),
        dict(base, symbol="CRASH", sector="Materials", ret_1m=-0.40),
        dict(base, symbol="CHASE", sector="Industrials", bucket="Chase"),
    ])


def test_picks_only_contrarian_bids_that_pass_every_filter_one_per_sector():
    trades = choose(_scored(), {}, CALM, TODAY, set())
    assert [t.symbol for t in trades] == ["A", "B"]


def test_score_adds_up_today_and_sector_inflow():
    trades = choose(_scored(), {"Energy": 5.0}, CALM, TODAY, set())
    assert [t.score for t in trades] == [40 + 15, 20 + 10]
    assert [t.symbol for t in trades] == ["A", "B"]


def test_excluded_names_and_max_five():
    rows = pd.concat([_scored()] + [_scored().iloc[[0]].assign(symbol=f"X{i}", sector=f"S{i}") for i in range(6)])
    assert len(choose(rows, {}, CALM, TODAY, set())) == 5
    assert "A" not in [t.symbol for t in choose(_scored(), {}, CALM, TODAY, {"A"})]


def test_stormy_market_allows_two():
    rows = pd.concat([_scored()] + [_scored().iloc[[0]].assign(symbol=f"X{i}", sector=f"S{i}") for i in range(3)])
    assert len(choose(rows, {}, STORM, TODAY, set())) == 2
    assert len(choose(rows, {}, {"SPY": {"ret_1m": -0.06}, "VIX": {"ret_1d": 0.0}}, TODAY, set())) > 2


def test_plan_maths_wide_stop_for_jumpy_names():
    t = choose(_scored(), {}, CALM, TODAY, set())[0]  # atm 0.40
    move = 1.2 * 0.40 * math.sqrt(10 / 252)
    assert t.stop == pytest.approx(50 * (1 - move))
    assert t.target == pytest.approx(50 + 2 * (50 - t.stop))
    assert t.until == "2026-12-16"


def test_plan_maths_stop_never_tighter_than_four_percent():
    rows = _scored().assign(atm=0.10)
    t = choose(rows, {}, CALM, TODAY, set())[0]
    assert t.stop == pytest.approx(50 * 0.96)


def test_reasons_are_plain_words():
    t = choose(_scored(), {"Tech": 3.0}, CALM, TODAY, set())[0]
    text = " ".join(t.reasons)
    assert "down 8% this month" in text.lower() and "bounce" in text
    assert "first sign" in text and "flowing into Tech" in text


def _trade(**kw):
    return dict(date="2026-11-02", entry=100.0, stop=90.0, target=120.0, until="2026-11-30", **kw)


def _closes(values, start="2026-11-02"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)))


def test_settle_stop_target_time_and_still_open():
    assert settle(_trade(), _closes([100, 95, 89, 130]))["status"] == "stopped"
    out = settle(_trade(), _closes([100, 105, 121, 80]))
    assert out["status"] == "target" and out["exit_price"] == 121 and out["exit_date"] == "2026-11-04"
    assert settle(_trade(), _closes([100] + [101] * 30))["status"] == "time"
    assert settle(_trade(), _closes([100, 101, 102])) is None


def test_settle_ignores_the_entry_day_and_earlier():
    assert settle(_trade(), _closes([80, 100, 100], start="2026-10-30")) is None


def test_net_return_subtracts_round_trip_fees():
    gross = net_return(100.0, 100.0)
    assert gross == pytest.approx((1 - costs.RATES["usd_buy"]) * (1 - costs.RATES["usd_sell"]) - 1)
    assert -0.0135 < gross < -0.0125
    assert net_return(100.0, 120.0) == pytest.approx(1.2 * (1 - costs.RATES["usd_buy"]) * (1 - costs.RATES["usd_sell"]) - 1)


def test_record_open_and_closed_against_voo():
    idx = pd.bdate_range("2026-11-02", periods=4)
    closes = pd.DataFrame({"VOO": [500, 505, 510, 515.0], "AA": [100, 104, 108, 110.0]}, index=idx)
    rows = [dict(symbol="AA", date="2026-11-02", entry=100.0, stop=90.0, target=120.0, until="2026-11-30", status="open",
                 exit_date=None, exit_price=None, net_ret=None, spy_entry=500.0),
            dict(symbol="AA", date="2026-11-02", entry=100.0, stop=90.0, target=120.0, until="2026-11-30", status="target",
                 exit_date="2026-11-04", exit_price=108.0, net_ret=0.07, spy_entry=500.0)]
    out = record(rows, closes)
    assert out[0]["now"] == 110.0 and out[0]["ret"] == net_return(100.0, 110.0) and out[0]["voo_ret"] == pytest.approx(0.03)
    assert out[1]["ret"] == 0.07 and out[1]["voo_ret"] == pytest.approx(0.02)
