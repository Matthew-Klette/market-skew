"""BUY NOW: the rare days when every signal the app has lines up at once. Pure: reads the saved report and Quality score rows.

Most days this is empty, and that is the point. It only fires when several independent checks agree, each one strict:

  Index fund (VOO, QQQ, SCHD; VOOG gets no new money)
    1. The S&P 500 is 10%+ below its high (a real correction, not a wobble).
    2. VIX is up 30%+ over the month (people are scared, which is when prices are marked down).
    3. The fund itself is 10%+ below its one-year high.
    4. Options traders on that fund lean towards a bounce (Contrarian Bid, not Fear).
    5. Google's prediction, when installed, does not point lower over the next month.

  Single stock
    1. It is already on today's Picks list (quality gate, Contrarian Bid, liquid, no results within 7 days).
    2. Quality score 75+ AFTER Claude argued against it (an unchecked score never counts).
    3. The price is under the bear case of the fair-value range: cheap even on pessimistic assumptions.
    4. It sits on a floor: within 3% of a price that held 3+ separate times in the last year.
    5. Not a stormy market (in a storm single stocks fall together).
    6. Google's prediction, when installed, does not point lower over the next month.

Rules on public data, not advice. A rare setup is still not a sure thing.
"""
from . import levels, swing
from .funds import NEW_MONEY

MARKET_OFF_HIGH = -0.10
VIX_MONTH = 0.30
FUND_OFF_HIGH = -0.10
STOCK_SCORE = 75

FUND_RISKS = ("Corrections can turn into bear markets: in 2000-02 and 2008-09 the S&P 500 kept falling for more than a year after a drop like this.",
              "This is for money you won't need for 5+ years. If that's not this money, it's not a BUY NOW for you.")
STOCK_RISKS = ("One company can fall a long way on news no rule can see. Keep it to the stock part of your plan, not extra.",
               "Respect the 'Sell if below' price on the card. A floor that held three times can still break.")


def _off_high(closes: list[float] | None) -> float | None:
    values = [v for v in closes or [] if v]
    return values[-1] / max(values) - 1 if len(values) >= 120 else None


def _google(pred: dict | None, price: float) -> tuple[bool, str]:
    """(passes, reason line). A missing prediction never blocks, it is just said."""
    if not pred or not pred.get("mid"):
        return True, "Google's prediction is not installed or has no range for it, so that check was skipped."
    change = pred["mid"] / (pred.get("last") or price) - 1
    if change < 0:
        return False, ""
    return True, f"Google's prediction has its middle guess {change * 100:+.0f}% over the next month (a guess, not a promise)."


def _fund(symbol: str, fund: dict, report: dict) -> dict | None:
    spy, vix = report["indexes"].get("SPY") or {}, report["indexes"].get("VIX") or {}
    market, fear = spy.get("off_high"), vix.get("ret_1m")
    own = _off_high((report.get("levels") or {}).get(symbol, {}).get("closes"))
    if None in (market, fear, own) or market > MARKET_OFF_HIGH or fear < VIX_MONTH or own > FUND_OFF_HIGH:
        return None
    if fund.get("bucket") != "Contrarian Bid":
        return None
    ok, google = _google((report.get("predictions") or {}).get(symbol), fund["price"])
    if not ok:
        return None
    return {"symbol": symbol, "name": fund.get("name", symbol), "kind": "fund", "price": fund["price"],
            "action": f"Put this month's {symbol} money in now, in one go, instead of spreading it out.",
            "reasons": [f"The whole US market is on sale: the S&P 500 is {abs(market) * 100:.0f}% below its high.",
                        f"People are scared: the fear gauge (VIX) is up {fear * 100:.0f}% this month. Long-term buyers have usually done best buying into fear, not after it passes.",
                        f"{symbol} itself is {abs(own) * 100:.0f}% below its one-year high.",
                        f"Options traders on {symbol} are betting on a bounce, not on more falls.",
                        google],
            "risks": list(FUND_RISKS)}


def _stock(pick: dict, row: dict | None, report: dict) -> dict | None:
    if not row or row["score"] < STOCK_SCORE or not row.get("breaking") or row.get("thin"):
        return None
    value = row.get("value") or {}
    if not value.get("ok") or pick["entry"] >= value["bear"]:
        return None
    floor = levels.floor_near(
        (report.get("levels") or {}).get(pick["symbol"], {}).get("closes") or [])
    if not floor or swing.is_stormy(report["indexes"]):
        return None
    ok, google = _google((report.get("predictions") or {}).get(pick["symbol"]), pick["entry"])
    if not ok:
        return None
    cheap = 1 - pick["entry"] / value["bear"]
    return {"symbol": pick["symbol"], "name": pick["name"], "kind": "stock", "price": pick["entry"],
            "action": f"Buy near ${pick['entry']:,.2f} with the stock part of this month's plan. Sell if it closes below ${pick['stop']:,.2f}.",
            "reasons": [f"High quality: Quality score {row['score']} even after Claude argued against it.",
                        f"Cheap even on bad assumptions: the price is {cheap * 100:.0f}% under the bear case of its fair-value range (${value['bear']:,.2f}).",
                        f"On a floor: it has bounced off about ${floor['level']:,.2f} {floor['touches']} separate times this year, and it's {abs(floor['distance_pct']):.1f}% from it now.",
                        "Good timing: down this month while options traders bet on a bounce, with no results due within a week.",
                        google],
            "risks": list(STOCK_RISKS)}


def check(report: dict, scores: list[dict], excluded=frozenset()) -> list[dict]:
    """Every BUY NOW for this report, funds first. Usually []."""
    hits = [_fund(s, f, report) for s, f in (report.get("funds") or {}).items() if s in NEW_MONEY and s not in excluded]
    rows = {r["symbol"]: r for r in scores}
    hits += [_stock(p, rows.get(p["symbol"]), report) for p in report.get("swing") or [] if p["symbol"] not in excluded]
    return [h for h in hits if h]
