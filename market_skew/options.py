"""Turns one option chain into a skew reading: 25-delta put IV, 25-delta call IV, ATM IV and today's call/put flow.

skew = (IV of the 25-delta put - IV of the 25-delta call) / ATM IV.
High skew = people pay up for crash protection. Low or negative skew = people pay up for upside (calls are bid).
"""
from dataclasses import dataclass
from typing import Iterable, Mapping

from . import blackscholes as bs

TARGET_DELTA = 0.25
MAX_DELTA_GAP = 0.12  # nearest point must be this close to 0.25 when nothing brackets it
MIN_POINTS = 2
FALLBACK_MIN_IV = 0.02
MIN_OPEN_INTEREST = 300   # thinner chains give nonsense skews (one stale quote can mean 200%)
MAX_ABS_SKEW = 1.0
ATM_RANGE = (0.03, 3.0)
MAX_SPREAD = 0.6          # (ask - bid) / mid; wider quotes are stale or empty and give absurd IVs
OUTLIER_MULTIPLE = 2.0    # a point more than 2x (or under half) the chain's median IV is a bad quote
MIN_ATM_DELTA = 0.3       # the nearest-the-money point on each side must be at least this close to the money


@dataclass(frozen=True)
class Point:
    delta: float  # absolute delta
    iv: float


@dataclass(frozen=True)
class SkewReading:
    put25: float
    call25: float
    atm: float
    skew: float
    call_volume: float
    put_volume: float
    call_oi: float
    put_oi: float
    source: str  # "mid" when IV came from our own solve of mid prices, "yahoo" when we fell back to Yahoo's IV


def _num(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number == number else 0.0  # NaN -> 0


def _mid(row: Mapping) -> float | None:
    bid, ask = _num(row.get("bid")), _num(row.get("ask"))
    if bid > 0 and ask >= bid:
        mid = (bid + ask) / 2
        return mid if (ask - bid) / mid <= MAX_SPREAD else None
    return None


def _drop_outliers(put_points: list[Point], call_points: list[Point]) -> tuple[list[Point], list[Point]]:
    ivs = sorted(p.iv for p in put_points + call_points)
    if not ivs:
        return put_points, call_points
    median = ivs[len(ivs) // 2]
    keep = lambda pts: [p for p in pts if median / OUTLIER_MULTIPLE <= p.iv <= median * OUTLIER_MULTIPLE]
    return keep(put_points), keep(call_points)


def side_points(kind: str, rows: Iterable[Mapping], spot: float, years: float, use_mid: bool) -> list[Point]:
    """Out-of-the-money points only: puts below spot, calls above. They carry the real skew information."""
    points = []
    for row in rows:
        strike = _num(row.get("strike"))
        if strike <= 0 or (kind == "put" and strike > spot) or (kind == "call" and strike < spot):
            continue
        if use_mid:
            mid = _mid(row)
            vol = bs.implied_vol(kind, mid, spot, strike, years) if mid else None
        else:
            raw = _num(row.get("impliedVolatility"))
            vol = raw if raw >= FALLBACK_MIN_IV else None
        if vol:
            points.append(Point(abs(bs.delta(kind, spot, strike, years, vol)), vol))
    return sorted(points, key=lambda p: p.delta)


def iv_at(points: list[Point], target: float) -> float | None:
    """Linear interpolation in delta; nearest point if nothing brackets the target but one is close enough."""
    if not points:
        return None
    for low, high in zip(points, points[1:]):
        if low.delta <= target <= high.delta:
            if high.delta == low.delta:
                return (low.iv + high.iv) / 2
            weight = (target - low.delta) / (high.delta - low.delta)
            return low.iv + weight * (high.iv - low.iv)
    nearest = min(points, key=lambda p: abs(p.delta - target))
    return nearest.iv if abs(nearest.delta - target) <= MAX_DELTA_GAP else None


def _flow(rows: Iterable[Mapping], field: str) -> float:
    return sum(_num(row.get(field)) for row in rows)


def read_chain(calls: list[Mapping], puts: list[Mapping], spot: float, years: float) -> SkewReading | None:
    if _flow(calls, "openInterest") + _flow(puts, "openInterest") < MIN_OPEN_INTEREST:
        return None
    for use_mid, source in ((True, "mid"), (False, "yahoo")):
        put_points, call_points = _drop_outliers(side_points("put", puts, spot, years, use_mid),
                                                 side_points("call", calls, spot, years, use_mid))
        if len(put_points) < MIN_POINTS or len(call_points) < MIN_POINTS:
            continue
        put25, call25 = iv_at(put_points, TARGET_DELTA), iv_at(call_points, TARGET_DELTA)
        # ATM: the strikes nearest the price on each side (out-of-the-money only reach ~0.4 delta, never 0.5)
        nearest = [pts[-1] for pts in (put_points, call_points) if pts[-1].delta >= MIN_ATM_DELTA]
        if not (put25 and call25 and nearest):
            continue
        atm = sum(p.iv for p in nearest) / len(nearest)
        if not ATM_RANGE[0] <= atm <= ATM_RANGE[1] or abs((put25 - call25) / atm) > MAX_ABS_SKEW:
            continue
        return SkewReading(
            put25=put25, call25=call25, atm=atm, skew=(put25 - call25) / atm,
            call_volume=_flow(calls, "volume"), put_volume=_flow(puts, "volume"),
            call_oi=_flow(calls, "openInterest"), put_oi=_flow(puts, "openInterest"), source=source,
        )
    return None
