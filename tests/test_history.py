import pandas as pd
import pytest

from market_skew import history


def months(start: str, n: int) -> list[str]:
    return [str(p) for p in pd.period_range(start, periods=n, freq="M")]


def test_month_levels_drop_the_current_partial_month():
    idx = pd.to_datetime(["2026-09-01", "2026-10-01", "2026-11-01"])
    out = history.month_levels(pd.Series([1.0, 2.0, 3.0], index=idx), "2026-11-18")
    assert out == {"2026-09": 1.0, "2026-10": 2.0}


def test_usd_funds_are_measured_in_rand_and_jse_in_rand_already():
    m = months("2026-01", 3)
    levels = {"VOO": dict(zip(m, [100.0, 110.0, 110.0])), "USDZAR": dict(zip(m, [18.0, 18.0, 19.8])),
              "SYG500": dict(zip(m, [50.0, 55.0, 55.0]))}
    r = history.rand_returns(levels)
    assert r["VOO"]["2026-02"] == pytest.approx(0.10) and r["VOO"]["2026-03"] == pytest.approx(0.10)  # fund flat, rand weaker
    assert r["SYG500"]["2026-02"] == pytest.approx(0.10) and r["SYG500"]["2026-03"] == pytest.approx(0.0)


def test_a_gap_month_gives_no_return_for_the_month_after_it():
    levels = {"SYG500": {"2026-01": 1.0, "2026-03": 1.2, "2026-04": 1.32}}
    assert history.rand_returns(levels)["SYG500"] == {"2026-04": pytest.approx(0.10)}


def test_young_jse_fund_borrows_voo_in_rand_and_says_so():
    returns = {"VOO": {"2026-01": 0.01, "2026-02": 0.02, "2026-03": 0.03}, "QQQ": {"2026-01": 0.0, "2026-02": 0.0, "2026-03": 0.0},
               "SYG500": {"2026-03": 0.05}}
    filled, notes = history.with_proxies(returns)
    assert filled["SYG500"] == {"2026-01": 0.01, "2026-02": 0.02, "2026-03": 0.05}
    assert notes["SYG500"] == {"proxy": "VOO", "months": 2, "from": "2026-03"}


def test_refresh_keeps_a_fresh_cache_and_survives_a_failing_symbol(tmp_path):
    calls = []

    def fetcher(name):
        calls.append(name)
        if name == "QQQ":
            raise OSError("down")
        return {"2026-01": 1.0}
    out = history.refresh(tmp_path, today="2026-11-18", fetcher=fetcher, now=1000.0)
    assert "QQQ" not in out["levels"] and out["levels"]["VOO"] == {"2026-01": 1.0}
    calls.clear()
    history.refresh(tmp_path, today="2026-11-19", fetcher=fetcher, now=1001.0)  # same week: nothing refetched
    assert calls == []
    assert history.cached(tmp_path)["levels"]["VOO"] == {"2026-01": 1.0}


def test_refresh_force_refetches(tmp_path):
    n = []
    history.refresh(tmp_path, today="2026-11-18", fetcher=lambda s: n.append(s) or {"2026-01": 1.0}, now=1.0)
    history.refresh(tmp_path, today="2026-11-18", fetcher=lambda s: n.append(s) or {"2026-01": 1.0}, now=1.0, force=True)
    assert len(n) == 2 * len(history.NAMES)
