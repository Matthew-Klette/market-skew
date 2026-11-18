from market_skew import fundamentals as f


def quarters(start_year, values, first_quarter=1):
    out, year, q = {}, start_year, first_quarter
    for v in values:
        out[f"{year}Q{q}"] = v
        q += 1
        if q == 5:
            year, q = year + 1, 1
    return out


def company(**over):
    rev = quarters(2023, [100, 100, 100, 100, 110, 110, 110, 110, 130, 130, 130, 130])  # 2023Q1..2025Q4 (12 quarters)
    base = {
        "q": {"revenue": rev, "gross": {k: v * 0.4 for k, v in rev.items()}},
        "a": {"ocf": {"2022": 50, "2023": 60, "2024": 80, "2025": 120}, "capex": {"2022": 10, "2023": 10, "2024": 20, "2025": 20},
              "revenue": {"2022": 380, "2023": 400, "2024": 440, "2025": 520}},
        "i": {"cash": {"2025Q4": 300}, "debt": {"2025Q4": 200},
              "shares_out": {"2024Q4": 100, "2025Q4": 98}},
    }
    return {**base, **over}


def test_ttm_growth_and_acceleration():
    m = f.compute(company())
    assert m["as_of"] == "2025Q4"
    assert m["ttm_revenue"] == 520
    assert round(m["revenue_growth"], 4) == round(130 / 110 - 1, 4)
    assert round(m["revenue_growth_prior"], 4) == round(110 / 100 - 1, 4)
    assert m["accelerating"] is True


def test_decelerating_when_growth_falls():
    rev = quarters(2023, [100] * 4 + [150] * 4 + [160] * 4)
    m = f.compute(company(q={"revenue": rev}))
    assert m["accelerating"] is False


def test_margins_fcf_cash_and_debt():
    m = f.compute(company())
    assert round(m["gross_margin"], 4) == 0.4
    assert m["fcf"] == 100  # annual fallback: 120 - 20
    assert round(m["fcf_margin"], 4) == round(100 / 520, 4)
    assert m["net_cash"] == 100
    assert m["debt_to_fcf"] == 2.0
    assert m["fcf_by_year"] == {"2022": 40, "2023": 50, "2024": 60, "2025": 100}


def test_quarterly_cash_flow_is_summed_when_every_quarter_exists():
    q = company()["q"] | {"ocf": quarters(2024, [10] * 8), "capex": quarters(2024, [2] * 8)}
    m = f.compute(company(q=q))
    assert m["fcf"] == 32


def test_missing_q4_is_derived_from_the_annual_figure():
    rev = quarters(2024, [100, 100, 100, 100, 120, 120, 120])  # no 2025Q4 and no 2024Q4... 2024Q4 present, 2025Q4 missing
    m = f.compute({"q": {"revenue": rev}, "a": {"revenue": {"2025": 500}}, "i": {}})
    assert m["as_of"] == "2025Q4"
    assert m["ttm_revenue"] == 500  # 120*3 + (500-360)=140 -> 360+140


def test_share_change_and_fcf_per_share_growth():
    m = f.compute(company())
    assert round(m["share_change"], 4) == -0.02
    assert m["fcf_per_share_growth"] is not None


def test_dilution_from_diluted_average_when_no_cover_count():
    shares = quarters(2024, [100] * 4 + [105] * 4)
    m = f.compute(company(i={"cash": {}, "debt": {}}, q=company()["q"] | {"shares_avg": shares}))
    assert round(m["share_change"], 4) == 0.05


def test_missing_concepts_give_none_not_errors():
    m = f.compute({"q": {"revenue": quarters(2025, [10, 11])}, "a": {}, "i": {}})
    assert m["gross_margin"] is None and m["fcf"] is None and m["net_cash"] is None
    assert m["revenue_growth"] is None and m["accelerating"] is None
    assert m["depth"] == "Thin"


def test_no_revenue_means_no_row():
    assert f.compute({"q": {}, "a": {}, "i": {}}) is None
    assert f.compute({}) is None


def test_annual_only_company_still_gets_growth():
    m = f.compute({"q": {}, "a": {"revenue": {"2022": 100, "2023": 120, "2024": 150}}, "i": {}})
    assert round(m["revenue_growth"], 4) == 0.25 and m["accelerating"] is True
    assert m["ttm_revenue"] == 150


def test_negative_fcf_has_no_debt_to_fcf():
    m = f.compute(company(a={"ocf": {"2025": 10}, "capex": {"2025": 30}, "revenue": {"2025": 520}}))
    assert m["fcf"] == -20 and m["debt_to_fcf"] is None


def test_depth_levels():
    assert f.depth(8, 4) == "Deep"
    assert f.depth(12, 3) == "Medium"
    assert f.depth(4, 0) == "Medium"
    assert f.depth(3, 6) == "Thin"


def test_cash_flow_pieces_and_per_share_history_are_exposed():
    m = f.compute(company())
    assert m["ocf"] == 120 and m["capex"] == 20 and m["fcf"] == 100
    assert m["shares"] == 98
    assert set(m["fcf_ps_by_year"]) <= {"2022", "2023", "2024", "2025"} and m["fcf_ps_by_year"]


def test_share_averages_are_not_derived_by_subtraction():
    # KO-like: annual average 4300, Q1..Q3 around 4320 each -> subtraction would give a negative Q4
    shares = {"2025Q1": 4320, "2025Q2": 4322, "2025Q3": 4318}
    q = company()["q"] | {"shares_avg": shares}
    m = f.compute(company(q=q, a=company()["a"] | {"shares_avg": {"2025": 4300}}, i={"cash": {}, "debt": {}}))
    assert m["shares"] is None or m["shares"] > 0
    assert f._quarters(shares, {"2025": 4300}, additive=False) == {f.qindex(k): v for k, v in shares.items()}


def test_non_positive_share_counts_are_never_used():
    q = company()["q"] | {"shares_avg": {"2025Q4": -5.0, "2024Q4": 0.0}}
    m = f.compute(company(q=q, i={"cash": {}, "debt": {}}))
    assert m["shares"] is None and m["share_change"] is None
    data = company(i={"shares_out": {"2025Q4": -3, "2024Q4": 100}})
    assert f.compute(data)["shares"] is None


def test_fcf_per_share_ignores_non_positive_counts():
    data = company(i={"shares_out": {"2025Q1": -4, "2025Q2": 100, "2025Q3": 100, "2025Q4": 100}})
    m = f.compute(data)
    assert m["fcf_ps_by_year"]["2025"] == 1.0


def test_annual_fallback_fcf_margin_uses_that_fiscal_years_revenue():
    # latest quarter 2025Q4 -> TTM revenue 520, but FCF year is 2024 when 2025 isn't tagged
    data = company(a={"ocf": {"2024": 80}, "capex": {"2024": 20}, "revenue": {"2024": 440, "2025": 520}})
    m = f.compute(data)
    assert m["fcf"] == 60
    assert round(m["fcf_margin"], 4) == round(60 / 440, 4)
