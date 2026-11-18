import json

import pytest

from market_skew import holdings, money_rules
from market_skew.ui import money_ctx, money_view, plan_view, server

REPORT = {"date": "2026-11-18", "stocks": [{"symbol": "VOO", "close": 500.0}, {"symbol": "QQQ", "close": 600.0}],
          "funds": {"SCHD": {"price": 30.0}}}
AMOUNTS = {"tfsa": 3000.0, "usd": 5000.0}


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    path = tmp_path / "holdings.json"
    monkeypatch.setattr(holdings, "HOLDINGS", path)
    monkeypatch.setattr(holdings, "save", lambda rows, p=path, _s=holdings.save: _s(rows, p))
    monkeypatch.setattr(holdings, "load", lambda p=path, _l=holdings.load: _l(p))
    monkeypatch.setattr(money_ctx.fx, "cached", lambda: {"rate": 18.0})
    monkeypatch.setattr(money_ctx.jse, "cached", lambda: {"SYG500": {"price": 20.0}})
    monkeypatch.setattr(money_ctx.goal_ctx.history, "cached", lambda: None)
    return path


def test_closes_use_stocks_then_fund_prices():
    assert money_ctx.closes(REPORT) == {"VOO": 500.0, "QQQ": 600.0, "SCHD": 30.0} and money_ctx.closes(None) == {}


def test_units_empty_prompts_instead_of_inventing_a_split(cfg):
    cfg.write_text(json.dumps([{"symbol": "QQQ", "account": "usd"}, {"symbol": "STXNDQ", "account": "tfsa"}]))
    html = money_view.page(money_ctx.page_ctx(REPORT, {}, AMOUNTS))
    assert "Add how many units you own to see your split." in html and "Valued at" not in html


def test_page_with_units_shows_drift_and_suggestion(cfg):
    cfg.write_text(json.dumps([{"symbol": "VOO", "account": "usd", "units": 1}, {"symbol": "QQQ", "account": "usd", "units": 5}]))
    ctx = money_ctx.page_ctx(REPORT, {"money": {"take_home": 20000, "expenses": 9000}}, AMOUNTS)
    html = money_view.page(ctx)
    assert "Under target" in html and "Over target" in html and "If you put in R8,000" in html
    assert "Nothing is ever sold" in html and "common rule of thumb" in html
    assert sum(x["rand"] for x in ctx["suggestion"]) == pytest.approx(8000)


def test_plan_lean_only_when_drift_is_large(cfg):
    cfg.write_text(json.dumps([{"symbol": "VOO", "account": "usd", "units": 1}, {"symbol": "QQQ", "account": "usd", "units": 5}]))
    lean = money_ctx.plan_lean(REPORT, {})
    assert "growth funds are" in lean["drift_note"] and lean["drift_tilt"]["QQQ"] < 1
    cfg.write_text("[]")
    assert money_ctx.plan_lean(REPORT, {}) == {}


def test_plan_shows_the_line_and_tilted_amounts(cfg):
    report = {**REPORT, "funds": {k: {"timing": "wait", "label": "w", "why": "x"} for k in ("QQQ", "SCHD", "VOO")},
              "picks": [], "drift_note": "Your growth funds are 12pp over target: this month's plan leans to VOO and SCHD.",
              "drift_tilt": {"QQQ": 0.5, "VOO": 1.5, "SCHD": 1.5}}
    html = plan_view.plan(AMOUNTS, report, 18.0, {})
    assert "12pp over target" in html
    flat = plan_view.usd_lines({**report, "drift_tilt": None}, 5000, "mine", 18.0)
    leaning = plan_view.usd_lines(report, 5000, "mine", 18.0)
    assert leaning[0]["rand"] < flat[0]["rand"]


def test_escapes_symbol_in_editor():
    html = money_view.holdings_view.holding_row({"symbol": '"><script>', "account": "usd"})
    assert "<script>" not in html


def test_post_helpers_validate(cfg):
    saved = {}
    ok = money_ctx.post("/holdings", {"holdings": [{"symbol": "VOO", "account": "usd", "units": "2"}]}, saved.update)
    assert ok[0] == 200 and holdings.load()[0]["units"] == 2.0
    assert money_ctx.post("/holdings", {"holdings": [{"symbol": "x y", "account": "usd"}]}, saved.update)[0] == 400
    assert money_ctx.post("/money", {"money": {"take_home": "abc"}}, saved.update)[0] == 400
    assert money_ctx.post("/money", {"money": {"take_home": "20000"}}, saved.update)[0] == 200 and saved["money"] == {"take_home": 20000.0}
    assert money_ctx.post("/targets", {"targets": {"broad": 60, "growth": 20, "stock": 10}}, saved.update)[0] == 400
    assert money_ctx.post("/targets", {"targets": {"broad": 70, "growth": 20, "stock": 10}}, saved.update)[0] == 200


def test_money_route_and_tab_exist():
    assert server.VIEW_PATHS["/money"] == "money"
    from market_skew.ui import views
    keys = [k for k, _, _ in views.TABS]
    assert keys.index("money") == keys.index("picks") + 1


def test_etf_meter_shows_share_against_the_rule_of_thumb():
    from market_skew import rebalance
    from market_skew.ui import holdings_view
    vals = [{"symbol": "VOO", "rand": 720.0, "sleeve": "broad"}, {"symbol": "NVDA", "rand": 280.0, "sleeve": "stock"}]
    html = holdings_view.etf_block(rebalance.etf_share(vals))
    assert "72%" in html and "70 to 75%" in html and "a common rule of thumb" in html.lower() and 'data-status="ok"' in html
    assert 'class="meter-fill" style="width:72.0%"' in html and html.count("meter-mark") == 2
    assert 'data-status="low"' in holdings_view.etf_block(rebalance.etf_share([{"symbol": "NVDA", "rand": 5.0, "sleeve": "stock"}]))
    assert "Add how many units" in holdings_view.etf_block(None)
