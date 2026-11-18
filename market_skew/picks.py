"""Steady picks: a long-term, low-volatility shortlist, and when the options market says it's a good time to add.

Built for a beginner starting a long-term portfolio, not for trading:
  - The core of the portfolio is a broad index fund. The picks are a small satellite around it.
  - Picks are big, calm companies the options market isn't worried about.
  - The gaps (price vs options bets) only decide timing: add on calm dips, wait when a name is crowded,
    hold off when people are buying insurance against it.

Rules (all of them):
  1. Big and established: market value $20B+, share price $10+, $100M+ traded a day.
  2. Calm: options price in small moves (at-the-money implied volatility 30% a year or less).
  3. Nobody is bracing for trouble: not in the Fear or Hedged Rally bucket, not down more than 15% in a month.
  4. Score = 100 - implied volatility: calmer ranks higher, +5 when money is moving into its sector.
     The gaps don't change the ranking, only the timing label (and which picks get this month's money).
  5. One per sector so the list is spread out, at most 6.
  6. Quality score: an adjusted score of 60+ for companies (gate.py); funds are exempt.
"""
from dataclasses import asdict, dataclass

import pandas as pd

from . import gate as sentinel_gate
from .swing import steady_note

FUNDS = ("QQQ", "SCHD", "VOO", "VOOG")  # same list as funds.FUNDS (funds.py imports this module, so it is not imported back)
MAX_PICKS = 6
MIN_MARKET_CAP, MIN_PRICE, MIN_DOLLAR_VOLUME = 20e9, 10.0, 100e6
MAX_ATM_IV, WORST_MONTH = 0.30, -0.15
FLOW_POINTS = 5
CORE_SHARE = 0.8  # suggested share of new money for the index fund
PER_MONTH = 2     # stock money goes to the top 2 ready picks; tiny slices across six lose too much to fees

TIMING = {
    "Contrarian Bid": ("add", "Good time to add", "It dipped this month and options traders are betting on a bounce."),
    "Chase": ("wait", "OK, but no rush", "It's been popular lately. Buying in small monthly amounts beats buying all at once here."),
    "Hedged Rally": ("hold", "Don't add now", "It's up, but traders are buying insurance against a drop. Wait for that to calm down."),
    "Fear": ("hold", "Don't add now", "It's falling and traders expect more. No need to sell a long-term holding, but don't add yet."),
}


@dataclass(frozen=True)
class Pick:
    symbol: str
    name: str
    sector: str
    score: int
    price: float
    iv: float
    ret_1m: float
    timing: str
    timing_label: str
    reasons: tuple[str, ...]
    earnings_note: str = ""


def timing(bucket: str) -> tuple[str, str, str]:
    return TIMING.get(bucket, ("wait", "No signal", "No options reading today."))


def _reasons(row) -> tuple[str, ...]:
    expected = row["atm"] / (12 ** 0.5)
    return (
        f"Large and established: worth about ${row['market_cap'] / 1e9:,.0f}B.",
        f"Calm: options price in a typical move of about {expected * 100:.0f}% a month.",
        timing(row["bucket"])[2],
    )


def _with_score(reasons: tuple[str, ...], gate: dict | None, symbol: str) -> tuple[str, ...]:
    entry = (gate or {}).get(symbol)
    return (entry["line"], *reasons) if entry else reasons


def choose(scored: pd.DataFrame, sector_flow: dict, excluded: frozenset | set = frozenset(), gate: dict | None = None,
           earnings: dict | None = None, today: str | None = None) -> list[Pick]:
    """`gate` is gate.table(...): companies need an adjusted Quality score of 60+ (funds exempt). None = no Quality score gate."""
    frame = scored[
        ~scored["symbol"].isin(excluded) &
        (scored["market_cap"].fillna(0) >= MIN_MARKET_CAP) & (scored["close"] >= MIN_PRICE)
        & (scored["dvol_21"] >= MIN_DOLLAR_VOLUME) & (scored["source"] == "mid")
        & (scored["atm"] <= MAX_ATM_IV) & (scored["ret_1m"] > WORST_MONTH)
        & (~scored["bucket"].isin(["Fear", "Hedged Rally"]))
    ].copy()
    if gate is not None:
        frame = frame[[sentinel_gate.passes_steady(sym, gate.get(sym), FUNDS) for sym in frame["symbol"]]]
    if frame.empty:
        return []
    flow = frame["sector"].map(sector_flow).fillna(0)
    frame["score"] = (100 - frame["atm"] * 100 + FLOW_POINTS * (flow > 0)).round().astype(int)
    frame = frame.sort_values("score", ascending=False).drop_duplicates("sector").head(MAX_PICKS)
    return [Pick(r["symbol"], r.get("name") or r["symbol"], r["sector"], int(r["score"]), float(r["close"]),
                 float(r["atm"]), float(r["ret_1m"]), *timing(r["bucket"])[:2], _with_score(_reasons(r), gate, r["symbol"]),
                 "" if earnings is None or today is None else steady_note(earnings.get(r["symbol"]), today))
            for r in frame.to_dict("records")]


def holdings_check(scored: pd.DataFrame, mine: set[str]) -> list[dict]:
    """A warning light for each stock you own (your starred stocks)."""
    rows = scored[scored["symbol"].isin(mine)]
    out = []
    for r in rows.to_dict("records"):
        kind, label, why = timing(r["bucket"])
        out.append({"symbol": r["symbol"], "name": r.get("name") or r["symbol"], "light": kind, "label": label,
                    "why": why, "price": float(r["close"]), "ret_1m": float(r["ret_1m"])})
    missing = sorted(mine - set(rows["symbol"]))
    out += [{"symbol": s, "name": s, "light": "none", "label": "No reading", "why": "Not in today's scan (no usable option quotes).",
             "price": None, "ret_1m": None} for s in missing]
    order = {"hold": 0, "add": 1, "wait": 2, "none": 3}
    return sorted(out, key=lambda x: order[x["light"]])


def split(amount: float, picks: list[dict]) -> dict:
    """Suggested split of new money: most to the index fund, the rest evenly across the picks you can add to now."""
    ready = ([p for p in picks if p["timing"] == "add"] or [p for p in picks if p["timing"] == "wait"])[:PER_MONTH]
    core = amount * (CORE_SHARE if ready else 1.0)
    each = (amount - core) / len(ready) if ready else 0
    return {"core": core, "each": each, "symbols": [p["symbol"] for p in ready]}


def without(picks: list[dict], excluded: set[str]) -> list[dict]:
    """Saved picks minus tickers you can't buy, so a click takes effect before the next scan."""
    return [p for p in picks if p["symbol"] not in excluded]


def as_dicts(picks: list[Pick]) -> list[dict]:
    return [{**asdict(p), "reasons": list(p.reasons)} for p in picks]
