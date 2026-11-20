from market_skew import buynow, levels


def _fund_report(**over):
    closes = [600.0] * 200 + [700.0] + [690.0] * 50 + [600.0]          # high 700, now 600: 14% off
    report = {
        "date": "2026-11-20",
        "indexes": {"SPY": {"off_high": -0.12, "ret_1m": -0.09}, "VIX": {"ret_1m": 0.60, "ret_1d": 0.01}},
        "funds": {"QQQ": {"name": "Invesco QQQ", "bucket": "Contrarian Bid", "ret_1m": -0.13, "price": 600.0},
                  "VOO": {"name": "Vanguard S&P 500", "bucket": "Fear", "ret_1m": -0.10, "price": 500.0}},
        "levels": {"QQQ": {"closes": closes, "levels": []}, "VOO": {"closes": closes, "levels": []}},
        "predictions": {"QQQ": {"mid": 630.0, "last": 600.0}},
        "swing": [],
    }
    report.update(over)
    return report


def test_fund_fires_only_when_market_sale_panic_and_bullish_bets_all_line_up():
    hits = buynow.check(_fund_report(), [])
    assert [h["symbol"] for h in hits] == ["QQQ"]          # VOO is in Fear: traders expect more falls
    assert hits[0]["kind"] == "fund"
    assert any("14%" in r for r in hits[0]["reasons"])
    assert hits[0]["risks"]


def test_fund_needs_a_real_correction():
    report = _fund_report(indexes={"SPY": {"off_high": -0.06, "ret_1m": -0.05}, "VIX": {"ret_1m": 0.60, "ret_1d": 0}})
    assert buynow.check(report, []) == []


def test_fund_needs_panic():
    report = _fund_report(indexes={"SPY": {"off_high": -0.12, "ret_1m": -0.09}, "VIX": {"ret_1m": 0.10, "ret_1d": 0}})
    assert buynow.check(report, []) == []


def test_fund_blocked_when_google_points_down():
    report = _fund_report(predictions={"QQQ": {"mid": 580.0, "last": 600.0}})
    assert buynow.check(report, []) == []


def test_missing_prediction_never_blocks_but_is_said():
    hits = buynow.check(_fund_report(predictions={}), [])
    assert [h["symbol"] for h in hits] == ["QQQ"]
    assert any("not installed" in r or "no prediction" in r.lower() for r in hits[0]["reasons"])


def test_excluded_fund_is_skipped():
    assert buynow.check(_fund_report(), [], excluded={"QQQ"}) == []


def _floor_closes():
    """A year of closes that bounced off ~100 three times and sit at 101 today."""
    out = []
    for leg in range(3):
        out += [130 - i for i in range(30)] + [100.0] + [100 + i for i in range(1, 31)]
    out += [130 - i * 1.0 for i in range(29)] + [101.0]
    return [float(x) for x in out]


def _stock_report(**over):
    pick = {"symbol": "ACME", "name": "Acme", "sector": "Industrials", "entry": 101.0, "stop": 95.0, "target": 113.0,
            "until": "2026-12-18", "reasons": []}
    report = _fund_report(indexes={"SPY": {"off_high": -0.03, "ret_1m": 0.01}, "VIX": {"ret_1m": 0.0, "ret_1d": 0.0}},
                          swing=[pick], levels={"ACME": {"closes": _floor_closes(), "levels": []}},
                          predictions={"ACME": {"mid": 106.0, "last": 101.0}})
    report.update(over)
    return report


def _score(**over):
    row = {"symbol": "ACME", "score": 80, "raw_score": 84, "thin": False, "breaking": {"deductions": []},
           "value": {"ok": True, "bear": 120.0, "base": 160.0, "bull": 220.0, "band": "below bear", "flags": []}}
    row.update(over)
    return row


def test_floor_finder_sees_three_bounces():
    floor = levels.floor_near(_floor_closes())
    assert floor and floor["touches"] >= 3 and abs(floor["level"] - 100) < 1


def test_stock_fires_when_quality_cheap_floor_and_timing_agree():
    hits = buynow.check(_stock_report(), [_score()])
    assert [h["symbol"] for h in hits] == ["ACME"]
    assert hits[0]["kind"] == "stock"


def test_stock_needs_high_score_after_claude():
    assert buynow.check(_stock_report(), [_score(score=70)]) == []
    assert buynow.check(_stock_report(), [_score(breaking=None)]) == []      # Claude hasn't argued against it yet


def test_stock_needs_price_under_the_bear_case():
    assert buynow.check(_stock_report(), [_score(value={"ok": True, "bear": 90.0, "base": 120.0, "bull": 150.0,
                                                        "band": "in range", "flags": []})]) == []


def test_stock_needs_a_floor_right_under_it():
    flat = [float(100 + (i % 7)) for i in range(250)]
    assert buynow.check(_stock_report(levels={"ACME": {"closes": flat, "levels": []}}), [_score()]) == []


def test_stock_blocked_in_a_storm():
    storm = {"SPY": {"off_high": -0.08, "ret_1m": -0.07}, "VIX": {"ret_1m": 0.2, "ret_1d": 0.08}}
    assert buynow.check(_stock_report(indexes=storm), [_score()]) == []


def test_banner_is_red_buy_now_with_reasons_and_empty_when_nothing_fires():
    from market_skew.ui import buynow_view
    html = buynow_view.block(buynow.check(_fund_report(), []))
    assert "BUY NOW" in html and "buynow-word" in html and "QQQ" in html and "What could still go wrong" in html
    assert buynow_view.block([]) == ""
