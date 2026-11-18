import pandas as pd

from market_skew import closest, selection, swing
from market_skew.picks import choose as choose_steady
from market_skew.ui import swing_view

TODAY = "2026-11-18"
CALM = {"SPY": {"ret_1m": 0.01}, "VIX": {"ret_1d": 0.0}}


def rep(day):
    return {"kind": "stock", "next_date": day, "beats": 4, "of": 4, "avg_surprise": 2.0, "spread": "narrow"}


def test_wait_note_blocks_within_seven_days_inclusive():
    assert swing.wait_note(rep("2026-11-19"), TODAY) == "Wait until after results on 19 Nov"
    assert swing.wait_note(rep("2026-11-18"), TODAY) is not None   # today
    assert swing.wait_note(rep("2026-11-25"), TODAY) is not None   # day 7 inclusive
    assert swing.wait_note(rep("2026-11-26"), TODAY) is None
    assert swing.wait_note(rep("2026-11-10"), TODAY) is None       # already reported


def test_missing_or_fund_data_never_blocks():
    assert swing.wait_note(None, TODAY) is None
    assert swing.wait_note({"kind": "stock", "next_date": None}, TODAY) is None
    assert swing.wait_note({"kind": "fund"}, TODAY) is None


def test_steady_note_counts_days_or_says_unknown():
    assert swing.steady_note(rep("2026-11-21"), TODAY) == "Reports in 3 days"
    assert swing.steady_note(rep("2026-11-19"), TODAY) == "Reports in 1 day"
    assert swing.steady_note(rep("2026-11-18"), TODAY) == "Reports today"
    assert swing.steady_note(rep("2027-01-20"), TODAY) == "Reports in 63 days"
    assert swing.steady_note(None, TODAY) == "earnings date unknown"
    assert swing.steady_note({"kind": "fund"}, TODAY) == ""


def _scored():
    base = dict(bucket="Contrarian Bid", close=50.0, dvol_21=2e8, source="mid", atm=0.20, ret_1m=-0.08, ret_1d=0.01,
                asym=30, name="Co", market_cap=100e9)
    return pd.DataFrame([dict(base, symbol="ROST", sector="Cons Disc", asym=40), dict(base, symbol="OK", sector="Energy")])


def test_swing_skips_names_reporting_this_week_and_labels_unknown():
    data = {"ROST": rep("2026-11-19")}
    trades = swing.choose(_scored(), {}, CALM, TODAY, set(), earnings=data)
    assert [t.symbol for t in trades] == ["OK"] and trades[0].earnings == "earnings date unknown"
    assert [t.symbol for t in swing.choose(_scored(), {}, CALM, TODAY, set())] == ["ROST", "OK"]  # no data given: no rule


def test_steady_keeps_the_pick_with_a_note():
    got = choose_steady(_scored().assign(bucket="Chase"), {}, earnings={"ROST": rep("2026-11-19")}, today=TODAY)
    notes = {p.symbol: p.earnings_note for p in got}
    assert notes == {"ROST": "Reports in 1 day", "OK": "earnings date unknown"}


def test_closest_his_way_names_the_wait_reason():
    entries = {s: {"score": 90, "raw": 90, "checked": True, "thin": False, "line": "", "why": None} for s in ("ROST", "OK")}
    out = closest.his_way(_scored(), entries, earnings={"ROST": rep("2026-11-19")}, today=TODAY)
    assert [x["symbol"] for x in out] == ["ROST"] and out[0]["text"] == "Wait until after results on 19 Nov"


def test_choose_all_moves_rost_to_the_closest_list():
    entries = {s: {"score": 90, "raw": 90, "checked": True, "thin": False, "line": "", "why": None} for s in ("ROST", "OK")}
    body = {"date": TODAY, "sectors": [], "indexes": CALM}
    out = selection.choose_all(body, _scored(), entries, set(), earnings={"ROST": rep("2026-11-19")})
    assert [t["symbol"] for t in out["swing"]] == ["OK"]


def test_card_shows_unknown_label_escaped():
    html = swing_view.earnings_note("<b>x</b>")
    assert "&lt;b&gt;" in html and swing_view.earnings_note("") == ""
