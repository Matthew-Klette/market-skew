import pandas as pd

from market_skew import closest, gate, selection
from market_skew.ui import swing_view, views

BODY = {"date": "2026-11-18", "sectors": [], "indexes": {"SPY": {"ret_1m": 0.01}, "VIX": {"ret_1d": 0.0}}}


def entry(score, raw=None, checked=True, why=None, thin=False):
    return {"score": score, "raw": raw or score, "checked": checked, "thin": thin, "line": "", "why": why}


def frame(**changes):
    base = dict(bucket="Contrarian Bid", close=50.0, dvol_21=2e8, source="mid", atm=0.20, ret_1m=-0.04, ret_1d=0.01, asym=30,
                market_cap=100e9, name="Co")
    return pd.DataFrame([dict(base, symbol=s, sector=s, **changes.get(s, {})) for s in ("A", "B", "C", "D", "VOO")])


def test_steady_closest_names_the_gap_and_claudes_biggest_reason():
    short = gate.STEADY_MIN - 4
    entries = {"A": entry(short, raw=short + 20, why="heavy debt vs free cash"), "B": entry(short - 10, checked=False), "C": entry(5), "D": entry(1)}
    out = closest.steady(frame(), entries)
    assert [x["symbol"] for x in out] == ["A", "B", "C"] and "VOO" not in {x["symbol"] for x in out}
    assert out[0]["text"] == f"Quality score {short} after Claude (needs {gate.STEADY_MIN}): heavy debt vs free cash"
    assert "not yet checked by Claude" in out[1]["text"]


def test_his_way_closest_says_timing_when_sentinel_passes():
    ok = gate.HIS_WAY_MIN + 5
    entries = {s: entry(ok) for s in "ABCD"}
    out = closest.his_way(frame(A={"bucket": "Chase"}, B={"bucket": "Fear"}), entries)
    assert out[0]["text"] == "timing: not a Contrarian Bid today" and len(out) == 2
    assert closest.his_way(frame(), entries) == []  # everyone passes: nothing missed


def test_excluded_names_are_never_shown():
    entries = {s: entry(1) for s in "ABCD"}
    assert "A" not in {x["symbol"] for x in closest.steady(frame(), entries, {"A"})}


def test_choose_all_fills_near_only_for_an_empty_list_and_never_touches_the_real_lists():
    weak = {s: entry(gate.STEADY_MIN - 1) for s in "ABCD"}
    out = selection.choose_all(BODY, frame(), weak, set())
    assert out["picks"] == [] or all(p["symbol"] == "VOO" for p in out["picks"])
    assert len(out["swing_near"]) == 3 and out["swing"] == []
    strong = {s: entry(gate.HIS_WAY_MIN + 10) for s in "ABCD"}
    out = selection.choose_all(BODY, frame(), strong, set())
    assert out["swing"] and out["swing_near"] == [] and out["picks_near"] == []


def test_views_label_the_block_as_not_picks():
    items = [{"symbol": "A", "name": "Acme", "text": "timing: not a Contrarian Bid today"}]
    html = swing_view.section({"swing": [], "swing_near": items})
    assert closest.LABEL in html and "Acme" in html and f"Quality score {gate.HIS_WAY_MIN} or more" in html
    assert closest.LABEL not in swing_view.section({"swing": []})
