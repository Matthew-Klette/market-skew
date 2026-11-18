import pandas as pd

from market_skew.backtest import forward_returns, summary


def _history(days):
    rows = []
    for i in range(days):
        d = f"2026-01-{i + 1:02d}"  # one run a calendar day
        rows.append(dict(date=d, symbol="WIN", close=100 * 1.01 ** i, bucket="Contrarian Bid", asym=150))
        rows.append(dict(date=d, symbol="LOSE", close=100 * 0.99 ** i, bucket="Fear", asym=10))
    return pd.DataFrame(rows)


def test_not_ready_until_enough_days():
    result = summary(_history(3))
    assert result["horizons"][5] == {"ready": False, "needs": 3}


def test_contrarian_bid_beats_average_in_rigged_history():
    result = summary(_history(10))
    rows = {r["group"]: r for r in result["horizons"][5]["rows"]}
    assert rows["Contrarian Bid"]["mean"] > 0 > rows["Fear"]["mean"]
    assert rows["Contrarian Bid"]["hit"] == 1.0


def test_forward_returns_use_the_close_n_sessions_later():
    fwd = forward_returns(_history(8), 7)
    win = fwd[fwd["symbol"] == "WIN"].iloc[0]
    assert len(fwd) == 2 and win["excess"] > 0


def test_split_sized_moves_are_dropped():
    h = _history(9)
    h.loc[(h["symbol"] == "WIN") & (h["date"] == "2026-01-08"), "close"] = 1.0  # a 1:100 reverse-split artefact
    fwd = forward_returns(h, 7)
    assert "WIN" not in set(fwd[fwd["date"] == "2026-01-01"]["symbol"])
