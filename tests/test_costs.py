import pytest

from market_skew import costs


def test_usd_trade_rate_is_brokerage_plus_clearing_with_vat():
    assert costs.RATES["usd_buy"] == pytest.approx((0.0025 + 0.0031) * 1.15)
    assert costs.RATES["usd_sell"] == costs.RATES["usd_buy"]


def test_other_rates():
    assert costs.RATES["fx_convert"] == pytest.approx(0.012)
    assert costs.RATES["jse_buy"] == pytest.approx(0.0025)


def test_fee_breakdown_for_one_step():
    out = costs.fee(10_000, "usd_buy")
    assert out["fee"] == pytest.approx(64.4) and out["net"] == pytest.approx(9935.6)
    assert out["rate"] == costs.RATES["usd_buy"]


def test_unknown_kind_and_negative_amount_rejected():
    with pytest.raises(KeyError):
        costs.fee(100, "nope")
    assert costs.fee(-5, "usd_buy")["fee"] == 0


def test_tfsa_line_pays_jse_fee_only():
    line = costs.tfsa_line(3000)
    assert line["fee"] == pytest.approx(7.5) and line["invested"] == pytest.approx(2992.5)
    assert [s["kind"] for s in line["steps"]] == ["jse_buy"]


def test_usd_line_converts_then_buys():
    line = costs.usd_line(5000)
    assert [s["kind"] for s in line["steps"]] == ["fx_convert", "usd_buy"]
    after_fx = 5000 * (1 - 0.012)
    assert line["invested"] == pytest.approx(after_fx * (1 - costs.RATES["usd_buy"]))
    assert line["fee"] == pytest.approx(5000 - line["invested"])
    assert line["fee_pct"] == pytest.approx(line["fee"] / 5000)


def test_zero_amount_has_no_fee():
    assert costs.usd_line(0)["fee"] == 0 and costs.usd_line(0)["fee_pct"] == 0
