import numpy as np
import pandas as pd

from market_skew import levels


def series(values):
    return pd.Series(values, index=pd.bdate_range("2025-11-01", periods=len(values)))


def test_nice_rounding_by_scale():
    assert levels.nice(172.4) == 170
    assert levels.nice(523) == 525
    assert levels.nice(268) == 270
    assert levels.nice(8.4) == 8
    assert levels.nice(37.2) == 38


def test_floor_revisited_is_found_and_rounded():
    closes = np.concatenate([np.linspace(160, 200, 40), np.linspace(200, 150.5, 30), np.linspace(150.5, 190, 30),
                             np.linspace(190, 151.2, 30), np.linspace(151.2, 200, 40), np.linspace(200, 188, 80)])
    found = levels.find(series(closes))
    assert found and found[0]["kind"] == "floor"
    assert found[0]["level"] == 150 and found[0]["touches"] >= 2
    assert 18 < found[0]["distance_pct"] < 24


def test_returns_at_most_two_sorted_high_to_low():
    closes = np.concatenate([np.linspace(100, 70, 30), np.linspace(70, 100, 30), np.linspace(100, 71, 30), np.linspace(71, 100, 30),
                             np.linspace(100, 85, 30), np.linspace(85, 100, 30), np.linspace(100, 86, 30), np.linspace(86, 100, 30),
                             np.linspace(100, 120, 20)])
    found = levels.find(series(closes))
    assert 1 <= len(found) <= 2
    assert [x["level"] for x in found] == sorted((x["level"] for x in found), reverse=True)


def test_floor_too_close_to_price_is_ignored():
    closes = np.concatenate([np.linspace(100, 98, 60), np.linspace(98, 101, 60), np.linspace(101, 98.1, 60), np.linspace(98.1, 100, 70)])
    assert levels.find(series(closes)) == []


def test_floor_too_deep_is_ignored():
    closes = np.concatenate([np.linspace(60, 20, 30), np.linspace(20, 60, 30), np.linspace(60, 20.5, 30), np.linspace(20.5, 60, 30),
                             np.linspace(60, 100, 130)])
    assert levels.find(series(closes)) == []


def test_single_touch_is_not_a_floor():
    closes = np.concatenate([np.linspace(100, 80, 100), np.linspace(80, 130, 150)])
    assert levels.find(series(closes)) == []


def test_short_history_returns_nothing():
    assert levels.find(series(np.linspace(100, 90, 50))) == []
    assert levels.find(None) == []


def test_input_not_mutated():
    s = series(np.linspace(100, 120, 200))
    before = s.copy()
    levels.find(s)
    pd.testing.assert_series_equal(s, before)


def test_add_on_rule():
    assert levels.next_add(100.0) == 95.0
    assert levels.next_add(None) is None
    assert levels.next_add(-3) is None
