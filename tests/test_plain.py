from market_skew.ui import plain, views

DOWN = {
    "date": "2026-11-19",
    "indexes": {"SPY": {"ret_1d": -0.02, "ret_1w": -0.054, "ret_1m": -0.074, "off_high": -0.113},
                "RSP": {"ret_1m": -0.023}, "VIX": {"ret_1d": 0.158, "ret_1w": 0.52, "ret_1m": 0.705}},
    "sectors": [dict(name="Staples", rel_1m=0.11, flow_bps=51.0), dict(name="Comm Svcs", rel_1m=-0.05, flow_bps=-92.7),
                dict(name="Info Tech", rel_1m=-0.03, flow_bps=119.6)],
    "themes": [dict(name="Homebuilders", rel_1m=0.12, leaders=["PHM", "KBH"])],
    "funds": {"VOO": dict(name="Vanguard S&P 500", timing="add", label="Good time to add", why="It dipped."),
              "SCHD": dict(name="Schwab", timing="hold", label="Don't add now", why="Falling.")},
    "heatmap": {"weeks": ["w1", "w2", "w3"], "rows": {"Staples": [0.01, 0.02, 0.03], "Comm Svcs": [-0.01, 0.01, -0.02]}},
}


def test_market_down_says_no_because_with_plain_numbers():
    html = plain.market_up(DOWN)
    assert ">No</span> because" in html and "down 7% this month" in html and "11% below its highest" in html
    assert "1 of 3 kinds of business are up" in html and "not as bad as the headline" in html


def test_nervous_market_and_monthly_money_answers():
    assert ">Yes</span>" in plain.nervous(DOWN) and "fear gauge" in plain.nervous(DOWN)
    html = plain.monthly(DOWN)
    assert ">Yes</span>" in html and "buys more" in html and "For VOO" in html and "For SCHD" in html


def test_money_flow_uses_everyday_sector_names():
    html = plain.money_flow(DOWN)
    assert "Into tech companies" in html and "internet and media" in html and "Homebuilders (PHM, KBH)" in html


def test_streaks_replace_the_grid_with_dots_and_words():
    html = plain.streaks(DOWN["heatmap"], DOWN["sectors"])
    assert "Beat the market every week" in html and "Beat the market 1 of the last 3 weeks" in html
    assert html.index("Everyday basics") < html.index("Internet and media") and html.count('class="dot up"') == 4


def test_answers_cope_with_a_report_missing_fields():
    assert plain.answers({}) == "" and plain.market_up({"indexes": {}}) == ""
    assert "Not enough weeks" in plain.streaks({}, [])


def test_market_tab_leads_with_answers_and_tucks_numbers_away():
    html = views.overview({**DOWN, "sectors": [], "themes": [], "kpis": [], "read": ["x"], "universe": 1, "with_skew": 1, "expiry": None})
    assert html.index("in plain English") < html.index("Show the detailed numbers") and "winning streak" in html
