from market_skew.ui import views
from market_skew.ui.fmt import cp_ratio, pct, tone

REPORT = {
    "date": "2026-11-18", "built_at": "2026-11-18T23:20:00", "universe": 2000, "with_skew": 1900, "failed_count": 3,
    "expiry": "2026-12-18", "intraday": False, "buckets": {"Chase": 1},
    "kpis": [{"label": "S&P 500 (SPY), 1 month", "value": 0.04, "kind": "pct", "note": "QQQ +5.0%"},
             {"label": "Money moved in", "value": "Cons Disc", "kind": "text", "note": "x"}],
    "read": ["The tape: <b>not html</b>"],
    "themes": [dict(name="Gold", count=18, rel_1m=0.27, rel_1w=0.03, today=0.02, vol_today=1.0, trend="improving",
                    flow_bps=9.4, breadth=1.0, skew=0.05, leaders=["NEM"])],
    "sectors": [], "heatmap": {"weeks": ["Nov 2–Nov 6"], "rows": {"Energy": [0.02]}, "rel_1m": {"Energy": 0.04}},
    "stocks": [dict(symbol="FTV", sector="Industrials", action="FRESH LOOK - contrarian bid", bucket="Contrarian Bid",
                    asym=191, close=60.6, ret_1d=0.01, ret_1w=-0.02, ret_1m=-0.1, skew=0.05, atm=0.3,
                    call_volume=900, put_volume=100, price_z=-1, bet_z=2, watch=True, source="mid")],
}


def test_overview_escapes_text_and_shows_tiles():
    html = views.overview(REPORT)
    assert "&lt;b&gt;not html&lt;/b&gt;" in html
    assert "Cons Disc" in html and "+27.0%" in html and "3 chains failed" in html


def test_stocks_table_has_filters_and_starred_row():
    html = views.stocks(REPORT)
    assert 'data-filter="Contrarian Bid"' in html
    assert 'aria-pressed="true" aria-label="Watch FTV"' in html


def test_shell_marks_current_tab_and_carries_token():
    html = views.shell("stocks", "Stocks", "", REPORT, ["2026-11-18"], "tok", "system", {"state": "idle"})
    assert 'href="/stocks" aria-current=page' in html and 'content="tok"' in html


def test_formatters():
    assert pct(0.0123) == "+1.2%" and pct(None) == "–"
    assert tone(0.01) == "up" and tone(-0.01) == "down" and tone(0) == "flat"
    assert cp_ratio(900, 100) == "9.00"


def test_picks_page_splits_money_and_lights_holdings():
    report = dict(REPORT, picks=[dict(symbol="KO", name="Coca-Cola", sector="Staples", score=95, price=70.0, iv=0.15,
                                      ret_1m=-0.03, timing="add", timing_label="Good time to add", reasons=["Calm."])],
                  holdings=[dict(symbol="SCARY", name="Scary", light="hold", label="Don't add now", why="Falling.",
                                 price=10.0, ret_1m=-0.1)],
                  paper=[dict(symbol="KO", date="2026-11-18", entry=70.0, now=72.0, ret=0.0286, voo_ret=0.01)])
    html = views.picks_page(report, {"tfsa": 0, "usd": 1000}, 17.5)
    assert "R300" in html and "KO" in html and "QQQ" in html and "<b>VOOG</b>" not in html  # 30% to the pick, funds share the rest
    assert "Good time to add" in html and "Don&#x27;t add now" in html
    assert "+2.9%" in html


def test_picks_plan_shows_both_accounts_in_rand_and_dollars_with_costs():
    report = dict(REPORT, jse={"SYG500": {"price": 80.0, "date": "2026-11-18"}},
                  picks=[dict(symbol="KO", name="Coca-Cola", sector="Staples", score=95, price=70.0, iv=0.15,
                              ret_1m=-0.03, timing="add", timing_label="Good time to add", reasons=["Calm."])])
    html = views.picks_page(report, {"tfsa": 3000, "usd": 5000}, 17.5)
    assert "SYG500" in html and "R3,000" in html and "R5,000" in html
    assert "R1,500" in html and "$86" in html            # KO's 30% of R5,000 in rand and dollars
    assert "$" in html and "R25" in html and "Thrive" in html
    assert 'data-amount="tfsa"' in html and 'data-amount="usd"' in html


def test_picks_plan_without_price_or_rate_says_so_and_escapes():
    report = dict(REPORT, picks=[dict(symbol="<b>", name="<i>x</i>", sector="S", score=1, price=1.0, iv=0.1, ret_1m=0.0,
                                      timing="add", timing_label="Good", reasons=["<script>"])])
    html = views.picks_page(report, {"tfsa": 0, "usd": 0}, None)
    assert "next scan" in html and "<script>" not in html and "<i>x</i>" not in html


def test_prediction_block_labels_and_escapes():
    from market_skew.ui import prediction_view
    p = {"low": 90.0, "mid": 100.0, "high": 110.0, "last": 98.0, "model": "TimesFM 2.5", "verdict": "<b>x</b> hasn't"}
    html = prediction_view.block(p)
    assert "Google's prediction" in html and "(TimesFM 2.5)" in html and "&lt;b&gt;x" in html and "<b>x</b>" not in html
    assert prediction_view.block(None) == ""


def test_his_way_section_shows_levels_reasons_prediction_and_record_escaped():
    trade = dict(symbol="<X>", name="<i>Co</i>", sector="Tech", score=60, entry=50.0, stop=46.0, target=58.0, until="2026-12-16",
                 stop_pct=-0.08, target_pct=0.16, atm=0.4, ret_1m=-0.08, reasons=["Down 8% this month, but a bounce."])
    row = dict(symbol="AA", date="2026-11-02", entry=100.0, stop=90.0, target=120.0, until="2026-11-30", status="target",
               exit_date="2026-11-10", exit_price=121.0, net_ret=0.19, spy_entry=500.0, now=121.0, ret=0.19, voo_ret=0.02)
    pred = dict(low=40.0, mid=50.0, high=60.0, last=50.0, verdict="v", model="TimesFM 2.5")
    html = views.picks_page(dict(REPORT, swing=[trade], swing_record=[row], predictions={"<X>": pred}), {"tfsa": 0, "usd": 0}, None)
    assert "His way" in html and "swing-trading creator" in html
    assert "Sell if below" in html and "$46.00" in html and "Take profit at" in html and "2026-12-16" in html
    assert "Not on EasyEquities" in html and "Google&#x27;s prediction" in html or "Google's prediction" in html
    assert "<X>" not in html and "&lt;X&gt;" in html
    assert "Hit the target" in html and "+19.0%" in html and "VOO same period" in html


def test_picks_plan_uses_fund_signals_and_lens():
    from market_skew.ui import plan_view
    funds = {"QQQ": dict(timing="add", label="Good time to add", why="It dipped."), "SCHD": dict(timing="hold", label="x", why="y")}
    swing = [dict(symbol="SW", name="Swing Co", sector="Tech", ret_1m=-0.1, entry=10.0, stop=9.0, target=12.0, stop_pct=-0.1, target_pct=0.2,
                  until="2026-12-16", reasons=["r"])]
    html = views.picks_page(dict(REPORT, funds=funds, swing=swing), {"tfsa": 0, "usd": 10000}, 17.5, "his")
    assert "Good time to add: It dipped." in html and "His way: buy near $10.00" in html and "SW" in html
    rows = plan_view.usd_body(plan_view.usd_lines(dict(REPORT, funds=funds), 5000, "mine", 17.5), 17.5)
    assert rows.count("<tr") == 4 and "R5,000" in rows  # three funds plus the total


def test_picks_lens_control_shows_choice_recommendation_and_arranges_sections():
    rec = {"lens": "mine", "reason": "Not enough evidence yet: 5 days of record; needs about 3 months.", "evidence": {}}
    report = dict(REPORT, picks=[], swing=[])
    auto = views.picks_page(report, {"tfsa": 0, "usd": 0}, None, "mine", "auto", rec)
    assert 'data-lens="auto" aria-pressed="true"' in auto and 'data-lens="his" aria-pressed="false"' in auto
    assert "Recommended: My way." in auto and "Not enough evidence yet" in auto
    assert auto.index("data-my-way") < auto.index('class="other-way"') < auto.index("data-his-way")
    his = views.picks_page(report, {"tfsa": 0, "usd": 0}, None, "his", "his", rec)
    assert 'data-lens="his" aria-pressed="true"' in his and "You chose His way" in his
    assert his.index("data-his-way") < his.index('class="other-way"') < his.index("data-my-way")


def test_lens_reason_is_escaped():
    html = views.picks_page(dict(REPORT), {"tfsa": 0, "usd": 0}, None, "mine", "auto", {"lens": "mine", "reason": "<script>x</script>"})
    assert "<script>x" not in html


def test_lens_control_sits_above_the_plan_and_dollar_column_says_before_costs():
    rec = {"lens": "mine", "reason": "Not enough evidence yet.", "evidence": {}}
    html = views.picks_page(dict(REPORT), {"tfsa": 0, "usd": 1000}, 17.5, "mine", "auto", rec)
    assert html.index("data-lens-control") < html.index("Your plan this month")
    assert html.index("Recommended: My way.") < html.index("Your plan this month")
    assert "In dollars, before costs" in html and "usdFee" not in html


def test_missing_forecaster_shows_one_muted_note():
    html = views.picks_page(dict(REPORT, forecaster_missing=True), {"tfsa": 0, "usd": 0}, None)
    assert html.count("isn&#x27;t installed on this Mac") == 1


def test_stale_rate_and_missing_price_wording():
    html = views.picks_page(dict(REPORT, rate_date="2026-11-10", jse={"SYG500": {"price": 80.0, "date": "2026-11-10"}}),
                            {"tfsa": 100, "usd": 100}, 17.5)
    assert "last known rate" in html and "2026-11-10" in html and "as of 2026-11-10" in html
    assert "price at next scan" in views.picks_page(dict(REPORT), {"tfsa": 1, "usd": 1}, None)


def test_open_swing_trade_shows_return_after_fees_if_sold_now():
    row = dict(symbol="AA", date="2026-11-02", entry=100.0, stop=90.0, target=120.0, until="2026-11-30", status="open",
               exit_date=None, exit_price=None, net_ret=None, now=110.0, ret=0.086, voo_ret=0.03)
    html = views.picks_page(dict(REPORT, swing=[], swing_record=[row]), {"tfsa": 0, "usd": 0}, None)
    assert "after fees if sold now" in html


def test_picks_first_run_panel_replaces_the_plan_until_amounts_are_saved():
    html = views.picks_page(REPORT, {"tfsa": 0.0, "usd": 0.0}, 17.5, amounts_set=False)
    assert "Tell me how much you invest each month" in html
    assert 'data-first-amount="tfsa"' in html and 'data-first-amount="usd"' in html
    assert "SYG500" not in html and "R3,000" not in html and "R5,000" not in html
