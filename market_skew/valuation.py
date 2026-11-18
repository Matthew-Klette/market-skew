"""Fair-value range: a simplified free-cash-flow DCF with a bear, base and bull case. Pure: no files, no network.

Simplified to free data. We have free cash flow (operating cash flow minus capex) from SEC filings, not clean EBIT, D&A or working
capital, so the model grows free cash flow directly (the margin stays flat, so free cash grows with sales). No analyst estimates.
The spec moves the bear and bull cases by plus or minus 200 basis points of EBIT margin. We have no EBIT, so the same idea is applied
to the FCF margin as a relative shift: for a typical 20% margin, 200bp is 10% of the margin, so bear starts from 10% less free cash and
bull from 10% more (MARGIN_SHIFT in SCENARIOS). Growth fades over ten years, as the spec asks.
It is always shown as a range, never as a single target. Every rule is in the "How it works" page.
"""
import numpy as np

from .sentinel import TREASURY_10Y

RISK_FREE = TREASURY_10Y          # shared with the Quality score cash-yield bar
EQUITY_PREMIUM = 0.045
DEFAULT_BETA = 1.0                # fallback when no measured beta exists for a name (not enough price history): the market's own beta
BETA_CLAMP = (0.6, 1.6)           # a measured beta is kept inside this range; two years of weekly returns is a noisy estimate
BETA_MIN_WEEKS = 52
DEBT_COST, TAX = 0.06, 0.21
YEARS = 10
GROWTH_CLAMP = (-0.05, 0.25)
FADE_TO = 0.01                    # growth in year 10 is terminal growth plus this
SCENARIOS = {                     # name: (terminal growth, growth shift, discount-rate shift, relative FCF-margin shift)
    "bear": (0.015, -0.03, +0.01, -0.10),
    "base": (0.025, 0.0, 0.0, 0.0),
    "bull": (0.030, +0.03, -0.01, +0.10),
}
SKIP_SECTORS = {"Financials": "Banks, insurers and similar firms live on their balance sheet, so free cash flow does not describe them.",
                "Real Estate": "Property companies are valued on property income and debt terms, not free cash flow."}
FAR, CHECK = 0.85, 0.45           # share of value that sits in the terminal value
DEVIATION = 0.40                  # latest free cash more than 40% above or below its 3-year average: the average is used instead
IMPLIED_RANGE = (-0.10, 1.0)      # search range for the market-implied yearly growth

LATE = "Most of the value is far in the future: over 85% of it comes after year ten, so small changes in the assumptions move it a lot."
CHECKS = "Check the inputs: under 45% of the value comes from the long run, which is unusual for a going concern."


def skip(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _starting_cash(m: dict) -> tuple[float, str]:
    """TTM free cash, or the 3-year average when the latest is unusually high or low against it."""
    latest = m["fcf"]
    years = m.get("fcf_by_year") or {}
    recent = [years[y] for y in sorted(years)[-3:]]
    if len(recent) == 3:
        average = sum(recent) / 3
        if average > 0 and abs(latest / average - 1) > DEVIATION:
            return average, "the 3-year average, because the latest year is far from its usual level"
    return latest, "the last twelve months"


def _balance(m: dict) -> tuple[float, float]:
    cash, debt = m.get("cash"), m.get("debt")
    if cash is None or debt is None:  # older stored numbers only carry net cash
        net = m.get("net_cash") or 0.0
        return max(net, 0.0), max(-net, 0.0)
    return cash, debt


def beta_from_closes(stock, market) -> float | None:
    """Beta of weekly returns against the market over the last two years, kept between 0.6 and 1.6.
    stock and market are daily close Series with a date index. None when fewer than 52 shared weeks."""
    import pandas as pd
    both = pd.concat([stock, market], axis=1, keys=["s", "m"]).dropna()
    both = both[both.index >= both.index.max() - pd.Timedelta(days=730)] if len(both) else both
    weekly = both.resample("W-FRI").last().pct_change().dropna()
    if len(weekly) < BETA_MIN_WEEKS or weekly["m"].var() == 0:
        return None
    beta = float(weekly["s"].cov(weekly["m"]) / weekly["m"].var())
    return min(max(beta, BETA_CLAMP[0]), BETA_CLAMP[1])


def discount_rate(m: dict, price: float, beta: float = DEFAULT_BETA) -> float:
    equity_cost = RISK_FREE + beta * EQUITY_PREMIUM
    _, debt = _balance(m)
    equity = price * m["shares"]
    share = equity / (equity + debt)
    return share * equity_cost + (1 - share) * DEBT_COST * (1 - TAX)


def _case(start: float, g1: float, terminal: float, rate: float, flat: bool = False) -> dict:
    """flat=True holds g1 every year instead of fading it (used to read the growth the price assumes)."""
    growth = np.full(YEARS, g1) if flat else np.linspace(g1, terminal + FADE_TO, YEARS)
    flows = start * np.cumprod(1 + growth)
    pv = float(np.sum(flows / (1 + rate) ** np.arange(1, YEARS + 1)))
    tv = float(flows[-1] * (1 + terminal) / (rate - terminal))
    pv_tv = tv / (1 + rate) ** YEARS
    return {"ev": pv + pv_tv, "pv_tv": pv_tv, "tv_share": pv_tv / (pv + pv_tv), "rate": rate, "terminal": terminal}


def position(price: float, bear: float, base: float, bull: float) -> str:
    if price < bear:
        return "price is below the bear case"
    if price < base:
        return "price is between the bear and base cases"
    if price <= bull:
        return "price is between the base and bull cases"
    return "price is above the bull case"


def band(price: float, bear: float, bull: float) -> str:
    return "below bear" if price < bear else "above bull" if price > bull else "in range"


def implied_growth(price: float, start: float, rate: float, terminal: float, cash: float, debt: float, shares: float) -> float | None:
    """The yearly growth, held for ten years, that makes the base case worth exactly the price (bisection).
    None when even the top of the search range (100% a year) is not enough."""
    def per_share(g):
        return (_case(start, g, terminal, rate, flat=True)["ev"] + cash - debt) / shares
    low, high = IMPLIED_RANGE
    if per_share(high) < price:
        return None
    if per_share(low) > price:
        return low
    for _ in range(60):
        mid = (low + high) / 2
        low, high = (mid, high) if per_share(mid) < price else (low, mid)
    return (low + high) / 2


def _assumptions(g1, start, how, rate, beta) -> list[str]:
    return [f"Starting free cash flow: ${start / 1e6:,.0f}M a year, from {how}.",
            f"Growth: free cash flow grows with sales, starting at {g1 * 100:.0f}% a year (recent sales growth, kept between -5% and 25%) and "
            f"fading steadily to the long-run rate over ten years. Bear is 3 points lower, bull 3 points higher, and bear starts from "
            "10% less free cash, bull from 10% more (our stand-in for plus or minus 2 points of operating margin).",
            f"Long-run growth after year 10: 1.5% bear, 2.5% base, 3.0% bull.",
            f"Discount rate: {rate * 100:.1f}% base (cost of equity {RISK_FREE * 100:.1f}% + beta {beta:g} x 4.5%, blended with 6% debt after 21% tax). "
            f"Beta is {'assumed to be 1.0 (not enough price history to measure)' if beta == DEFAULT_BETA else 'measured from two years of weekly returns against the market, kept between 0.6 and 1.6'}. Bear adds 1 point, bull takes off 1.",
            "Value = ten years of cash plus a long-run value, plus cash, minus debt, divided by shares today."]


def value(m: dict, price, sector: str | None, beta: float = DEFAULT_BETA) -> dict:
    """{'ok': False, 'reason'} or {'ok': True, bear, base, bull (per share), price, position, band, assumptions, flags, ...}."""
    if sector in SKIP_SECTORS:
        return skip(SKIP_SECTORS[sector])
    if (m.get("depth") or "Thin") == "Thin":
        return skip("Not enough filings to trust a cash-flow projection.")
    fcf, shares = m.get("fcf"), m.get("shares")
    if fcf is None or not price or not shares or shares <= 0:
        return skip("Free cash flow, share count or price is missing.")
    if fcf <= 0:
        return skip("Free cash flow is zero or negative, so a cash-flow valuation has nothing to grow from.")
    growth = m.get("revenue_growth")
    if growth is None:
        return skip("Sales growth is unknown, so there is no starting growth rate.")
    start, how = _starting_cash(m)
    if start <= 0:
        return skip("Free cash flow is zero or negative, so a cash-flow valuation has nothing to grow from.")
    g1 = min(max(growth, GROWTH_CLAMP[0]), GROWTH_CLAMP[1])
    base_rate = discount_rate(m, price, beta)
    cash, debt = _balance(m)
    cases = {}
    for name, (terminal, dg, dr, dm) in SCENARIOS.items():
        rate = base_rate + dr
        if rate <= terminal:
            return skip(f"The discount rate ({rate * 100:.1f}%) is not above long-run growth ({terminal * 100:.1f}%), so the maths breaks.")
        c = _case(start * (1 + dm), g1 + dg, terminal, rate)
        cases[name] = {**c, "per_share": max(0.0, (c["ev"] + cash - debt) / shares)}
    flags = [f for f, hit in ((LATE, cases["base"]["tv_share"] > FAR), (CHECKS, cases["base"]["tv_share"] < CHECK)) if hit]
    if how != "the last twelve months":
        flags.append("The latest year of free cash was unusual, so the 3-year average was used.")
    bear, base, bull = (cases[k]["per_share"] for k in ("bear", "base", "bull"))
    where, implied = position(price, bear, base, bull), None
    if price > bull:
        implied = implied_growth(float(price), start, base_rate, SCENARIOS["base"][0], cash, debt, shares)
        phrase = ("more than 100% growth a year for 10 years" if implied is None else f"about {implied * 100:.0f}% growth a year for 10 years")
        where = f"{where}: the price assumes {phrase}"
    return {"ok": True, "bear": bear, "base": base, "bull": bull, "price": float(price), "position": where, "implied_growth": implied,
            "band": band(price, bear, bull), "rate": base_rate, "tv_share": cases["base"]["tv_share"], "g1": g1, "beta": beta,
            "assumptions": _assumptions(g1, start, how, base_rate, beta), "flags": flags}


def for_row(row: dict, beta: float = DEFAULT_BETA) -> dict:
    """The range for one scored Quality score row (its numbers and the price the scan saw)."""
    return value(row["metrics"], (row.get("px") or {}).get("close"), row.get("sector"), beta)
