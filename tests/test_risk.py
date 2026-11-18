import math

import pytest

from market_skew import risk

# 20 months: one bad month, then a long slide, then a recovery
SERIES = [("2020-01", 0.02), ("2020-02", -0.04), ("2020-03", -0.20), ("2020-04", 0.10), ("2020-05", 0.05), ("2020-06", 0.04),
          ("2020-07", 0.03), ("2020-08", 0.02), ("2020-09", 0.01), ("2020-10", 0.01), ("2020-11", 0.02), ("2020-12", 0.02),
          ("2021-01", 0.01), ("2021-02", 0.01), ("2021-03", 0.01), ("2021-04", 0.01), ("2021-05", 0.01), ("2021-06", 0.01),
          ("2021-07", 0.01), ("2021-08", 0.01)]


def test_var_and_cvar_are_historical_and_scale_with_value():
    out = risk.analyse(SERIES, 100000.0)
    assert out["var"]["pct"] == pytest.approx(0.048) and out["cvar"]["pct"] == pytest.approx(0.20)
    assert out["var"]["rand"] == pytest.approx(4800.0) and out["cvar"]["rand"] == pytest.approx(20000.0)


def test_worst_month_and_worst_twelve_months_with_dates():
    out = risk.analyse(SERIES, 1000.0)
    assert out["worst_month"] == {"month": "2020-03", "pct": -0.20, "rand": -200.0}
    w = out["worst_12"]
    expect = math.prod(1 + r for _, r in SERIES[1:13]) - 1
    assert w["from"] == "2020-02" and w["to"] == "2021-01" and w["pct"] == pytest.approx(expect) and w["rand"] == pytest.approx(expect * 1000)


def test_drawdown_has_peak_trough_and_recovery():
    d = risk.analyse(SERIES, 1000.0)["drawdown"]
    assert d["peak"] == "2020-01" and d["trough"] == "2020-03" and d["depth"] == pytest.approx(1 - 0.96 * 0.8)
    assert d["recovered"] == "2020-11" and d["months_to_recover"] == 8 and d["months_underwater"] == 10


def test_unrecovered_drawdown_says_so():
    d = risk.analyse([("2020-01", 0.1), ("2020-02", -0.3), ("2020-03", 0.01)] + [(f"2020-{m:02d}", 0.0) for m in range(4, 13)], 1000.0)["drawdown"]
    assert d["recovered"] is None and d["months_to_recover"] is None and d["trough"] == "2020-02"


def test_stress_replays_a_window_on_todays_value_and_skips_missing_ones():
    out = risk.analyse(SERIES, 1000.0, windows=(("Mar 2020", "2020-03", "2020-03"), ("2022", "2022-01", "2022-10")))
    assert out["stress"][0]["label"] == "Mar 2020" and out["stress"][0]["rand"] == pytest.approx(-200.0)
    assert [s["label"] for s in out["stress"]] == ["Mar 2020"]


def test_too_short_a_history_gives_nothing():
    assert risk.analyse(SERIES[:5], 1000.0) is None
