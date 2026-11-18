import pytest
import pandas as pd

from market_skew import narrative

IDX = {k: {"ret_1d": 0.01, "ret_1m": 0.04, "ret_1w": 0.01} for k in ("SPY", "QQQ", "IWM")}


def _themes():
    return pd.DataFrame([
        dict(name="Gold", rel_1m=0.27, rel_1w=0.03, today=0.02, trend="improving", breadth=1.0, flow_bps=9, leaders=["NEM", "HL"]),
        dict(name="Software", rel_1m=0.14, rel_1w=-0.03, today=-0.02, trend="fading", breadth=0.84, flow_bps=120, leaders=["MSFT"]),
        dict(name="GLP1", rel_1m=-0.08, rel_1w=-0.01, today=0.0, trend="fading", breadth=0.2, flow_bps=-5, leaders=["LLY"]),
    ])


def test_tape_calls_risk_on_when_all_up_and_vix_down():
    idx = dict(IDX, VIX={"ret_1d": -0.05})
    assert "risk-on" in narrative.tape(idx)


def test_tape_is_mixed_when_indexes_disagree_and_vix_calm():
    idx = dict(IDX, IWM={"ret_1d": -0.003, "ret_1m": 0.0}, VIX={"ret_1d": 0.007})
    assert "mixed, no strong signal" in narrative.tape(idx)


def test_strongest_theme_names_breadth_and_leaders():
    line = narrative.strongest_theme(_themes())
    assert "Gold" in line and "+27.0%" in line and "healthy" in line and "NEM" in line


def test_fading_leader_and_laggard_are_found():
    assert "Software" in narrative.leader_fading(_themes())
    assert narrative.leader_fading(_themes().iloc[1:].reset_index(drop=True)) is None  # never repeats the strongest
    assert "penalty box" in narrative.laggard(_themes())


def test_caution_prefers_watchlist_names():
    scored = pd.DataFrame([
        dict(symbol="IONQ", bucket="Hedged Rally", ret_1m=0.3, skew=0.54, dvol_21=1e8),
        dict(symbol="BIG", bucket="Hedged Rally", ret_1m=0.1, skew=0.60, dvol_21=1e10),
    ])
    assert "IONQ" in narrative.caution(scored, {"IONQ"})
    assert "BIG" in narrative.caution(scored, set())


def test_strongest_theme_admits_when_nothing_beats_spy():
    themes = _themes().assign(rel_1m=[-0.01, -0.02, -0.03])
    assert "No theme beat SPY" in narrative.strongest_theme(themes)


def test_market_open_follows_new_york_hours():
    import datetime as dt
    from market_skew.scan import market_open
    utc = dt.timezone.utc
    assert market_open(dt.datetime(2026, 11, 18, 15, 54, tzinfo=utc))       # 10:54 New York, Wednesday
    assert not market_open(dt.datetime(2026, 11, 18, 21, 15, tzinfo=utc))   # 16:15 New York
    assert not market_open(dt.datetime(2026, 11, 21, 15, 0, tzinfo=utc))    # Saturday


def test_scan_on_open_once_per_new_york_close():
    import datetime as dt
    from market_skew.scan import is_stale, last_close
    utc = dt.timezone.utc
    sa_evening = dt.datetime(2026, 11, 18, 19, 0, tzinfo=utc)       # 21:00 SAST Wed, New York still trading
    after_close = dt.datetime(2026, 11, 18, 21, 30, tzinfo=utc)     # 23:30 SAST Wed, New York closed
    assert last_close(sa_evening) == dt.date(2026, 11, 17)
    assert last_close(after_close) == dt.date(2026, 11, 18)
    assert last_close(dt.datetime(2026, 11, 22, 15, 0, tzinfo=utc)) == dt.date(2026, 11, 20)  # Sunday -> Friday
    built_tue_night = {"date": "2026-11-17", "covers": "2026-11-17"}
    assert not is_stale(built_tue_night, sa_evening)     # reopening Wednesday evening: no scan
    assert is_stale(built_tue_night, after_close)        # first open after Wednesday's close: scan
    assert not is_stale({"date": "2026-11-26", "covers": "2026-11-27"}, dt.datetime(2026, 11, 28, 15, 0, tzinfo=utc))  # holiday: once
    assert is_stale(None)


def _sectors(rels):
    return pd.DataFrame([dict(name=f"S{i}", rel_1m=r, flow_bps=1.0) for i, r in enumerate(rels)])


def _idx(spy, rsp, off_high=None):
    spy_row = {"ret_1m": spy, **({"off_high": off_high} if off_high is not None else {})}
    return {"SPY": spy_row, "RSP": {"ret_1m": rsp}}


def test_rotation_says_gains_are_narrow_when_spy_beats_equal_weight_by_two_points():
    line = narrative.rotation_read(_idx(0.05, 0.02), _sectors([0.01] * 3 + [-0.01] * 8))
    assert "The S&P is up 5.0% on the month while the average stock is up 2.0%: gains are narrow, money is rotating" in line
    assert "3 of 11 sectors beat SPY this month" in line


def test_rotation_reverse_wording_when_equal_weight_leads():
    line = narrative.rotation_read(_idx(0.01, 0.04), _sectors([0.01] * 11))
    assert "The average stock is up 4.0% on the month while the S&P is up 1.0%" in line and "broad market" in line and "narrow" not in line
    assert "11 of 11 sectors beat SPY" in line


def test_rotation_is_silent_on_the_gap_within_two_points_but_still_counts_sectors():
    line = narrative.rotation_read(_idx(0.03, 0.02), _sectors([0.01, -0.01]))
    assert "narrow" not in line and "broad" not in line and "1 of 2 sectors beat SPY" in line


def test_rotation_adds_distance_from_52_week_high_only_when_known():
    assert "3.4% below its 52-week high" in narrative.rotation_read(_idx(0.03, 0.03, -0.034), _sectors([]))
    assert "at its 52-week high" in narrative.rotation_read(_idx(0.03, 0.03, 0.0), _sectors([]))
    assert narrative.rotation_read(_idx(0.03, 0.03), _sectors([])) is None
    assert narrative.rotation_read({"SPY": {"ret_1m": 0.03}}, _sectors([])) is None  # no RSP: no gap sentence


def test_off_high_is_distance_below_the_highest_close():
    closes = pd.Series([100.0, 120.0, 108.0])
    assert narrative.off_high(closes) == pytest.approx(-0.10)
    assert narrative.off_high(pd.Series([], dtype=float)) is None


def test_todays_read_puts_rotation_after_the_tape():
    idx = dict(IDX, SPY=dict(IDX["SPY"], ret_1m=0.06), RSP={"ret_1m": 0.01}, VIX={"ret_1d": 0.0})
    scored = pd.DataFrame(columns=["symbol", "bucket"])
    lines = narrative.todays_read(idx, _themes(), _sectors([0.01] * 4), scored, set())
    assert lines[0].startswith("The tape") and "narrow" in lines[1]


def test_rotation_says_down_when_the_month_is_negative():
    line = narrative.rotation_read(_idx(-0.044, 0.011), _sectors([]))
    assert "average stock is up 1.1%" in line and "S&P is down 4.4%" in line


def test_rotation_separates_sectors_up_outright_from_sectors_beating_spy():
    # SPY is down 4%: a sector 2 points ahead of SPY is still down 2% outright
    line = narrative.rotation_read(_idx(-0.04, -0.04), _sectors([0.02] * 3 + [0.06] * 2 + [-0.01] * 6))
    assert "5 of 11 sectors beat SPY this month, and 2 of 11 are up outright" in line
    assert line.count("of 11") == 2


def test_rotation_leaves_out_the_outright_count_without_a_spy_return():
    line = narrative.rotation_read({}, _sectors([0.01, -0.01]))
    assert "1 of 2 sectors beat SPY this month." in line and "outright" not in line
