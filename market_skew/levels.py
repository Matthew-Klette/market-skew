"""Candidate buy levels from about a year of daily closes. Pure: no network.

A swing-trading creator's public method: look for the price floors where a stock has stopped and bounced before, and add in
pieces rather than all at once. These are candidate areas to watch, not buy signals and not predictions. When no floor
qualifies the answer is an empty list; a level is never invented."""
import pandas as pd

MIN_CLOSES = 120
SWING = 5            # a local low is the lowest close within 5 sessions either side
TOLERANCE = 0.02     # lows within 2% of each other are the same floor
MIN_TOUCHES = 2
APART = 15           # two touches are separate visits only when 15+ sessions apart
NEAR, FAR = 0.05, 0.40   # a level must sit 5% to 40% below today's price
MAX_LEVELS = 2
ADD_GAP = 0.05       # the next add only below 5% under your last buy
STEPS = ((20, 1), (50, 2), (100, 5), (300, 10), (600, 25), (float("inf"), 50))


def nice(value: float) -> float:
    """Round to a number a person would put an order at: 1 under $20, 2 under $50, 5 under $100, 10 under $300, 25 under $600, else 50."""
    step = next(s for limit, s in STEPS if value < limit)
    return float(round(value / step) * step)


def _lows(values: list[float]) -> list[tuple[int, float]]:
    n = len(values)
    return [(i, v) for i, v in enumerate(values)
            if SWING <= i < n - SWING and v <= min(values[i - SWING:i + SWING + 1])]


def _clusters(lows: list[tuple[int, float]]) -> list[list[float]]:
    """Lows within the tolerance of each other form a floor; lows less than APART sessions apart are one visit, not two."""
    groups: list[list[tuple[int, float]]] = []
    for low in sorted(lows, key=lambda x: x[1]):
        if groups and low[1] <= groups[-1][0][1] * (1 + TOLERANCE):
            groups[-1].append(low)
        else:
            groups.append([low])
    out = []
    for group in groups:
        visits: list[tuple[int, float]] = []
        for i, v in sorted(group):
            if visits and i - visits[-1][0] < APART:
                visits[-1] = min(visits[-1], (i, v), key=lambda x: x[1])
            else:
                visits.append((i, v))
        out.append([v for _, v in visits])
    return out


def find(closes: pd.Series | None) -> list[dict]:
    """[{level, kind: "floor", touches, distance_pct}] for up to two floors below today's price, highest first, or []."""
    if closes is None:
        return []
    values = [float(v) for v in closes.dropna().tail(260) if v > 0]
    if len(values) < MIN_CLOSES:
        return []
    price = values[-1]
    found = []
    for group in _clusters(_lows(values)):
        if len(group) < MIN_TOUCHES:
            continue
        level = nice(sorted(group)[len(group) // 2])
        gap = (price - level) / price
        if NEAR <= gap <= FAR:
            found.append({"level": level, "kind": "floor", "touches": len(group), "distance_pct": round(gap * 100, 1)})
    unique = {x["level"]: x for x in sorted(found, key=lambda x: x["touches"])}.values()  # same rounded level: keep the most touched
    best = sorted(unique, key=lambda x: (-x["touches"], x["distance_pct"]))[:MAX_LEVELS]
    return sorted(best, key=lambda x: -x["level"])


def next_add(last_buy: float | None) -> float | None:
    """Add-on rule: the next piece only below 5% under your last buy."""
    if not last_buy or last_buy <= 0:
        return None
    return round(last_buy * (1 - ADD_GAP), 2)


def floor_near(closes, above: float = 0.03, below: float = 0.02, touches: int = 3) -> dict | None:
    """The floor today's price is sitting on: one that held `touches`+ separate times in the last year and is within 3% under
    today's price (or up to 2% through it). {level, touches, distance_pct} or None. Used by the BUY NOW check only."""
    values = [float(v) for v in (closes.dropna() if hasattr(closes, "dropna") else closes) if v and v > 0][-260:]
    if len(values) < MIN_CLOSES:
        return None
    price = values[-1]
    near = []
    for group in _clusters(_lows(values)):
        level = sorted(group)[len(group) // 2]
        gap = (price - level) / price
        if len(group) >= touches and -below <= gap <= above:
            near.append({"level": round(level, 2), "touches": len(group), "distance_pct": round(gap * 100, 1)})
    return max(near, key=lambda x: (x["touches"], -abs(x["distance_pct"]))) if near else None
