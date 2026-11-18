import numpy as np
import pandas as pd

from market_skew import levels_run


def frame():
    idx = pd.bdate_range("2025-01-01", periods=400)
    return pd.DataFrame({"AAA": np.linspace(100, 150, 400), "SHORT": [np.nan] * 350 + list(np.linspace(10, 11, 50))}, index=idx)


def test_build_keeps_a_year_of_closes_and_skips_short_history():
    out = levels_run.build(["AAA", "SHORT", "MISSING"], frame())
    assert set(out) == {"AAA"}
    assert len(out["AAA"]["closes"]) == 252 and out["AAA"]["last"] == 150.0
    assert out["AAA"]["levels"] == [] and out["AAA"]["end"] > out["AAA"]["start"]


def test_build_without_closes_is_empty():
    assert levels_run.build(["AAA"], None) == {}
