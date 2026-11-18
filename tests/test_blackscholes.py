from market_skew import blackscholes as bs


def test_implied_vol_recovers_the_vol_used_to_price():
    premium = bs.price("put", 100, 95, 30 / 365, 0.42)
    assert abs(bs.implied_vol("put", premium, 100, 95, 30 / 365) - 0.42) < 1e-4


def test_call_delta_is_half_near_the_money_and_put_delta_negative():
    assert 0.45 < bs.delta("call", 100, 100, 30 / 365, 0.3) < 0.6
    assert -0.55 < bs.delta("put", 100, 100, 30 / 365, 0.3) < -0.4


def test_implied_vol_is_none_for_impossible_premiums():
    assert bs.implied_vol("call", 0, 100, 110, 0.1) is None
    assert bs.implied_vol("call", 150, 100, 110, 0.1) is None
