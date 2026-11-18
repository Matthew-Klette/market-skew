from market_skew import sentinel as s


def metrics(**over):
    base = {"as_of": "2025Q4", "ttm_revenue": 1000.0, "revenue_growth": 0.25, "revenue_growth_prior": 0.15, "accelerating": True,
            "gross_margin": 0.6, "fcf": 250.0, "fcf_margin": 0.25, "net_cash": 100.0, "debt_to_fcf": 0.5, "share_change": -0.02,
            "fcf_per_share_growth": 0.2, "ocf": 300.0, "capex": 50.0, "shares": 100.0, "depth": "Deep",
            "fcf_ps_by_year": {"2021": 1.0, "2022": 1.25, "2023": 1.5, "2024": 2.0, "2025": 2.5}}
    return {**base, **over}


def px(**over):
    base = {"name": "Acme", "sector": "Info Tech", "market_cap": 5000.0, "close": 50.0, "ret_1m": 0.05, "ret_3m": 0.10,
            "bet_z": 1.0, "bucket": "Chase",
            "year_closes": {"2021": 40.0, "2022": 45.0, "2023": 60.0, "2024": 90.0, "2025": 120.0}}
    return {**base, **over}


def peers(n=6):
    """n other Info Tech names with ordinary numbers so sector medians and percentiles exist."""
    f = {f"P{i}": metrics(fcf_margin=0.02 * i, fcf=20.0 * i) for i in range(n)}
    p = {f"P{i}": px(name=f"Peer {i}", ret_1m=0.0, ret_3m=0.0, close=100.0, market_cap=3000.0) for i in range(n)}
    return f, p


def one(symbol="ACME", m=None, x=None, previous=None):
    f, p = peers()
    f[symbol], p[symbol] = m or metrics(), x or px()
    return {r["symbol"]: r for r in s.score_all(f, p, previous)}[symbol]


def test_label_bands():
    assert [s.label(v) for v in (100, 80, 79, 65, 64, 0)] == ["WATCH", "WATCH", "OK", "OK", "PASS", "PASS"]


def test_pillars_respect_their_caps_and_sum_to_the_score():
    r = one()
    caps = {k: v["max"] for k, v in r["pillars"].items()}
    assert caps == {"growing": 35, "protected": 25, "survive": 25, "street": 15}
    assert all(0 <= v["pts"] <= v["max"] for v in r["pillars"].values())
    assert r["score"] == sum(v["pts"] for v in r["pillars"].values())
    assert r["score"] >= 80 and r["label"] == "WATCH"


def test_thirty_percent_growth_after_fifty_scores_below_thirty_after_ten():
    slowing = one(m=metrics(revenue_growth=0.30, revenue_growth_prior=0.50, accelerating=False))
    speeding = one(m=metrics(revenue_growth=0.30, revenue_growth_prior=0.10, accelerating=True))
    assert speeding["pillars"]["growing"]["pts"] > slowing["pillars"]["growing"]["pts"]
    assert slowing["accelerating"] is False and speeding["accelerating"] is True


def test_dilution_costs_points():
    assert one(m=metrics(share_change=0.06))["pillars"]["growing"]["pts"] < one(m=metrics(share_change=-0.02))["pillars"]["growing"]["pts"]


def test_capex_above_operating_cash_flow_is_flagged_and_scores_zero():
    r = one(m=metrics(ocf=100.0, capex=150.0, fcf=-50.0, fcf_margin=-0.05))
    part = {p["key"]: p for p in r["pillars"]["protected"]["parts"]}["capex"]
    assert part["pts"] == 0
    assert any("more than it makes" in f for f in r["flags"])


def test_survive_pillar_rewards_net_cash_and_punishes_burning_cash():
    strong = one()["pillars"]["survive"]["pts"]
    weak = one(m=metrics(net_cash=-600.0, debt_to_fcf=None, fcf=-20.0, fcf_margin=-0.02, ocf=10.0, capex=30.0))["pillars"]["survive"]["pts"]
    assert strong == 25 and weak <= 2


def test_cash_yield_is_compared_with_treasuries():
    r = one()  # 250 / 5000 = 5%
    assert round(r["cash_yield"], 4) == 0.05 and r["beats_treasury"] is True
    low = one(x=px(market_cap=50000.0))
    assert round(low["cash_yield"], 4) == 0.005 and low["beats_treasury"] is False


def test_price_vs_growth_is_pfcf_over_growth():
    r = one()  # price 50 / (250/100 per share) = 20x; growth 25 -> 0.8
    assert round(r["pfcf"], 2) == 20.0 and round(r["peg"], 2) == 0.8 and r["peg_label"] == "cheap"
    assert one(m=metrics(revenue_growth=0.05))["peg_label"] == "rich"
    assert one(m=metrics(revenue_growth=-0.02))["peg"] is None


def test_own_history_cheap_or_rich_percent():
    r = one()  # history P/FCF: 40, 36, 40, 45, 48 -> median 40; now 20 -> -50% cheap
    assert round(r["own_history_pct"], 2) == -0.5 and r["own_history_label"] == "cheap"
    rich = one(x=px(close=100.0))  # now 40 vs median 40 -> fair... push higher
    assert rich["own_history_label"] == "fair"
    assert one(x=px(close=140.0))["own_history_label"] == "rich"
    assert [h["year"] for h in r["history"]] == ["2021", "2022", "2023", "2024", "2025"]
    assert one(x=px(year_closes={}))["own_history_pct"] is None


def test_sector_peer_comparison_uses_median_pfcf():
    r = one()
    assert r["peer_pct"] is not None and r["peer_pct"] < 0  # 20x against peers at 100 / (fcf per share)


def test_with_sector_or_alone():
    f, p = peers()
    f["A"], p["A"] = metrics(), px(ret_1m=0.15)   # sector median 1M is 0.0 -> +15pp
    f["B"], p["B"] = metrics(), px(ret_1m=0.01)
    f["C"], p["C"] = metrics(), px(ret_1m=-0.12)
    out = {r["symbol"]: r for r in s.score_all(f, p)}
    assert out["A"]["together"] == "alone +15pp" and out["B"]["together"] == "with sector" and out["C"]["together"] == "alone -12pp"


def test_score_change_against_the_last_run():
    assert one(previous={"ACME": 70})["change"] == one()["score"] - 70
    assert one()["change"] is None


def test_thin_company_is_flagged_not_hidden():
    r = one(m=metrics(depth="Thin"))
    assert r["thin"] is True and r["depth"] == "Thin" and isinstance(r["score"], int)


def test_a_sparse_company_does_not_crash_and_rescales():
    r = one(m={"as_of": "2025Q4", "ttm_revenue": 100.0, "revenue_growth": 0.1, "depth": "Thin"}, x={"sector": "Info Tech", "close": 10.0})
    assert 0 <= r["score"] <= 100 and r["cash_yield"] is None and r["own_history_pct"] is None


def test_percentile_within_sector():
    r = one()  # peers' margins 0%..10%; this one is 25%
    part = {p["key"]: p for p in r["pillars"]["protected"]["parts"]}["sector_rank"]
    assert part["pts"] == 5


def test_read_this_first_has_four_labelled_sentences_from_the_numbers():
    r = one()
    tags = [t.split(":")[0] for t in r["summary"]]
    assert tags == ["QUALITY", "DIRECTION", "PRICE", "THE BET"]
    assert "25 cents" in r["summary"][0] and "speeding up" in r["summary"][1]


def test_ranked_best_first():
    f, p = peers()
    f["ACME"], p["ACME"] = metrics(), px()
    rows = s.score_all(f, p)
    assert rows[0]["symbol"] == "ACME" and [r["rank"] for r in rows] == list(range(1, len(rows) + 1))


def test_a_pillar_with_too_little_known_scores_zero_and_is_listed_as_a_gap():
    r = one(m=metrics(net_cash=None, debt_to_fcf=None, fcf=None, fcf_margin=None, ocf=None, capex=None))
    assert r["pillars"]["survive"]["pts"] == 0 and "balance sheet" in r["gaps"]
    assert one()["gaps"] == []
