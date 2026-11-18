import numpy as np
import pandas as pd
import pytest

from market_skew import sentinel, valuation as v
from tests.test_sentinel import metrics

M = metrics(fcf=2.5e9, shares=1e9, ttm_revenue=1e10, revenue_growth=0.10, net_cash=1e9, depth="Deep",
            fcf_by_year={"2023": 2.4e9, "2024": 2.5e9, "2025": 2.6e9})


def val(m=None, price=50.0, sector="Info Tech", **over):
    return v.value({**(m or M), **over}, price, sector)


def test_risk_free_is_the_sentinel_constant():
    assert v.RISK_FREE is sentinel.TREASURY_10Y


def test_gordon_terminal_value_matches_the_formula():
    c = v._case(100.0, 0.05, 0.025, 0.09)
    flows = 100.0 * np.cumprod(1 + np.linspace(0.05, 0.035, 10))
    tv = flows[-1] * 1.025 / (0.09 - 0.025)
    pv = sum(f / 1.09 ** (i + 1) for i, f in enumerate(flows))
    assert c["pv_tv"] == pytest.approx(tv / 1.09 ** 10)
    assert c["ev"] == pytest.approx(pv + tv / 1.09 ** 10)
    assert c["tv_share"] == pytest.approx((tv / 1.09 ** 10) / c["ev"])


def test_growth_fades_over_ten_years():
    assert v.YEARS == 10 and v.EQUITY_PREMIUM == 0.045


def test_bear_and_bull_shift_free_cash_by_ten_percent():
    assert v.SCENARIOS["bear"][3] == -0.10 and v.SCENARIOS["bull"][3] == 0.10 and v.SCENARIOS["base"][3] == 0.0
    r = val()
    plain = v._case(2.5e9, r["g1"], 0.025, r["rate"])
    assert plain["ev"] > 0 and r["bear"] < r["base"] < r["bull"]


def test_measured_beta_changes_the_range_and_is_clamped():
    assert val()["beta"] == 1.0
    assert v.value(M, 50.0, "Info Tech", beta=1.4)["base"] < val()["base"]
    idx = pd.bdate_range("2024-01-01", periods=520)
    mkt = pd.Series(100 * np.cumprod(1 + np.where(np.arange(520) % 2 == 0, 0.01, -0.008)), index=idx)
    steady = v.beta_from_closes(mkt, mkt)
    assert steady == pytest.approx(1.0)
    wild = mkt.pct_change().fillna(0) * 5
    assert v.beta_from_closes(100 * (1 + wild).cumprod(), mkt) == 1.6
    calm = mkt.pct_change().fillna(0) * 0.1
    assert v.beta_from_closes(100 * (1 + calm).cumprod(), mkt) == 0.6
    assert v.beta_from_closes(mkt.head(100), mkt.head(100)) is None


def test_price_above_bull_shows_the_growth_the_price_assumes():
    r = val(price=500.0)
    assert r["band"] == "above bull" and r["implied_growth"] is not None
    assert "the price assumes about" in r["position"] and "growth a year for 10 years" in r["position"]
    c = v._case(2.5e9, r["implied_growth"], 0.025, r["rate"], flat=True)
    assert (c["ev"] + 1e9) / 1e9 == pytest.approx(500.0, rel=1e-3)
    assert val()["implied_growth"] is None


def test_implied_growth_gives_up_beyond_one_hundred_percent():
    r = val(price=1e9)
    assert r["implied_growth"] is None and "more than 100%" in r["position"]


def test_normalised_cash_when_latest_is_over_forty_percent_off_average():
    assert v.DEVIATION == 0.40
    assert "3-year average" in val(fcf=3.6e9)["assumptions"][0]      # 44% above the 2.5B average
    assert "3-year average" not in val(fcf=3.3e9)["assumptions"][0]  # 32% above


def test_range_is_ordered_bear_base_bull():
    r = val()
    assert r["ok"] and r["bear"] < r["base"] < r["bull"]


def test_discount_rate_blends_equity_and_after_tax_debt():
    m = {**M, "debt": 1e9, "cash": 2e9}
    equity = 50.0 * 1e9
    expect = equity / (equity + 1e9) * (0.043 + 0.045) + 1e9 / (equity + 1e9) * 0.06 * 0.79
    assert v.discount_rate(m, 50.0) == pytest.approx(expect)


def test_net_cash_is_added_and_net_debt_subtracted():
    rich, poor = val(net_cash=5e9), val(net_cash=-5e9)
    assert rich["base"] > val()["base"] > poor["base"]


def test_growth_is_clamped():
    assert val(revenue_growth=0.9)["g1"] == 0.25
    assert val(revenue_growth=-0.4)["g1"] == -0.05


def test_unusual_latest_year_uses_three_year_average():
    r = val(fcf=6e9)
    assert any("3-year average" in f for f in r["flags"])
    assert "3-year average" in r["assumptions"][0]
    assert val()["flags"] == [] or all("average" not in f for f in val()["flags"])


@pytest.mark.parametrize("sector", ["Financials", "Real Estate"])
def test_banks_and_property_are_skipped(sector):
    r = val(sector=sector)
    assert r["ok"] is False and r["reason"]


def test_gates_skip_with_a_reason():
    assert val(fcf=-5.0)["ok"] is False
    assert val(fcf=0.0)["ok"] is False
    assert "filings" in val(depth="Thin")["reason"]
    assert val(revenue_growth=None)["ok"] is False
    assert val(shares=None)["ok"] is False


def test_skips_when_discount_rate_does_not_beat_growth(monkeypatch):
    monkeypatch.setattr(v, "RISK_FREE", 0.0)
    monkeypatch.setattr(v, "EQUITY_PREMIUM", 0.0)
    monkeypatch.setattr(v, "DEBT_COST", 0.0)
    r = val()
    assert r["ok"] is False and "discount rate" in r["reason"]


def test_far_future_flag_when_terminal_value_dominates(monkeypatch):
    monkeypatch.setattr(v, "EQUITY_PREMIUM", 0.0)  # a low discount rate pushes value past year ten
    r = val(revenue_growth=0.25, fcf=1e8, fcf_by_year={})
    assert r["tv_share"] > 0.85 and v.LATE in r["flags"]


def test_check_inputs_flag_when_terminal_value_is_small(monkeypatch):
    monkeypatch.setattr(v, "SCENARIOS", {**v.SCENARIOS, "base": (-0.5, 0.0, 0.0, 0.0), "bear": (-0.5, -0.03, 0.01, -0.1), "bull": (-0.4, 0.03, -0.01, 0.1)})
    assert v.CHECKS in val()["flags"]


@pytest.mark.parametrize("price,text,band", [(10.0, "below the bear case", "below bear"), (None, None, None)])
def test_position_words(price, text, band):
    if price is None:
        assert v.position(1, 0, 2, 3) == "price is between the bear and base cases"
        assert v.position(2.5, 0, 2, 3) == "price is between the base and bull cases"
        assert v.position(9, 0, 2, 3) == "price is above the bull case"
        return
    r = val(price=price)
    assert text in r["position"] and r["band"] == band


def test_band_is_in_range_between_bear_and_bull():
    assert v.band(5, 1, 10) == "in range" and v.band(11, 1, 10) == "above bull"


def test_for_row_reads_the_sentinel_row():
    row = {"metrics": M, "px": {"close": 50.0}, "sector": "Info Tech"}
    assert v.for_row(row) == val()


def test_never_a_single_target():
    r = val()
    assert {"bear", "base", "bull"} <= set(r) and "target" not in r
