"""Black-Scholes pricing, delta and implied volatility. Yahoo gives no greeks, so delta is worked out here."""
import math

from scipy.optimize import brentq
from scipy.stats import norm

RATE = 0.04  # rough US short rate; skew is a difference of two IVs, so this barely moves it
MIN_VOL, MAX_VOL = 0.01, 5.0


def _d1(spot: float, strike: float, years: float, vol: float, rate: float) -> float:
    return (math.log(spot / strike) + (rate + 0.5 * vol * vol) * years) / (vol * math.sqrt(years))


def price(kind: str, spot: float, strike: float, years: float, vol: float, rate: float = RATE) -> float:
    d1 = _d1(spot, strike, years, vol, rate)
    d2 = d1 - vol * math.sqrt(years)
    disc = math.exp(-rate * years)
    if kind == "call":
        return spot * norm.cdf(d1) - strike * disc * norm.cdf(d2)
    return strike * disc * norm.cdf(-d2) - spot * norm.cdf(-d1)


def delta(kind: str, spot: float, strike: float, years: float, vol: float, rate: float = RATE) -> float:
    d1 = _d1(spot, strike, years, vol, rate)
    return norm.cdf(d1) if kind == "call" else norm.cdf(d1) - 1.0


def implied_vol(kind: str, premium: float, spot: float, strike: float, years: float, rate: float = RATE) -> float | None:
    """None when the premium is outside what any volatility could produce (stale or crossed quotes)."""
    if premium <= 0 or years <= 0:
        return None
    low = price(kind, spot, strike, years, MIN_VOL, rate)
    high = price(kind, spot, strike, years, MAX_VOL, rate)
    if not low < premium < high:
        return None
    return brentq(lambda v: price(kind, spot, strike, years, v, rate) - premium, MIN_VOL, MAX_VOL, xtol=1e-6)
