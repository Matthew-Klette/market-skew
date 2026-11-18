"""Splits the monthly USD-account money (in rand) across funds and single stocks. Pure: no network, no disk.

Rules (SPEC story 3):
  - QQQ, SCHD and VOO always get at least 15% each of the amount.
  - Single stocks together get 30% of the amount when there are Picks (the top 2). With no Picks that money goes back to
    the funds.
  - Whatever is left above the floors is tilted between the three funds by signal weight: add 2, wait 1, hold 0.5.
    A fund with no reading counts as wait.
  - VOOG never gets new money.
Amounts are whole rand and add up to the input exactly (largest remainder).
"""
from . import costs, funds

FUND_ORDER = funds.NEW_MONEY
FUND_NAMES = funds.NAMES
FLOOR, STOCK_CAP, PER_MONTH = 0.15, 0.30, 2
WEIGHTS = {"add": 2.0, "wait": 1.0, "hold": 0.5}


def _largest_remainder(shares: list[float], total: int) -> list[int]:
    raw = [s * total for s in shares]
    floors = [int(x) for x in raw]
    order = sorted(range(len(raw)), key=lambda i: raw[i] - floors[i], reverse=True)
    for i in order[:total - sum(floors)]:
        floors[i] += 1
    return floors


def _fund_reason(signal: dict | None) -> str:
    kind = (signal or {}).get("timing")
    if kind == "add":
        return f"Good time to add: {signal.get('why', '')}".strip()
    if kind == "wait":
        return "OK, but no rush: floor amount plus a standard share of the rest."
    if kind == "hold":
        return "Floor amount: you asked to keep adding to this. Options say don't add extra now."
    return "Floor amount: you asked to keep adding to this. No options reading yet."


def _stock_reason(p: dict) -> str:
    return (f"Pick: buy near ${p['entry']:,.2f}, stop ${p['stop']:,.2f}, target ${p['target']:,.2f}, "
            f"give it until {p['until']}.")


def _line(symbol: str, name: str, kind: str, rand: int, reason: str, rate: float | None) -> dict:
    cost = costs.usd_line(rand)
    return {"symbol": symbol, "name": name, "kind": kind, "rand": rand, "dollars": rand / rate if rate else None,
            "fee": cost["fee"], "invested": cost["invested"], "reason": reason}


def allocate(amount: float, fund_signals: dict, candidates: list[dict],
             rate: float | None = None, tilt: dict | None = None) -> list[dict]:
    """`tilt` (optional) multiplies a fund's signal weight, e.g. {"QQQ": 0.5, "VOO": 1.5} when drift says so (rebalance.tilt)."""
    total = max(int(round(float(amount))), 0)
    stocks = list(candidates)[:PER_MONTH]
    stock_share = STOCK_CAP if stocks else 0.0
    weights = [WEIGHTS.get((fund_signals.get(s) or {}).get("timing"), WEIGHTS["wait"]) * (tilt or {}).get(s, 1.0) for s in FUND_ORDER]
    tilt_pool = 1.0 - stock_share - FLOOR * len(FUND_ORDER)
    fund_shares = [FLOOR + tilt_pool * w / sum(weights) for w in weights]
    stock_shares = [stock_share / len(stocks)] * len(stocks) if stocks else []
    rands = _largest_remainder(fund_shares + stock_shares, total)
    lines = [_line(s, FUND_NAMES[s], "fund", r, _fund_reason(fund_signals.get(s)), rate)
             for s, r in zip(FUND_ORDER, rands)]
    lines += [_line(p["symbol"], p.get("name") or p["symbol"], "stock", r, _stock_reason(p), rate)
              for p, r in zip(stocks, rands[len(FUND_ORDER):])]
    return lines
