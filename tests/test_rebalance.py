import pytest

from market_skew import allocation, rebalance as r

HOLD = [{"symbol": "VOO", "account": "usd", "units": 10}, {"symbol": "QQQ", "account": "usd", "units": 10},
        {"symbol": "AAPL", "account": "usd", "units": 5}, {"symbol": "SYG500", "account": "tfsa", "units": 100}]
CLOSES = {"VOO": 500.0, "QQQ": 600.0, "AAPL": 200.0}
QUOTES = {"SYG500": {"price": 20.0}}


def test_sleeve_of_known_funds_and_default_stock():
    assert r.sleeve_of("VOO") == r.sleeve_of("SYG500") == r.sleeve_of("SCHD") == "broad"
    assert r.sleeve_of("QQQ") == r.sleeve_of("STXNDQ") == r.sleeve_of("VOOG") == "growth"
    assert r.sleeve_of("AAPL") == "stock"


def test_values_convert_usd_at_the_cached_rate_and_skip_unpriced():
    vals = r.values(HOLD + [{"symbol": "ZZZ", "account": "usd", "units": 1}, {"symbol": "KO", "account": "usd", "units": None}],
                    CLOSES, QUOTES, rate=18.0)
    by = {v["symbol"]: v for v in vals}
    assert by["VOO"]["rand"] == 10 * 500 * 18 and by["SYG500"]["rand"] == 2000
    assert by["ZZZ"]["rand"] is None and by["KO"]["rand"] is None


def test_values_without_a_rate_leave_usd_unvalued():
    by = {v["symbol"]: v for v in r.values(HOLD, CLOSES, QUOTES, rate=None)}
    assert by["VOO"]["rand"] is None and by["SYG500"]["rand"] == 2000


def test_actual_weights_sum_to_one_and_none_without_units():
    vals = r.values(HOLD, CLOSES, QUOTES, 18.0)
    w = r.weights(vals)
    assert sum(w["weights"].values()) == pytest.approx(1.0)
    assert r.weights([])["total"] == 0 and r.weights([])["weights"] == {}


def test_drift_uses_min_for_broad_and_max_for_others():
    d = {x["sleeve"]: x for x in r.drift({"broad": 0.5, "growth": 0.4, "stock": 0.1}, r.DEFAULT_TARGETS)}
    assert d["broad"]["drift"] == pytest.approx(-0.2) and d["broad"]["state"] == "under"
    assert d["growth"]["drift"] == pytest.approx(0.2) and d["growth"]["state"] == "over"
    assert d["stock"]["state"] == "ok"
    ok = {x["sleeve"]: x for x in r.drift({"broad": 0.75, "growth": 0.15, "stock": 0.1}, r.DEFAULT_TARGETS)}
    assert all(x["state"] == "ok" for x in ok.values()) and ok["broad"]["drift"] == pytest.approx(0.05)


def test_cash_flow_goes_to_underweight_and_never_sells():
    out = r.cash_flow({"broad": 500.0, "growth": 400.0, "stock": 100.0}, {"broad": .7, "growth": .2, "stock": .1}, 1000)
    got = {x["sleeve"]: x["rand"] for x in out}
    assert got["broad"] > got["stock"] > 0 and got.get("growth", 0) == 0
    assert sum(got.values()) == pytest.approx(1000)
    assert all(v >= 0 for v in got.values())


def test_cash_flow_not_enough_money_is_shared_by_shortfall():
    out = {x["sleeve"]: x["rand"] for x in r.cash_flow({"broad": 0.0, "growth": 1000.0, "stock": 0.0}, {"broad": .7, "growth": .2, "stock": .1}, 100)}
    assert out["broad"] == pytest.approx(87.5) and out["stock"] == pytest.approx(12.5)


def test_cash_flow_all_at_target_splits_by_target():
    out = {x["sleeve"]: x["rand"] for x in r.cash_flow({"broad": 700.0, "growth": 200.0, "stock": 100.0}, {"broad": .7, "growth": .2, "stock": .1}, 100)}
    assert out["broad"] == pytest.approx(70)


def test_note_and_tilt_only_above_five_points():
    d = r.drift({"broad": 0.6, "growth": 0.32, "stock": 0.08}, r.DEFAULT_TARGETS)
    note = r.note(d)
    assert "growth funds are 12pp over target" in note and "VOO and SCHD" in note
    tilt = r.tilt(d)
    assert tilt["QQQ"] < 1 < tilt["VOO"] and tilt["VOO"] == tilt["SCHD"]
    calm = r.drift({"broad": 0.72, "growth": 0.2, "stock": 0.08}, r.DEFAULT_TARGETS)
    assert r.note(calm) is None and r.tilt(calm) == {}


def test_allocation_tilt_shifts_between_funds_and_keeps_floors_and_total():
    sig = {k: {"timing": "wait", "label": "w", "why": "x"} for k in ("QQQ", "SCHD", "VOO")}
    base = {x["symbol"]: x["rand"] for x in allocation.allocate(5000, sig, [], "mine", 17.0)}
    tilted = {x["symbol"]: x["rand"] for x in allocation.allocate(5000, sig, [], "mine", 17.0, tilt={"QQQ": 0.5, "VOO": 1.5, "SCHD": 1.5})}
    assert tilted["QQQ"] < base["QQQ"] and tilted["VOO"] > base["VOO"]
    assert sum(tilted.values()) == 5000 and min(tilted.values()) >= 750
    assert allocation.allocate(5000, sig, [], "mine", 17.0, tilt={}) == allocation.allocate(5000, sig, [], "mine", 17.0)


def test_clean_targets_validates_percent_and_defaults():
    assert r.clean_targets({"broad": 70, "growth": 20, "stock": 10}) == {"broad": 0.7, "growth": 0.2, "stock": 0.1}
    assert r.clean_targets({"broad": 80, "growth": 20, "stock": 10}) is None
    assert r.clean_targets({"broad": "x", "growth": 20, "stock": 10}) is None
    assert r.clean_targets({"broad": 70, "growth": -5, "stock": 35}) is None
    assert r.targets_from({}) == r.DEFAULT_TARGETS


def test_all_six_funds_count_as_etfs_and_single_stocks_do_not():
    assert set(r.ETFS) == {"VOO", "SYG500", "SCHD", "QQQ", "STXNDQ", "VOOG"}
    vals = [{"symbol": s, "rand": 100.0, "sleeve": r.sleeve_of(s)} for s in sorted(r.ETFS)]
    assert r.etf_share(vals)["share"] == 1.0
    assert r.etf_share([{"symbol": "AAPL", "rand": 100.0, "sleeve": "stock"}])["share"] == 0.0


def test_etf_share_is_a_share_of_valued_holdings_against_the_70_to_75_rule():
    mix = lambda etf, stock: [{"symbol": "VOO", "rand": etf, "sleeve": "broad"}, {"symbol": "NVDA", "rand": stock, "sleeve": "stock"},
                              {"symbol": "ZZZ", "rand": None, "sleeve": "stock"}]
    out = r.etf_share(mix(720.0, 280.0))
    assert out["share"] == 0.72 and out["status"] == "ok" and out["etf"] == 720.0 and out["total"] == 1000.0
    assert (r.ETF_RULE_LOW, r.ETF_RULE_HIGH) == (0.70, 0.75)
    assert r.etf_share(mix(600.0, 400.0))["status"] == "low"
    assert r.etf_share(mix(900.0, 100.0))["status"] == "high"
    assert r.etf_share(mix(700.0, 300.0))["status"] == "ok" and r.etf_share(mix(750.0, 250.0))["status"] == "ok"


def test_etf_share_is_none_when_nothing_is_valued():
    assert r.etf_share([]) is None and r.etf_share([{"symbol": "VOO", "rand": None, "sleeve": "broad"}]) is None
