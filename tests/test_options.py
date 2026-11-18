from market_skew import blackscholes as bs
from market_skew.options import Point, iv_at, read_chain

YEARS = 30 / 365


def _rows(kind, spot, vol_for_strike, strikes):
    rows = []
    for k in strikes:
        p = bs.price(kind, spot, k, YEARS, vol_for_strike(k))
        rows.append({"strike": k, "bid": p * 0.99, "ask": p * 1.01, "volume": 10, "openInterest": 100,
                     "impliedVolatility": vol_for_strike(k)})
    return rows


def test_iv_at_interpolates_between_bracketing_points():
    pts = [Point(0.2, 0.30), Point(0.3, 0.40)]
    assert abs(iv_at(pts, 0.25) - 0.35) < 1e-9


def test_iv_at_refuses_far_away_points():
    assert iv_at([Point(0.6, 0.3), Point(0.7, 0.3)], 0.25) is None


def test_put_skew_is_positive_when_downside_strikes_are_pricier():
    smile = lambda k: 0.30 + max(0.0, (100 - k) / 100) * 0.8  # puts richer as strike falls
    strikes = range(70, 131, 2)
    reading = read_chain(_rows("call", 100, smile, strikes), _rows("put", 100, smile, strikes), 100, YEARS)
    assert reading is not None and reading.source == "mid"
    assert reading.skew > 0.1
    assert reading.put25 > reading.call25


def test_flat_smile_has_near_zero_skew():
    flat = lambda k: 0.35
    strikes = range(70, 131, 2)
    reading = read_chain(_rows("call", 100, flat, strikes), _rows("put", 100, flat, strikes), 100, YEARS)
    assert abs(reading.skew) < 0.02


def test_falls_back_to_yahoo_iv_when_quotes_are_empty():
    smile = lambda k: 0.4
    rows = lambda kind: [dict(r, bid=0, ask=0) for r in _rows(kind, 100, smile, range(70, 131, 2))]
    reading = read_chain(rows("call"), rows("put"), 100, YEARS)
    assert reading.source == "yahoo"


def test_none_when_chain_is_too_thin():
    assert read_chain([], [], 100, YEARS) is None


def test_illiquid_chains_are_skipped():
    smile = lambda k: 0.4
    rows = lambda kind: [dict(r, openInterest=1) for r in _rows(kind, 100, smile, range(70, 131, 2))]
    assert read_chain(rows("call"), rows("put"), 100, YEARS) is None



def test_calm_stock_with_wide_strikes_still_gets_a_reading():
    # KMB-like: 20% vol, $5 strikes, nearest OTM points around 0.35-0.4 delta (none at 0.5)
    smile = lambda k: 0.20 + max(0.0, (107 - k) / 107) * 0.5
    strikes = range(85, 131, 5)
    reading = read_chain(_rows("call", 107.35, smile, strikes), _rows("put", 107.35, smile, strikes), 107.35, YEARS)
    assert reading is not None
    assert 0.18 < reading.atm < 0.26 and reading.skew > 0


def test_a_stale_wide_quote_does_not_poison_the_reading():
    flat = lambda k: 0.30
    calls = _rows("call", 100, flat, range(70, 131, 2))
    puts = _rows("put", 100, flat, range(70, 131, 2))
    puts[10] = dict(puts[10], bid=0.05, ask=9.0)   # absurd spread: ignored
    puts[12] = dict(puts[12], bid=puts[12]["bid"] * 6, ask=puts[12]["ask"] * 6)  # far-off IV: dropped as outlier
    reading = read_chain(calls, puts, 100, YEARS)
    assert abs(reading.skew) < 0.05
