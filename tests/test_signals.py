import pandas as pd

from market_skew.signals import capped_weights, group_table, robust_z, score


def _stocks():
    return pd.DataFrame([
        # falling stock where calls are bid (low skew, heavy call volume) -> Contrarian Bid
        dict(symbol="DIP", sector="Tech", ret_1m=-0.15, ret_1w=-0.02, ret_1d=0.02, skew=0.00, call_volume=900, put_volume=100),
        # falling stock with expensive puts -> Fear
        dict(symbol="SINK", sector="Tech", ret_1m=-0.12, ret_1w=-0.05, ret_1d=-0.01, skew=0.40, call_volume=100, put_volume=900),
        # rising with calls bid -> Chase
        dict(symbol="RIP", sector="Tech", ret_1m=0.20, ret_1w=0.05, ret_1d=0.01, skew=0.02, call_volume=800, put_volume=100),
        # rising but puts being bought -> Hedged Rally
        dict(symbol="NERV", sector="Tech", ret_1m=0.18, ret_1w=0.03, ret_1d=0.00, skew=0.45, call_volume=100, put_volume=700),
        dict(symbol="MID", sector="Tech", ret_1m=0.01, ret_1w=0.00, ret_1d=0.00, skew=0.15, call_volume=300, put_volume=300),
    ])


def test_each_quadrant_lands_in_its_bucket():
    scored = score(_stocks(), spy_1m=0.0).set_index("symbol")
    assert scored.loc["DIP", "bucket"] == "Contrarian Bid"
    assert scored.loc["SINK", "bucket"] == "Fear"
    assert scored.loc["RIP", "bucket"] == "Chase"
    assert scored.loc["NERV", "bucket"] == "Hedged Rally"


def test_contrarian_bid_ranks_first_on_asym():
    scored = score(_stocks(), spy_1m=0.0)
    assert scored.iloc[0]["symbol"] == "DIP"
    assert (scored["asym"] >= 0).all()


def test_rows_without_skew_are_dropped_and_input_untouched():
    frame = _stocks()
    frame.loc[0, "skew"] = None
    scored = score(frame, 0.0)
    assert "DIP" not in set(scored["symbol"])
    assert "bucket" not in frame.columns


def test_capped_weights_respect_the_cap_and_sum_to_one():
    w = capped_weights(pd.Series([100, 1, 1, 1, 1, 1]))
    assert abs(w.sum() - 1) < 1e-9
    assert w.max() <= 0.25 + 1e-9


def test_robust_z_is_clipped():
    z = robust_z(pd.Series([1, 2, 3, 4, 1000]))
    assert z.max() == 3.0


def test_group_table_reports_relative_return_and_breadth():
    scored = score(_stocks(), 0.0).assign(dvol_21=1e6, dvol_5=1e6, dvol_today=1e6)
    table = group_table(scored, {"All": list(scored["symbol"])}, {"ret_1m": 0.0, "ret_1w": 0.0}, 5e6, 5e6)
    row = table.iloc[0]
    assert row["count"] == 5
    assert abs(row["rel_1m"] - 0.024) < 1e-9
    assert row["breadth"] == 0.6


def test_a_stock_down_more_than_spy_is_never_a_chase_even_if_peers_fell_harder():
    frame = _stocks().assign(ret_1m=[-0.30, -0.28, -0.12, -0.25, -0.26])
    scored = score(frame, spy_1m=-0.05).set_index("symbol")
    assert scored.loc["RIP", "price_z"] < 0
    assert scored.loc["RIP", "bucket"] in {"Contrarian Bid", "Fear"}
