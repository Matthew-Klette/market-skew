from types import SimpleNamespace

from market_skew import funds


def sig(skew, ret, spy_ret=0.0, hist=None, spy_skew=0.10):
    return funds.signal("QQQ", skew, ret, 500.0, spy_ret, hist, spy_skew)


def test_dip_with_bullish_bets_is_good_time_to_add():
    s = sig(skew=0.05, ret=-0.04)
    assert s["bucket"] == "Contrarian Bid" and s["timing"] == "add" and s["label"] == "Good time to add"


def test_falling_with_bearish_bets_is_hold():
    assert sig(skew=0.20, ret=-0.04)["timing"] == "hold"


def test_rising_with_bullish_bets_is_chase_wait():
    assert sig(skew=0.05, ret=0.04)["bucket"] == "Chase"


def test_rising_with_bearish_bets_is_hedged_rally_hold():
    assert sig(skew=0.20, ret=0.04)["bucket"] == "Hedged Rally"


def test_own_history_beats_spy_baseline():
    s = sig(skew=0.12, ret=-0.04, hist=[0.20, 0.20], spy_skew=0.01)
    assert s["basis"] == "its own last readings" and s["bucket"] == "Contrarian Bid"


def test_tie_with_spy_uses_own_sign():
    assert sig(skew=0.05, ret=-0.01, spy_ret=-0.0095)["bucket"] == "Contrarian Bid"


def test_no_baseline_or_skew_gives_none():
    assert sig(skew=0.1, ret=0.0, spy_skew=None) is None
    assert funds.signal("QQQ", None, 0, 1, 0, None, 0.1) is None


def test_build_skips_funds_without_reading_and_needs_spy():
    r = lambda s: SimpleNamespace(skew=s)
    stats = {"SPY": {"close": 600, "ret_1m": 0.0}, "QQQ": {"close": 500, "ret_1m": -0.03}, "VOO": {"close": 550, "ret_1m": 0.0}}
    out = funds.build({"SPY": r(0.1), "QQQ": r(0.05), "VOO": None}, stats, {})
    assert list(out) == ["QQQ"] and out["QQQ"]["timing"] == "add"
    assert funds.build({"QQQ": r(0.05)}, stats, {}) == {}


def test_history_from_reports_and_holding_row():
    h = funds.history_from([{"funds": {"QQQ": {"skew": 0.1}}}, {}, {"funds": {"QQQ": {"skew": 0.2}}}])
    assert h == {"QQQ": [0.1, 0.2]}
    row = funds.as_holding("QQQ", sig(0.05, -0.04))
    assert row["light"] == "add" and row["price"] == 500.0
