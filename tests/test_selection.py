import pandas as pd

from market_skew import breaking, gate, scan, selection, store
from market_skew.ui import chat, research_view, swing_view

DATE = "2026-11-18"
MID = (gate.STEADY_MIN + gate.HIS_WAY_MIN) // 2 if gate.HIS_WAY_MIN - gate.STEADY_MIN > 1 else gate.STEADY_MIN  # passes Steady, not His way
BODY = {"date": DATE, "sectors": [], "indexes": {"SPY": {"ret_1m": 0.01}, "VIX": {"ret_1d": 0.0}}}


def sentinel_row(symbol, score, thin=False):
    return {"symbol": symbol, "name": symbol, "rank": 1, "score": score, "label": "OK", "as_of": "2026Q3", "thin": thin,
            "growth": 0.2, "accelerating": True, "metrics": {"fcf_margin": 0.25}}


def scored():
    base = dict(bucket="Contrarian Bid", close=50.0, dvol_21=2e8, source="mid", atm=0.20, ret_1m=-0.04, ret_1d=0.01, asym=30,
                market_cap=100e9, name="Co")
    return pd.DataFrame([dict(base, symbol="AAA", sector="Tech"), dict(base, symbol="BBB", sector="Energy")])


def test_first_scan_of_a_week_uses_raw_scores_and_labels_them(tmp_path):
    with store.connect(tmp_path / "t.db") as conn:
        store.save_sentinel(conn, DATE, [sentinel_row("AAA", 82), sentinel_row("BBB", MID)])
        out = selection.choose_all(BODY, scored(), selection.gate_for(conn, DATE), set())
    assert [t["symbol"] for t in out["swing"]] == ["AAA"]  # BBB: MID is under the His way bar
    assert sorted(p["symbol"] for p in out["picks"]) == ["AAA", "BBB"]  # but over the Steady bar
    assert out["swing"][0]["reasons"][0].startswith("Quality score 82 (not yet checked by Claude)")


def test_claudes_deductions_take_a_name_out_once_saved(tmp_path):
    with store.connect(tmp_path / "t.db") as conn:
        rows = [sentinel_row("AAA", 82), sentinel_row("BBB", MID)]
        store.save_sentinel(conn, DATE, rows)
        store.save_breaking(conn, "AAA", breaking.version(rows[0]), {"deductions": [], "what_breaks": "x", "total": 82 - gate.STEADY_MIN + 1})
        out = selection.choose_all(BODY, scored(), selection.gate_for(conn, DATE), set())
    assert out["swing"] == [] and [p["symbol"] for p in out["picks"]] == ["BBB"]  # AAA falls one under the Steady bar after deductions: out of both lists


def test_drop_unselected_only_touches_the_reports_own_day(tmp_path):
    with store.connect(tmp_path / "t.db") as conn:
        store.add_paper(conn, DATE, [{"symbol": "OLDPICK", "price": 1.0}], 1.0)
        store.add_paper(conn, "2026-11-01", [{"symbol": "EARLY", "price": 1.0}], 1.0)
        store.add_swing(conn, DATE, [{"symbol": "GONE", "entry": 1, "stop": 0.9, "target": 1.2, "until": "2026-12-16"}], 1.0)
        store.drop_unselected(conn, DATE, ["KEEP"], [])
        assert [r["symbol"] for r in store.paper_rows(conn)] == ["EARLY"] and store.swing_rows(conn) == []


def test_screened_selects_again_after_claude_has_argued(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(scan.breaking_run, "on_screen", lambda body, rows: ["AAA"])
    monkeypatch.setattr(scan, "_select", lambda *a: calls.append("select"))
    monkeypatch.setattr(scan, "_breaking", lambda *a: calls.append("breaking") or ["AAA"])
    monkeypatch.setattr(scan, "_dates", lambda *a: False)  # no network, nothing written to data/
    with store.connect(tmp_path / "t.db") as conn:
        scan._screened(conn, {}, scored(), DATE)
    assert calls == ["select", "breaking", "select", "select"]


def test_chip_says_when_claude_has_not_checked_and_chat_brief_carries_scores():
    assert "not yet checked by Claude" in research_view.chip({"score": 82, "raw": 82, "label": "WATCH", "checked": False}, "AAA")
    assert "not yet" not in research_view.chip({"score": 74, "raw": 82, "label": "OK", "checked": True}, "AAA")
    report = {"date": DATE, "universe": 1, "with_skew": 1, "read": [], "kpis": [], "stocks": [], "picks": [], "swing": [],
              "sentinel_brief": [{"symbol": "AAA", "score": 74, "raw": 82, "checked": True, "what_breaks": "Sales growth stalls."},
                                 {"symbol": "BBB", "score": 65, "raw": 65, "checked": False, "what_breaks": None}]}
    text = chat.brief("picks", report)
    assert "AAA: Quality score 74 (was 82 before Claude's deductions); what breaks: Sales growth stalls." in text
    assert "BBB: Quality score 65 (not yet checked by Claude)" in text


def test_empty_his_way_says_so_plainly():
    html = swing_view.section({"swing": []})
    assert "No company is both attractive" in html and "goes to the funds" in html
