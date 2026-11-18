import json

import numpy as np
import pandas as pd

from market_skew import scan, store, swing_run


def payload():
    rows = [{"date": f"2026-01-{i + 1:02d}", "q10": 90, "q50": 100, "q90": 110} for i in range(21)]
    return json.dumps({"last": "2026-01-01", "forecast": rows,
                       "backtest": {"mae": {"model": 1.0, "naive": 2.0}, "coverage_10_90": 0.8}})


def long_frame(symbols, n=300):
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame({s: np.linspace(100, 120, n) for s in symbols}, index=idx)


def test_predict_fetches_two_years_for_the_on_screen_names_only(monkeypatch):
    monkeypatch.setattr(scan, "write_status", lambda **kw: None)
    asked = {}

    def fetch(symbols, period):
        asked.update(symbols=list(symbols), period=period)
        return long_frame(symbols), None
    short = long_frame(["QQQ"], 80)  # the scan's 4-month frame is too short for a forecast
    body = {"swing": [{"symbol": "KO"}, {"symbol": "SW"}]}
    out = scan._predict(body, short, "2026-11-18", fetch=fetch, runner=lambda path: payload())
    assert asked["period"] == "2y" and {"QQQ", "SCHD", "VOO", "VOOG", "KO", "SW"} <= set(asked["symbols"])
    assert "KO" in out and "QQQ" in out


def test_swing_update_backfills_missing_voo_entry(tmp_path):
    closes = long_frame(["VOO"], 40)
    with store.connect(tmp_path / "t.db") as conn:
        conn.execute("INSERT INTO swing_paper VALUES ('AA', '2025-01-10', 10, 9, 12, '2025-02-07', 'open', NULL, NULL, NULL, NULL)")
        swing_run.update(conn, "2025-01-20", [], closes)
        assert store.swing_rows(conn)[0]["spy_entry"] == float(closes["VOO"].loc["2025-01-10"])


def test_breaking_step_runs_for_on_screen_names_and_never_fails_the_scan(tmp_path, monkeypatch, capsys):
    from market_skew import breaking_run
    from tests.test_sentinel import metrics, peers, px
    from market_skew import sentinel
    monkeypatch.setattr(scan, "write_status", lambda **kw: None)
    f, p = peers()
    f["ACME"], p["ACME"] = metrics(), px()
    seen = []
    with store.connect(tmp_path / "t.db") as conn:
        store.save_sentinel(conn, "2026-11-18", sentinel.score_all(f, p))
        monkeypatch.setattr(breaking_run, "run", lambda c, rows, names, **k: seen.append(names) or {"asked": 1, "cached": 0, "failed": 0})
        monkeypatch.setattr(breaking_run.holdings, "excluded", lambda: set())
        monkeypatch.setattr(breaking_run.holdings, "load", lambda: [])
        scan._breaking(conn, {"swing": [{"symbol": "ACME"}]}, "2026-11-18")
        assert seen[0][0] == "ACME" and len(seen[0]) == len(set(seen[0]))  # picks first, then the Board's WATCH names
        monkeypatch.setattr(breaking_run, "run", lambda *a, **k: 1 / 0)
        scan._breaking(conn, {"swing": []}, "2026-11-18")  # must not raise
    assert "counter-argument step skipped" in capsys.readouterr().out


def test_levels_survive_a_failure_reading_the_holdings(monkeypatch):
    monkeypatch.setattr(scan, "write_status", lambda **kw: None)
    from market_skew import holdings, prediction
    monkeypatch.setattr(holdings, "load", lambda: 1 / 0)
    body = {"swing": [{"symbol": "KO"}]}
    out = scan._predict(body, long_frame(["QQQ"], 80), "2026-11-18", fetch=lambda s, period: (long_frame(s), None), runner=lambda path: payload())
    assert "KO" in body["levels"] and "KO" in out


def test_levels_survive_a_failed_forecast(monkeypatch):
    monkeypatch.setattr(scan, "write_status", lambda **kw: None)
    from market_skew import prediction
    monkeypatch.setattr(prediction, "forecast_many", lambda *a, **k: 1 / 0)
    body = {"swing": [{"symbol": "KO"}]}
    assert scan._predict(body, long_frame(["QQQ"], 80), "2026-11-18", fetch=lambda s, period: (long_frame(s), None)) == {}
    assert "KO" in body["levels"]


def test_earnings_are_fetched_before_the_final_selection(monkeypatch):
    from market_skew import breaking_run, earnings
    monkeypatch.setattr(scan, "write_status", lambda **kw: None)
    order = []

    def select(conn, body, scored, date):
        order.append("select")
        body["swing"] = [{"symbol": "KO"}]
    monkeypatch.setattr(scan, "_select", select)
    monkeypatch.setattr(scan, "_breaking", lambda *a: order.append("breaking"))
    monkeypatch.setattr(scan.store, "sentinel", lambda c, d: (d, []))
    monkeypatch.setattr(breaking_run, "on_screen", lambda body, rows: [p["symbol"] for p in body["swing"]])
    monkeypatch.setattr(earnings, "refresh", lambda names, **k: order.append("earn:" + ",".join(names)) or {})
    monkeypatch.setattr(scan.prediction, "screen_symbols", lambda body: [p["symbol"] for p in body["swing"]])
    scan._screened(None, {"swing": []}, None, "2026-11-18")
    assert order[0] == "select" and "select" in order[order.index("earn:KO") + 1:]  # re-chosen after the dates arrive
    assert order[-1] == "select" and order.count("earn:KO") == 1
