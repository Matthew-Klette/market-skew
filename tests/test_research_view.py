import contextlib
import json

import pytest

from market_skew import scan, sentinel, store
from market_skew.ui import research_view, server
from tests.test_sentinel import metrics, peers, px

REAL_CONNECT = store.connect

REPORT = {"date": "2026-11-18", "built_at": "2026-11-18T23:20:00", "universe": 2000, "with_skew": 1900, "failed_count": 0,
          "expiry": "2026-12-18", "intraday": False, "buckets": {}, "kpis": [], "read": [], "themes": [], "sectors": [],
          "heatmap": {}, "stocks": [], "picks": [],
          "predictions": {"ACME": {"low": 40.0, "mid": 50.0, "high": 60.0, "last": 50.0, "verdict": "A projection."}}}


def scored_rows():
    f, p = peers()
    f["ACME"], p["ACME"] = metrics(), px(name="Acme <b>Corp</b>")
    f["THIN"], p["THIN"] = metrics(depth="Thin", revenue_growth=0.02), px(name="Thin Co", close=70.0)
    return sentinel.score_all(f, p, {"ACME": 70})


@pytest.fixture
def served(tmp_path, monkeypatch):
    path = tmp_path / "t.db"
    with REAL_CONNECT(path) as conn:
        store.save_report(conn, REPORT["date"], REPORT["built_at"], REPORT)
        store.save_sentinel(conn, REPORT["date"], scored_rows())
    monkeypatch.setattr(server.store, "connect", lambda: REAL_CONNECT(path))
    monkeypatch.setattr(server, "prefs", lambda: {"accepted_terms": "2026-01-01T00:00:00"})
    monkeypatch.setattr(scan, "watchlist", lambda: set())
    return path


@pytest.fixture
def empty(tmp_path, monkeypatch):
    path = tmp_path / "e.db"
    monkeypatch.setattr(server.store, "connect", lambda: REAL_CONNECT(path))
    monkeypatch.setattr(server, "prefs", lambda: {"accepted_terms": "2026-01-01T00:00:00"})
    monkeypatch.setattr(scan, "watchlist", lambda: set())
    with REAL_CONNECT(path) as conn:
        store.save_report(conn, REPORT["date"], REPORT["built_at"], REPORT)


def test_board_renders_sorted_rows_filters_and_escapes(served):
    code, html = server.render("/research", {})
    assert code == 200 and 'aria-current=page>Research' in html
    assert 'href="/research/ACME"' in html and "Acme &lt;b&gt;Corp&lt;/b&gt;" in html and "<b>Corp</b>" not in html
    assert 'data-filter="WATCH"' in html and "data-sector" in html and "data-search" in html
    assert "not enough filings" in html          # the Thin company's score is greyed with a reason
    assert html.index("Market</a>") < html.index("Research</a>") < html.index("Stocks</a>")


def test_company_card_renders_every_section(served):
    code, html = server.render("/research/ACME", {})
    assert code == 200
    for text in ("What breaks this call", "Read this first", "Is it growing?", "Does it keep cash?", "What are you paying?",
                 "Can it survive?", "Market&#x27;s view (proxy)", "Priced fair?", "What $1 of its yearly cash costs", "Google's prediction",
                 "Options market today", "QUALITY</b>", "<svg"):
        assert text in html, text
    assert "+" in html and "&lt;b&gt;Corp&lt;/b&gt;" in html


def test_card_accepts_lowercase_rejects_bad_tickers_and_explains_unknown_ones(served):
    assert server.render("/research/acme", {})[0] == 200
    assert server.render("/research/%3Cscript%3E", {})[0] == 404
    assert server.render("/research/WAYTOOLONGTICKER", {})[0] == 404
    code, html = server.render("/research/ZZZZ", {})
    assert code == 200 and "No company numbers for this ticker" in html


def test_empty_table_shows_the_empty_state(empty):
    for path in ("/research", "/research/AAPL"):
        code, html = server.render(path, {})
        assert code == 200 and "add your email under Settings on the How it works tab" in html.replace("&#x27;", "'")


def test_how_it_works_explains_sentinel(served):
    html = server.render("/how", {})[1]
    assert "Quality score" in html and "Market&#x27;s view, a proxy" in html or "Market's view, a proxy" in html
    assert "WATCH" in html


def test_tickers_on_stocks_and_picks_link_to_their_card(served):
    report = {**REPORT, "stocks": [dict(symbol="FTV", name="F", sector="Industrials", action="x", bucket="Chase", asym=1, close=1.0, ret_1d=0.0,
                                        ret_1w=0.0, ret_1m=0.0, skew=0.0, atm=0.2, call_volume=1, put_volume=1, price_z=0, bet_z=0, watch=False, source="mid")]}
    from market_skew.ui import views
    assert 'href="/research/FTV"' in views.stocks(report)


def test_chart_needs_three_years():
    row = scored_rows()[0]
    assert "<svg" in research_view.chart(row)
    assert "Needs at least three years" in research_view.chart({**row, "history": row["history"][:2]})


def _with_breaking(path, total=20, rows=None):
    from market_skew import breaking
    data = rows or scored_rows()
    acme = next(r for r in data if r["symbol"] == "ACME")
    answer = {"deductions": [{"points": 8, "reason": "Debt <script> is high."}, {"points": total - 8, "reason": "Growth is slowing."}],
              "what_breaks": "A sales slowdown would hurt.", "total": total}
    with REAL_CONNECT(path) as conn:
        store.save_breaking(conn, "ACME", breaking.version(acme), answer)
    return acme


def test_card_shows_what_breaks_headline_and_honest_note(served):
    acme = _with_breaking(served)
    _, html = server.render("/research/ACME", {})
    assert f'{acme["score"]} → {acme["score"] - 20}' in html
    assert "A sales slowdown would hurt." in html and "Growth is slowing." in html and "-8" in html and "-12" in html
    assert "Debt &lt;script&gt; is high." in html and "<script> is" not in html
    assert "Claude argued against this company using its filed numbers only, not news." in html
    assert "Claude has not argued" not in html


def test_card_without_an_answer_says_it_has_not_run(served):
    _, html = server.render("/research/ACME", {})
    assert "Claude has not argued against this company yet" in html and " → " not in html.split("score-big")[1][:60]


def test_board_shows_adjusted_score_with_the_raw_struck_through_and_labels_follow(served):
    acme = _with_breaking(served, 30)
    _, html = server.render("/research", {})
    assert f'<s class="was muted" title="before Claude\'s deductions">{acme["score"]}</s>'.replace("'", "&#x27;") in html or f">{acme['score']}</s>" in html
    assert f'data-v="{acme["score"] - 30}"' in html


def test_stale_answer_is_ignored_when_the_numbers_changed(served):
    with REAL_CONNECT(served) as conn:
        store.save_breaking(conn, "ACME", "2020Q1|1", {"deductions": [], "what_breaks": "old", "total": 30})
    _, html = server.render("/research/ACME", {})
    assert "old" not in html.split("What breaks this call")[1][:300] and "Claude has not argued" in html


def test_pick_and_swing_cards_show_the_compact_sentinel_chip_linking_to_the_card():
    from market_skew.ui import swing_view, views
    chip = {"ACME": {"score": 56, "raw": 76, "label": "PASS"}}
    pick = dict(symbol="ACME", name="Acme", sector="Staples", score=95, price=70.0, iv=0.15, ret_1m=0.01, timing="add",
                timing_label="Good time to add", reasons=["calm"])
    html = views.picks_page({"date": "d", "picks": [pick], "sentinel": chip, "read": ["The tape: x"]}, {"tfsa": 0, "usd": 0}, 17.5)
    assert '<a class="sentinel-chip" href="/research/ACME"' in html and "Quality score 76 → 56" in html
    plain = research_view.chip({"score": 80, "raw": 80, "label": "WATCH"}, "ACME")
    assert "Quality score 80<" in plain and "→" not in plain and research_view.chip(None, "ACME") == ""
    trade = dict(symbol="ACME", name="Acme", sector="Staples", ret_1m=0.01, entry=10.0, stop=9.0, target=12.0, stop_pct=-0.1, target_pct=0.2,
                 until="2026-12-16", reasons=["dip"])
    swing = swing_view.section({"swing": [trade], "sentinel": chip})
    assert 'class="sentinel-chip" href="/research/ACME"' in swing and "Quality score 76 → 56" in swing
