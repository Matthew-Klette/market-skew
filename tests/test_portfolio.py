import pytest

from market_skew import portfolio


def test_target_weights_split_each_sleeve_over_its_funds_and_sum_to_one():
    w = portfolio.target_weights({"broad": 0.7, "growth": 0.2, "stock": 0.1})
    assert sum(w.values()) == pytest.approx(1) and w["VOO"] == pytest.approx(0.7 / 3) and w["STXNDQ"] == pytest.approx(0.1)
    assert w["QQQ"] == pytest.approx(0.1 + 0.1)  # growth share plus single stocks modelled as QQQ


def test_holding_weights_use_rand_values_and_model_stocks_as_qqq():
    vals = [{"symbol": "VOO", "rand": 600.0}, {"symbol": "KO", "rand": 200.0}, {"symbol": "SYG500", "rand": 200.0}, {"symbol": "X", "rand": None}]
    w = portfolio.holding_weights(vals)
    assert w == {"VOO": 0.6, "QQQ": 0.2, "SYG500": 0.2} and portfolio.holding_weights([]) == {}


def test_series_is_the_weighted_sum_over_months_every_fund_has():
    returns = {"VOO": {"2026-01": 0.10, "2026-02": 0.0}, "QQQ": {"2026-02": 0.20}}
    assert portfolio.series(returns, {"VOO": 0.5, "QQQ": 0.5}) == [("2026-02", pytest.approx(0.10))]


def test_fee_blends_jse_and_dollar_paths():
    assert portfolio.fee_pct({"SYG500": 1.0}) == pytest.approx(0.0025)
    both = portfolio.fee_pct({"SYG500": 0.5, "VOO": 0.5})
    assert 0.0025 < both < 0.02 and portfolio.fee_pct({"VOO": 1.0}) == pytest.approx(0.0184, abs=0.0005)
