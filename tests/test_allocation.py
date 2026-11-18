from market_skew import allocation


def fund(kind, label=None):
    return {"timing": kind, "label": label or kind, "why": "because."}


ALL = {"QQQ": fund("wait"), "SCHD": fund("wait"), "VOO": fund("wait"), "VOOG": fund("add")}
PICKS = [dict(symbol="AAA", name="A", entry=10.0, stop=9.0, target=12.0, until="2026-12-16", reasons=["r"]),
         dict(symbol="BBB", name="B", entry=10.0, stop=9.0, target=12.0, until="2026-12-16", reasons=["r"]),
         dict(symbol="CCC", name="C", entry=10.0, stop=9.0, target=12.0, until="2026-12-16", reasons=["r"])]


def by(lines):
    return {x["symbol"]: x for x in lines}


def test_total_is_exactly_the_input_and_whole_rand():
    for amount in (5000, 4999, 1234, 777, 1):
        lines = allocation.allocate(amount, ALL, PICKS, rate=17.0)
        assert sum(x["rand"] for x in lines) == amount
        assert all(isinstance(x["rand"], int) for x in lines)


def test_floors_hold_even_when_all_funds_are_hold():
    sig = {k: fund("hold") for k in ("QQQ", "SCHD", "VOO")}
    lines = by(allocation.allocate(10000, sig, PICKS))
    for s in ("QQQ", "SCHD", "VOO"):
        assert lines[s]["rand"] >= 1500


def test_all_hold_splits_funds_evenly():
    sig = {k: fund("hold") for k in ("QQQ", "SCHD", "VOO")}
    lines = by(allocation.allocate(10000, sig, PICKS))
    rands = [lines[s]["rand"] for s in sig]
    assert max(rands) - min(rands) <= 1


def test_tilt_goes_to_the_add_fund_and_away_from_hold():
    sig = {"QQQ": fund("add"), "SCHD": fund("hold"), "VOO": fund("wait")}
    lines = by(allocation.allocate(10000, sig, PICKS))
    assert lines["QQQ"]["rand"] > lines["VOO"]["rand"] > lines["SCHD"]["rand"] >= 1500


def test_single_stocks_capped_at_30_percent_top_two_picks():
    lines = allocation.allocate(10000, ALL, PICKS)
    stocks = [x for x in lines if x["kind"] == "stock"]
    assert [x["symbol"] for x in stocks] == ["AAA", "BBB"] and sum(x["rand"] for x in stocks) == 3000
    assert stocks[0]["reason"].startswith("Pick: buy near $10.00, stop $9.00, target $12.00, give it until 2026-12-16")


def test_no_candidates_returns_cap_money_to_funds_by_tilt():
    sig = {"QQQ": fund("add"), "SCHD": fund("hold"), "VOO": fund("wait")}
    lines = allocation.allocate(10000, sig, [])
    assert all(x["kind"] != "stock" for x in lines) and sum(x["rand"] for x in lines) == 10000
    assert by(lines)["QQQ"]["rand"] > 4500


def test_voog_never_gets_money():
    assert "VOOG" not in by(allocation.allocate(10000, ALL, PICKS))


def test_missing_signal_counts_as_wait_and_lines_carry_costs_and_reason():
    lines = by(allocation.allocate(5000, {}, [], rate=17.5))
    q = lines["QQQ"]
    assert q["fee"] > 0 and q["invested"] < q["rand"] and abs(q["dollars"] - q["rand"] / 17.5) < 1e-9
    assert q["reason"] and abs(lines["QQQ"]["rand"] - lines["VOO"]["rand"]) <= 1


def test_reasons_by_signal():
    sig = {"QQQ": fund("add", "Good time to add"), "SCHD": fund("hold"), "VOO": fund("wait")}
    lines = by(allocation.allocate(5000, sig, []))
    assert lines["QQQ"]["reason"].startswith("Good time to add:")
    assert lines["SCHD"]["reason"].startswith("Floor amount: you asked to keep adding to this")


def test_zero_amount_gives_zero_lines():
    assert all(x["rand"] == 0 for x in allocation.allocate(0, ALL, PICKS))
