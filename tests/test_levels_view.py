import datetime as dt

from market_skew.ui import levels_view

TODAY = dt.date(2026, 11, 18)
DATA = {"closes": [100.0 + i % 7 for i in range(200)], "last": 103.0, "start": "2026-01-01", "end": "2026-11-17",
        "levels": [{"level": 90.0, "kind": "floor", "touches": 3, "distance_pct": 12.6}]}
EARN = {"kind": "stock", "next_date": "2026-12-01", "beats": 4, "of": 4, "avg_surprise": 3.1, "spread": None}


def report(**more):
    return {"levels": {"AAA": DATA}, "earnings": {"AAA": EARN}, **more}


def test_chart_has_title_desc_dashed_level_and_today_dot():
    html = levels_view.block("AAA", report(), "steady", today=TODAY)
    assert 'role="img"' in html and "<title" in html and "<desc" in html
    assert html.count('class="lv-floor"') == 1 and 'class="lv-now"' in html and "$90.00" in html
    assert "Candidate areas to add" in html and "not buy signals" in html


def test_earnings_flag_when_within_two_weeks():
    html = levels_view.block("AAA", report(), "steady", today=TODAY)
    assert "Reports 1 Dec · beat 4 of the last 4, average surprise +3.1%" in html and "Earnings within 2 weeks" in html
    far = levels_view.block("AAA", {**report(), "earnings": {"AAA": {**EARN, "next_date": "2027-01-20"}}}, "steady", today=TODAY)
    assert "Earnings within 2 weeks" not in far


def test_funds_show_no_earnings_line():
    html = levels_view.block("AAA", {**report(), "earnings": {"AAA": {"kind": "fund"}}}, "own", today=TODAY)
    assert "lv-earn" not in html


def test_add_on_rule_line():
    html = levels_view.block("AAA", report(), "own", last_buy=100.0, today=TODAY)
    assert "Next add only below <b>$95.00</b>" in html and "5% under your last buy" in html and "lv-buy" in html


def test_compact_is_smaller_and_still_labelled():
    html = levels_view.block("AAA", report(), "own", last_buy=100.0, compact=True, today=TODAY)
    assert "compact" in html and "<title" in html and "next add below $95.00" in html and "Areas: $90.00" in html


def test_no_levels_still_draws_chart_and_says_so():
    html = levels_view.block("AAA", {"levels": {"AAA": {**DATA, "levels": []}}}, "steady", today=TODAY)
    assert "No clear floor" in html and "lv-floor" not in html


def test_missing_data_is_empty_and_symbol_escaped():
    assert levels_view.block("ZZZ", report(), "steady") == ""
    assert "<script>" not in levels_view.block("<script>", {"levels": {"<script>": DATA}}, "steady", today=TODAY)
