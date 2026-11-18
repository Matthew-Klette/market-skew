"""Timing signals for the index funds (VOO, SCHD, QQQ, VOOG). Pure: no network.

Funds aren't in the per-stock cross-section (there is no fund peer group to rank against), so each fund gets a plain rule
that lands in the same four buckets stocks use:
  price side  1-month return against SPY's. A fund within 0.25 points of SPY (VOO is basically SPY) is judged by its own
              1-month sign instead, so a tie never flips the bucket at random.
  bets side   today's skew against the fund's own average over its last 5 saved reports; when there is no history yet,
              against SPY's skew. Lower than that baseline = calls are bid = bullish (the same direction stocks use).
Buckets and wording come from signals.BUCKETS and picks.timing, so a fund reads exactly like a stock.
"""
from .picks import timing
from .signals import BUCKETS

FUNDS = ("QQQ", "SCHD", "VOO", "VOOG")
NEW_MONEY = ("QQQ", "SCHD", "VOO")  # VOOG overlaps VOO, so it is tracked but gets nothing new
NAMES = {"QQQ": "Invesco QQQ (Nasdaq 100)", "SCHD": "Schwab US Dividend Equity", "VOO": "Vanguard S&P 500",
         "VOOG": "Vanguard S&P 500 Growth"}
TIE = 0.0025
HISTORY_DAYS = 5


def signal(symbol: str, skew: float, ret_1m: float, price: float, spy_ret_1m: float,
           own_history: list[float] | None, spy_skew: float | None) -> dict | None:
    """One fund's signal, or None when there is neither a baseline nor a skew to read."""
    if skew is None:
        return None
    history = [v for v in (own_history or []) if v is not None][-HISTORY_DAYS:]
    if history:
        baseline, basis = sum(history) / len(history), "its own last readings"
    elif spy_skew is not None:
        baseline, basis = spy_skew, "SPY's skew"
    else:
        return None
    relative = ret_1m - spy_ret_1m
    price_up = ret_1m >= 0 if abs(relative) < TIE else relative >= 0
    bets_up = skew <= baseline
    bucket = BUCKETS[(price_up, bets_up)][0]
    kind, label, why = timing(bucket)
    return {"name": NAMES.get(symbol, symbol), "bucket": bucket, "timing": kind, "label": label, "why": why,
            "skew": float(skew), "baseline": float(baseline), "basis": basis, "ret_1m": float(ret_1m), "price": float(price)}


def build(readings: dict, stats: dict, history: dict[str, list[float]]) -> dict[str, dict]:
    """readings: symbol -> SkewReading or None. stats: symbol -> {"close", "ret_1m"} (must include SPY).
    history: symbol -> earlier skews, oldest first. SPY's skew is read from readings."""
    spy = readings.get("SPY")
    spy_skew = spy.skew if spy else None
    spy_ret = (stats.get("SPY") or {}).get("ret_1m")
    out = {}
    for symbol in FUNDS:
        reading, row = readings.get(symbol), stats.get(symbol)
        if not reading or not row or spy_ret is None:
            continue
        result = signal(symbol, reading.skew, row["ret_1m"], row["close"], spy_ret, history.get(symbol), spy_skew)
        if result:
            out[symbol] = result
    return out


def history_from(bodies: list[dict]) -> dict[str, list[float]]:
    """Fund skews saved in earlier reports (oldest first) -> symbol -> list."""
    out: dict[str, list[float]] = {}
    for body in bodies:
        for symbol, f in (body.get("funds") or {}).items():
            if f.get("skew") is not None:
                out.setdefault(symbol, []).append(f["skew"])
    return out


def as_holding(symbol: str, fund: dict) -> dict:
    """A 'Stocks you own' row for a fund, same shape as picks.holdings_check."""
    return {"symbol": symbol, "name": fund.get("name", symbol), "light": fund["timing"], "label": fund["label"],
            "why": fund["why"], "price": fund["price"], "ret_1m": fund["ret_1m"]}


def compute(readings: dict, stats_frame, past_bodies: list[dict]) -> dict[str, dict]:
    """The glue the scan and `skew funds` share: readings + price_stats frame + earlier reports -> body["funds"]."""
    wanted = list(FUNDS) + ["SPY"]
    rows = stats_frame[stats_frame["symbol"].isin(wanted)].set_index("symbol")
    stats = {s: {"close": float(r["close"]), "ret_1m": float(r["ret_1m"])} for s, r in rows.iterrows()}
    return build(readings, stats, history_from(past_bodies))
