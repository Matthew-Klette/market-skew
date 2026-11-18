import datetime as dt

import numpy as np
import pandas as pd

from market_skew import sentinel_run, store
from tests.test_sentinel import metrics


def frames(symbols, n=100):
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame({s: np.linspace(100, 130, n) for s in symbols}, index=idx)


def scored(symbols):
    return pd.DataFrame([{"symbol": s, "name": f"Co {s}", "sector": "Info Tech", "market_cap": 5000.0, "close": 50.0,
                          "ret_1m": 0.02, "bet_z": 0.5, "bucket": "Chase"} for s in symbols])


def seed(conn, symbols):
    store.save_fundamentals(conn, [(s, "1", "2025Q4", __import__("json").dumps(metrics())) for s in symbols])


def test_three_month_return_needs_enough_history():
    assert sentinel_run.three_month_returns(frames(["A"], 40)) == {}
    r = sentinel_run.three_month_returns(frames(["A"], 100))
    assert round(r["A"], 3) == round(130 / (100 + 30 * 36 / 99) - 1, 3)


def test_year_closes_keep_completed_years_and_cache_for_a_week(tmp_path):
    idx = pd.to_datetime(["2023-06-01", "2023-12-29", "2024-12-31", "2025-06-02"])
    calls = []

    def fetch(symbols, period):
        calls.append(period)
        return pd.DataFrame({"A": [1.0, 2.0, 3.0, 4.0]}, index=idx), None
    path = tmp_path / "y.json"
    out = sentinel_run.year_closes(["A"], dt.date(2025, 6, 3), fetch, path)
    assert out == {"A": {"2023": 2.0, "2024": 3.0}}
    sentinel_run.year_closes(["A"], dt.date(2025, 6, 5), fetch, path)
    assert len(calls) == 1


def test_refresh_scores_and_stores_then_next_run_shows_change(tmp_path):
    symbols = [f"S{i}" for i in range(6)]
    fetch = lambda s, period: (frames(s, 1600), None)
    with store.connect(tmp_path / "t.db") as conn:
        seed(conn, symbols)
        n = sentinel_run.refresh(conn, "2026-11-17", scored(symbols), frames(symbols), dt.date(2026, 11, 17), fetch, tmp_path / "y.json")
        assert n == 6
        sentinel_run.refresh(conn, "2026-11-18", scored(symbols), frames(symbols), dt.date(2026, 11, 18), fetch, tmp_path / "y.json")
        date, rows = store.sentinel(conn)
        assert date == "2026-11-18" and len(rows) == 6 and rows[0]["change"] == 0
        assert store.sentinel(conn, "2026-11-17")[0] == "2026-11-17"


def test_no_company_numbers_means_no_rows(tmp_path):
    with store.connect(tmp_path / "t.db") as conn:
        assert sentinel_run.refresh(conn, "2026-11-18", scored(["A"]), frames(["A"]), dt.date(2026, 11, 18), None, tmp_path / "y.json") == 0
        assert store.sentinel(conn) == (None, [])


def test_history_failure_only_drops_the_history_check(tmp_path):
    def boom(s, period):
        raise RuntimeError("yahoo down")
    with store.connect(tmp_path / "t.db") as conn:
        seed(conn, ["A", "B"])
        assert sentinel_run.refresh(conn, "2026-11-18", scored(["A", "B"]), frames(["A", "B"]), dt.date(2026, 11, 18), boom, tmp_path / "y.json") == 2
        assert store.sentinel(conn)[1][0]["own_history_pct"] is None


def test_recompute_uses_stored_price_inputs(tmp_path):
    with store.connect(tmp_path / "t.db") as conn:
        seed(conn, ["A", "B"])
        store.save_report(conn, "2026-11-18", "x", {"date": "2026-11-18", "stocks": []})
        sentinel_run.refresh(conn, "2026-11-18", scored(["A", "B"]), frames(["A", "B"]), dt.date(2026, 11, 18), lambda s, period: (frames(s, 1600), None), tmp_path / "y.json")
        assert sentinel_run.recompute(conn) == ("2026-11-18", 2)
        assert store.sentinel(conn)[1][0]["name"].startswith("Co ")


def _long_frame(symbols, n=600):
    idx = pd.bdate_range("2023-01-02", periods=n)
    rng = np.random.default_rng(3)
    spy = rng.normal(0.0004, 0.01, n)
    cols = {"SPY": 100 * np.cumprod(1 + spy)}
    for i, s in enumerate(symbols):
        cols[s] = 100 * np.cumprod(1 + spy * (1.2 if s == "A" else 0.8) + rng.normal(0, 0.002, n))
    return pd.DataFrame(cols, index=idx)


def test_year_closes_fetches_only_missing_symbols_and_merges(tmp_path):
    calls = []

    def fetch(symbols, period):
        calls.append(list(symbols))
        return _long_frame([s for s in symbols if s != "SPY"]), None
    path = tmp_path / "y.json"
    sentinel_run.year_closes(["A"], dt.date(2026, 11, 18), fetch, path)
    out = sentinel_run.year_closes(["A", "B"], dt.date(2026, 11, 19), fetch, path)
    assert "B" in calls[1] and "A" not in calls[1]
    assert set(out) >= {"A", "B"} and out["A"]
    assert len(calls) == 2
    sentinel_run.year_closes(["A", "B"], dt.date(2026, 11, 20), fetch, path)
    assert len(calls) == 2


def test_year_closes_refreshes_everything_after_a_week(tmp_path):
    calls = []

    def fetch(symbols, period):
        calls.append(list(symbols))
        return _long_frame([s for s in symbols if s != "SPY"]), None
    path = tmp_path / "y.json"
    sentinel_run.year_closes(["A", "B"], dt.date(2026, 11, 1), fetch, path)
    sentinel_run.year_closes(["A", "B"], dt.date(2026, 11, 9), fetch, path)
    assert len(calls) == 2 and {"A", "B"} <= set(calls[1])


def test_betas_are_measured_against_spy_saved_and_used_in_value(tmp_path):
    path = tmp_path / "y.json"
    sentinel_run.year_closes(["A", "B"], dt.date(2026, 11, 18), lambda s, period: (_long_frame([x for x in s if x != "SPY"]), None), path)
    betas = sentinel_run.saved_betas(path)
    assert 0.6 <= betas["B"] < betas["A"] <= 1.6
    rows = [{"symbol": "A", "metrics": metrics(), "px": {"close": 50.0}, "sector": "Info Tech"}]
    assert sentinel_run.with_values(rows, betas)[0]["value"]["beta"] == betas["A"]
    assert sentinel_run.with_values(rows, {})[0]["value"]["beta"] == 1.0


def test_value_rows_without_a_spy_frame_get_no_beta(tmp_path):
    path = tmp_path / "y.json"
    sentinel_run.year_closes(["A"], dt.date(2026, 11, 18), lambda s, period: (_long_frame(["A"]).drop(columns="SPY"), None), path)
    assert sentinel_run.saved_betas(path) == {}
