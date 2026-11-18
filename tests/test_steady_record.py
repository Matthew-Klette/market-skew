import pandas as pd
import pytest

from market_skew import costs, recommend_run, steady_record, store

IDX = pd.bdate_range("2026-10-01", periods=40)
VOO = pd.Series([500 + i for i in range(40)], index=IDX, dtype=float)


def test_net_return_takes_off_rand_conversion_and_buy_fee_only():
    flat = steady_record.net_return(100.0, 100.0)
    assert flat == pytest.approx((1 - costs.RATES["fx_convert"]) * (1 - costs.RATES["usd_buy"]) - 1)
    assert -0.0190 < flat < -0.0180


def test_record_compares_with_voo_and_marks_settled_after_a_month():
    rows = [dict(symbol="KO", date="2026-10-01", entry=100.0, spy_entry=600.0, voo_entry=500.0),
            dict(symbol="PG", date="2026-11-10", entry=50.0, spy_entry=600.0, voo_entry=None)]
    out = steady_record.record(rows, {"KO": 110.0, "PG": 50.0}, VOO, "2026-11-18")
    assert out[0]["voo_ret"] == pytest.approx(VOO.loc["2026-11-18"] / 500 - 1)
    assert out[0]["ret"] == pytest.approx(steady_record.net_return(100, 110))
    assert out[0]["settled"] and not out[1]["settled"]
    assert out[1]["voo_ret"] == pytest.approx(VOO.loc["2026-11-18"] / VOO.loc["2026-11-10"] - 1)


def test_record_without_prices_or_voo_gives_none():
    out = steady_record.record([dict(symbol="KO", date="2026-10-01", entry=100.0, spy_entry=1, voo_entry=None)], {}, None, "2026-11-18")
    assert out[0]["ret"] is None and out[0]["voo_ret"] is None


def test_old_database_gets_the_voo_column_and_lazy_fill(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE paper (symbol TEXT PRIMARY KEY, date TEXT, entry REAL, spy_entry REAL)")
    old.execute("INSERT INTO paper VALUES ('KO', '2026-10-01', 60.0, 600.0)")
    old.commit(); old.close()
    with store.connect(path) as conn:
        rows = store.paper_rows(conn)
        assert rows[0]["voo_entry"] is None and rows[0]["spy_entry"] == 600.0
        filled = recommend_run.fill_voo_entries(conn, rows, VOO)
        assert filled[0]["voo_entry"] == 500.0
        assert store.paper_rows(conn)[0]["voo_entry"] == 500.0


def test_enrich_adds_paper_and_recommendation(tmp_path):
    with store.connect(tmp_path / "t.db") as conn:
        conn.execute("INSERT INTO paper (symbol, date, entry, spy_entry) VALUES ('KO', '2026-10-01', 100.0, 600.0)")
        conn.execute("INSERT INTO stocks (date, symbol, close) VALUES ('2026-11-18', 'KO', 105.0)")
        report = {"date": "2026-11-18", "indexes": {}, "read": ["The tape: x → mixed."], "swing_record": []}
        out = recommend_run.enrich(conn, report, voo=VOO)
    assert out["paper"][0]["now"] == 105.0 and out["paper"][0]["voo_ret"] is not None
    assert out["recommendation"]["lens"] == "mine" and "Not enough evidence" in out["recommendation"]["reason"]


def test_mood_reads_indexes_and_tape():
    m = recommend_run.mood({"indexes": {"SPY": {"ret_1m": -0.06}, "VIX": {"ret_1d": 0.07}}, "read": ["The tape: → risk-off: x"]})
    assert m == {"spy_1m": -0.06, "vix_1d": 0.07, "risk_off": True}


def test_settled_pick_is_frozen_at_its_day_28_close():
    idx = pd.bdate_range("2026-10-01", periods=40)
    closes = pd.DataFrame({"KO": [100 + i for i in range(40)]}, index=idx, dtype=float)
    row = dict(symbol="KO", date="2026-10-01", entry=100.0, spy_entry=1, voo_entry=500.0, exit_close=None, voo_exit=None)
    (symbol, pick, compare), = steady_record.freezes([row], closes, VOO, "2026-11-18")
    assert symbol == "KO" and pick == closes["KO"].loc["2026-10-29"] and compare == VOO.loc["2026-10-29"]
    frozen = dict(row, exit_close=pick, voo_exit=compare)
    out = steady_record.record([frozen], {"KO": 500.0}, VOO, "2026-11-18")  # the live price no longer matters
    assert out[0]["now"] == pick and out[0]["ret"] == pytest.approx(steady_record.net_return(100, pick))
    assert out[0]["voo_ret"] == pytest.approx(compare / 500.0 - 1)
    assert steady_record.freezes([frozen], closes, VOO, "2026-11-18") == []


def test_unsettled_or_not_yet_covered_picks_are_not_frozen():
    short = pd.DataFrame({"KO": [100.0] * 10}, index=pd.bdate_range("2026-10-01", periods=10))
    row = dict(symbol="KO", date="2026-10-01", entry=100.0, voo_entry=500.0, exit_close=None, voo_exit=None)
    assert steady_record.freezes([row], short, None, "2026-11-18") == []   # data stops before day 28
    assert steady_record.freezes([dict(row, date="2026-11-10")], short, None, "2026-11-18") == []   # only 8 days old


def test_voo_cache_is_read_only_for_the_page_and_filled_by_refresh(tmp_path):
    path = tmp_path / "voo.json"
    assert recommend_run.voo_closes(path) is None
    calls = []
    def fetch(symbols, period):
        calls.append(period)
        return pd.DataFrame({"VOO": VOO}), None
    got = recommend_run.refresh_voo("2026-11-18", path, fetch, now=0.0)
    assert got is not None and recommend_run.voo_closes(path).iloc[-1] == VOO.iloc[-1]
    recommend_run.refresh_voo("2026-11-18", path, fetch, now=1.0)
    assert len(calls) == 1


def test_failed_voo_fetch_backs_off_and_keeps_old_closes(tmp_path):
    path = tmp_path / "voo.json"
    recommend_run.refresh_voo("2026-11-17", path, lambda s, period: (pd.DataFrame({"VOO": VOO}), None), now=0.0)
    calls = []
    def boom(symbols, period):
        calls.append(1)
        raise OSError("offline")
    old = recommend_run.refresh_voo("2099-01-01", path, boom, now=10.0)
    recommend_run.refresh_voo("2099-01-01", path, boom, now=20.0)
    assert len(calls) == 1 and old.iloc[-1] == VOO.iloc[-1]
