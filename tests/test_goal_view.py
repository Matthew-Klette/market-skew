import json

import numpy as np
import pandas as pd
import pytest

from market_skew import history, holdings
from market_skew.ui import goal_ctx, goal_view, money_ctx, money_view, risk_view

REPORT = {"date": "2026-11-18", "stocks": [{"symbol": "VOO", "close": 500.0}], "funds": {}}
AMOUNTS = {"tfsa": 3000.0, "usd": 5000.0}
MONTHS = [str(p) for p in pd.period_range("2016-01", "2026-10", freq="M")]


def fake_levels():
    rng = np.random.default_rng(3)
    out = {}
    for name in history.NAMES:
        steps = rng.normal(0.008, 0.04, len(MONTHS)) if name != "USDZAR" else rng.normal(0.003, 0.025, len(MONTHS))
        base = 15.0 if name == "USDZAR" else 100.0
        out[name] = dict(zip(MONTHS, (base * np.cumprod(1 + steps)).tolist()))
    out["SYG500"] = {m: v for m, v in out["SYG500"].items() if m >= "2018-01"}
    return out


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    path = tmp_path / "holdings.json"
    monkeypatch.setattr(holdings, "load", lambda p=path, _l=holdings.load: _l(p))
    monkeypatch.setattr(money_ctx.fx, "cached", lambda: {"rate": 18.0})
    monkeypatch.setattr(money_ctx.jse, "cached", lambda: {})
    monkeypatch.setattr(goal_ctx.history, "cached", lambda: {"levels": fake_levels(), "date": "2026-11-18"})
    return path


PREFS = {"goal": {"target": 2e6, "years": 20, "start": 10000.0, "monthly": 8000.0, "actual": False}}


def test_page_shows_band_probability_plain_fv_and_the_not_a_forecast_line(cfg):
    html = money_view.page(money_ctx.page_ctx(REPORT, PREFS, AMOUNTS))
    assert "Will I get there?" in html and "<svg" in html and "fan-mid" in html and "Past returns, resampled; not a forecast." in html
    assert "resampled paths" in html and "at a steady 7% a year" in html and "SYG500 before 2018-02 is VOO in rand" in html


def test_page_without_a_saved_goal_asks_for_one_and_risk_still_shows(cfg):
    html = money_view.page(money_ctx.page_ctx(REPORT, {}, AMOUNTS))
    assert "Type a target and how many years" in html and "What a bad year looks like" in html and "uses R10,000 as an example" in html
    assert "Value at risk" in html and "Jan to Oct 2022 again would" in html and "March 2020 again would" in html


def test_defaults_come_from_holdings_value_and_this_months_plan(cfg):
    cfg.write_text(json.dumps([{"symbol": "VOO", "account": "usd", "units": 2}]))
    g = money_ctx.page_ctx(REPORT, {"goal": {"target": 1e6, "years": 5}}, AMOUNTS)["goal"]
    assert g["form"]["start"] == pytest.approx(2 * 500 * 18) and g["form"]["monthly"] == 8000.0


def test_actual_split_tick_uses_holdings_weights(cfg):
    cfg.write_text(json.dumps([{"symbol": "VOO", "account": "usd", "units": 2}]))
    g = money_ctx.page_ctx(REPORT, {"goal": {"target": 1e6, "years": 5, "actual": True}}, AMOUNTS)["goal"]
    assert g["weights"] == {"VOO": 1.0} and g["label"] == "your actual split"


def test_no_history_says_to_run_skew_history(cfg, monkeypatch):
    monkeypatch.setattr(goal_ctx.history, "cached", lambda: None)
    html = money_view.page(money_ctx.page_ctx(REPORT, PREFS, AMOUNTS))
    assert "Run ./skew history" in html and "<svg" not in html


def test_post_goal_saves_clean_values_and_rejects_bad_ones():
    saved = {}
    assert money_ctx.post("/goal", {"goal": {"target": "500000", "years": "10", "actual": True}}, saved.update)[0] == 200
    assert saved["goal"]["target"] == 500000.0 and saved["goal"]["years"] == 10
    assert money_ctx.post("/goal", {"goal": {"target": "x", "years": 10}}, saved.update)[0] == 400
    assert "/goal" in money_ctx.POSTS


def test_saved_inflation_round_trips_as_a_share():
    assert goal_ctx.saved({"goal": {"target": 1e6, "years": 5, "inflation": 0.05}})["inflation"] == 0.05


def test_fan_svg_escapes_and_has_no_scripts():
    svg = goal_view.fan_svg({"years": [0, 1], "p10": [1, 2], "p50": [1, 3], "p90": [1, 4]}, 5.0)
    assert "<script" not in svg and "aria-label" in svg and "Target R5" in svg


def test_risk_block_handles_unrecovered_and_short_history():
    assert "Not enough" in risk_view.block({"reason": None, "stats": None, "value": 1, "assumed": True, "label": "x", "notes": {}})
    assert "No price history" in risk_view.block({"reason": "No price history saved yet.", "stats": None})


def test_page_says_how_fast_the_sampled_history_grew_and_flags_a_hot_stretch(cfg):
    g = money_ctx.page_ctx(REPORT, PREFS, AMOUNTS)["goal"]
    assert g["cagr"] is not None and f"grew {g['cagr'] * 100:.0f}% a year in rand" in goal_view.block(g)
    assert "leans optimistic" in goal_view.block({**g, "cagr": 0.20}) and "leans optimistic" not in goal_view.block({**g, "cagr": 0.05})


def test_a_stress_gain_in_rand_is_explained():
    stats = {"months": 130, "from": "2016-01", "to": "2026-10", "var": {"pct": .05, "rand": 5}, "cvar": {"pct": .06, "rand": 6},
             "worst_month": {"month": "2017-12", "pct": -.08, "rand": -8}, "worst_12": None,
             "drawdown": {"depth": .1, "peak": "2021-12", "trough": "2022-06", "recovered": None, "months_to_recover": None, "months_underwater": None},
             "stress": [{"label": "March 2020", "pct": 0.02, "rand": 2200.0}]}
    html = risk_view.block({"reason": None, "stats": stats, "value": 100.0, "assumed": False, "label": "x", "notes": {}})
    assert "March 2020 again would add R2,200" in html and "weaker rand lifts dollar funds" in html and "has not got back" in html


def test_form_shows_big_numbers_without_exponents(cfg):
    html = money_view.page(money_ctx.page_ctx(REPORT, PREFS, AMOUNTS))
    assert 'value="2000000"' in html and "2e+06" not in html


def test_two_fans_side_by_side_cautious_first_with_a_chance_for_each(cfg):
    g = money_ctx.page_ctx(REPORT, PREFS, AMOUNTS)["goal"]
    html = goal_view.block(g)
    assert html.count('class="fan"') == 2 and 'class="fan-pair"' in html
    assert html.index("<h3>Cautious (default)</h3>") < html.index("<h3>Past decade</h3>")
    assert html.count("resampled paths") == 2 and g["result"]["prob"] <= g["past"]["prob"]
    assert "unusually high" in html and "5 points a year" in html and f"{g['cagr'] * 100:.0f}% a year in rand" in html


def test_both_fans_share_one_scale_so_they_compare_honestly(cfg):
    g = money_ctx.page_ctx(REPORT, PREFS, AMOUNTS)["goal"]
    labels = lambda svg: [x for x in svg.split("<text") if "fan-label" in x][:5]
    pair = goal_view.block(g).split('class="fan"')[1:3]
    assert labels(pair[0]) == labels(pair[1])


def test_cautious_is_the_saved_default_result_and_past_decade_is_higher(cfg):
    g = money_ctx.page_ctx(REPORT, PREFS, AMOUNTS)["goal"]
    assert g["result"]["final"]["p50"] < g["past"]["final"]["p50"]


def test_milestones_block_lists_defaults_with_progress_and_date_bands(cfg):
    ctx = money_ctx.page_ctx(REPORT, {"money": {"expenses": 10000, "emergency": 15000}, **PREFS}, AMOUNTS)
    html = goal_view.block(ctx["goal"])
    assert "Milestones" in html and "R100,000 invested" in html and "R1,000,000 invested" in html and "Emergency fund" in html
    assert "data-milestones" in html and "(cautious)" in html and "(past decade)" in html and "50%" in html
    assert "<script" not in html


def test_milestone_labels_are_escaped(cfg):
    ctx = money_ctx.page_ctx(REPORT, {"milestones": [{"label": "<img onerror=x>", "kind": "invested", "value": 5e5}]}, AMOUNTS)
    html = goal_view.block(ctx["goal"])
    assert "<img onerror" not in html and "&lt;img onerror=x&gt;" in html


def test_post_milestones_saves_clean_rows_and_rejects_bad_ones():
    saved = {}
    ok = {"milestones": [{"label": "Car", "kind": "invested", "value": "250000"}]}
    assert money_ctx.post("/milestones", ok, saved.update) == (200, {"milestones": [{"label": "Car", "kind": "invested", "value": 250000.0}]})
    assert saved["milestones"][0]["value"] == 250000.0
    assert money_ctx.post("/milestones", {"milestones": [{"label": "", "kind": "invested", "value": 5}]}, saved.update)[0] == 400
    assert money_ctx.post("/milestones", {}, saved.update)[0] == 400 and "/milestones" in money_ctx.POSTS


def test_milestones_show_without_a_saved_goal_and_without_history(cfg, monkeypatch):
    html = goal_view.block(money_ctx.page_ctx(REPORT, {}, AMOUNTS)["goal"])
    assert "R500,000 invested" in html
    monkeypatch.setattr(goal_ctx.history, "cached", lambda: None)
    assert "Milestones" in goal_view.block(money_ctx.page_ctx(REPORT, {}, AMOUNTS)["goal"])
